"""
test_integration_pipeline.py — Tests d'intégration du pipeline ETL sur PostgreSQL.

Ces tests couvrent les modules que les tests unitaires ne peuvent pas atteindre.
src/extract.py, src/load.py, src/aggregate.py et src/db.py écrivent tous en base,
et ce qu'ils font n'a de sens que face à un vrai moteur : résolution des clés
étrangères, respect des contraintes d'intégrité référentielle, idempotence du
patron TRUNCATE + INSERT, exactitude des requêtes d'agrégation.

Rabattre ces vérifications sur SQLite n'aurait pas de sens ici : le pipeline
s'appuie sur plusieurs schémas logiques, et l'API sur ON CONFLICT avec index
d'expression. Un PostgreSQL éphémère coûte moins cher qu'une couche d'émulation
et teste le moteur réellement utilisé en production.

ACTIVATION — ces tests sont ignorés par défaut, afin que `pytest tests/` reste
exécutable sans infrastructure.

La seule dépendance est **un PostgreSQL jetable**, quelle qu'en soit la
provenance. Le projet n'en fournit ni n'en administre aucun : la voie de
référence est le service déclaré dans .github/workflows/tests.yml, que GitHub
Actions démarre avec le job et détruit à la fin. Ces tests s'exécutent donc à
chaque push sans qu'aucun moteur ne soit installé sur un poste de travail.

Pour les rejouer en local, il suffit de faire pointer les variables DB_* vers
n'importe quelle instance jetable — PostgreSQL installé sur le poste, service
d'un collègue, conteneur si l'on en dispose — puis :

    NEWTECH_INTEGRATION=1 DB_HOST=localhost DB_PORT=5432 DB_USER=test \
    DB_PASSWORD=test DB_NAME=newtech_test DB_SSLMODE=disable \
        pytest tests/test_integration_pipeline.py -v

Le nom de base DOIT contenir « test » : c'est l'un des deux garde-fous vérifiés
par _refuser_si_production() ci-dessous.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("NEWTECH_INTEGRATION") != "1",
    reason="Tests d'intégration désactivés (NEWTECH_INTEGRATION != 1). "
           "Voir la docstring du module pour les activer.",
)

RACINE = Path(__file__).resolve().parent.parent


def _refuser_si_production() -> None:
    """
    Garde-fou. Ces tests exécutent TRUNCATE : les lancer contre la base de
    production effacerait l'historique commercial et les commandes saisies.
    Deux vérifications indépendantes, l'une sur l'hôte, l'autre sur le nom.
    """
    hote = (os.getenv("DB_HOST") or "").lower()
    base = (os.getenv("DB_NAME") or "").lower()

    if any(marqueur in hote for marqueur in ("supabase", "pooler", "amazonaws")):
        pytest.exit(
            f"REFUS : DB_HOST='{hote}' désigne une base hébergée. "
            "Ces tests vident des tables et ne doivent jamais viser la production.",
            returncode=1,
        )
    if "test" not in base:
        pytest.exit(
            f"REFUS : DB_NAME='{base}' ne contient pas « test ». "
            "Par sécurité, ces tests exigent une base explicitement jetable.",
            returncode=1,
        )


@pytest.fixture(scope="session")
def moteur():
    """Moteur pointant la base jetable, schéma appliqué depuis sql/."""
    _refuser_si_production()
    from src.db import creer_moteur

    m = creer_moteur()
    # AUTOCOMMIT : les fichiers sql/ contiennent leur propre BEGIN/COMMIT,
    # qui entrerait en conflit avec une transaction ouverte par SQLAlchemy.
    with m.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for fichier in sorted((RACINE / "sql").glob("*.sql")):
            conn.exec_driver_sql(fichier.read_text(encoding="utf-8"))
    return m


@pytest.fixture(scope="session")
def pipeline_charge(moteur):
    """Exécute la chaîne complète Extract → Transform → Load → Aggregate."""
    from src.aggregate import alimenter_series
    from src.extract import extraire_tout
    from src.load import charger_analytics, charger_brut
    from src.transform import transformer_tout

    dfs = extraire_tout()
    charger_brut(dfs)
    charger_analytics(transformer_tout(dfs))
    alimenter_series()
    return moteur


def _compter(moteur, table: str) -> int:
    with moteur.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


# ─────────────────────────────────────────────────────────────────────────────
# Couche Load — schema_brut
# ─────────────────────────────────────────────────────────────────────────────

class TestChargementBrut:

    def test_les_trois_tables_brutes_sont_peuplees(self, pipeline_charge):
        for table in ("ventes_raw", "depenses_raw", "clients_raw"):
            assert _compter(pipeline_charge, f"schema_brut.{table}") > 0

    def test_anomalies_preservees_a_l_identique(self, pipeline_charge):
        # schema_brut est une photocopie de la source : les doublons de factures
        # et les montants sentinelles ne doivent pas y avoir été corrigés.
        with pipeline_charge.connect() as conn:
            doublons = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT facture_id FROM schema_brut.ventes_raw
                    GROUP BY facture_id HAVING COUNT(*) > 1
                ) d
            """)).scalar()
            zeros = conn.execute(text(
                "SELECT COUNT(*) FROM schema_brut.ventes_raw WHERE total = '0'"
            )).scalar()
        assert doublons > 0, "les doublons de la source ont été corrigés trop tôt"
        assert zeros > 0, "les montants sentinelles ont été corrigés trop tôt"

    def test_horodatage_de_chargement_renseigne(self, pipeline_charge):
        with pipeline_charge.connect() as conn:
            manquants = conn.execute(text(
                "SELECT COUNT(*) FROM schema_brut.ventes_raw WHERE charge_le IS NULL"
            )).scalar()
        assert manquants == 0


# ─────────────────────────────────────────────────────────────────────────────
# Couche Load — schema_analytics et intégrité référentielle
# ─────────────────────────────────────────────────────────────────────────────

class TestChargementAnalytics:

    def test_toutes_les_tables_sont_peuplees(self, pipeline_charge):
        for table in ("client", "employe", "facture", "ligne_facture",
                      "fournisseur", "categorie_achat", "achat"):
            assert _compter(pipeline_charge, f"schema_analytics.{table}") > 0, table

    def test_aucune_cle_etrangere_orpheline(self, pipeline_charge):
        # Le patron insert-then-read résout les identifiants générés par
        # PostgreSQL. S'il échouait, les FK seraient à NULL sans erreur visible.
        # id_employe est exclu : il est légitimement nullable, cf. le test suivant.
        with pipeline_charge.connect() as conn:
            for table, colonne in (
                ("facture", "id_client"),
                ("ligne_facture", "id_service"),
                ("ligne_facture", "id_facture"),
                ("achat", "id_fournisseur"),
                ("achat", "id_categorie"),
            ):
                nuls = conn.execute(text(
                    f"SELECT COUNT(*) FROM schema_analytics.{table} "
                    f"WHERE {colonne} IS NULL"
                )).scalar()
                assert nuls == 0, f"{table}.{colonne} : {nuls} clé(s) non résolue(s)"

    def test_factures_sans_employe_conservees_et_denombrees(self, pipeline_charge):
        # Une facture sans employé assigné est conservée — la commande a eu lieu
        # et son chiffre d'affaires compte — avec id_employe à NULL. Ce test
        # verrouille le fait que ce NULL provient bien de la source et non d'une
        # résolution de clé étrangère qui aurait échoué.
        # L'assertion est une inégalité, pas une égalité : la déduplication sur
        # Facture_ID retire des lignes en amont, le compte en base est donc au
        # plus égal au compte source. C'est le dépassement qui signalerait une
        # résolution défaillante.
        from src.extract import extraire_tout

        attendu = int(extraire_tout()["ventes"]["Employe_En_Charge"].isna().sum())
        with pipeline_charge.connect() as conn:
            constate = conn.execute(text(
                "SELECT COUNT(*) FROM schema_analytics.facture WHERE id_employe IS NULL"
            )).scalar()
        assert constate <= attendu, (
            f"{constate} factures sans employé pour {attendu} lignes source : "
            "une résolution de clé étrangère a échoué"
        )
        assert constate > 0, "le jeu de travail doit contenir ce cas de bord"

    def test_services_tous_normalises(self, pipeline_charge):
        # Les 16 formes non canoniques de la source doivent toutes se rattacher
        # aux 4 libellés du référentiel.
        with pipeline_charge.connect() as conn:
            libelles = {r[0] for r in conn.execute(text("""
                SELECT DISTINCT s.libelle
                FROM schema_analytics.ligne_facture lf
                JOIN schema_analytics.service s ON lf.id_service = s.id_service
            """))}
        assert libelles <= {"Imprimerie", "Sérigraphie", "Maintenance", "Vidéosurveillance"}

    def test_aucun_doublon_client_insensible_a_la_casse(self, pipeline_charge):
        with pipeline_charge.connect() as conn:
            doublons = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT LOWER(nom_client) FROM schema_analytics.client
                    GROUP BY LOWER(nom_client) HAVING COUNT(*) > 1
                ) d
            """)).scalar()
        assert doublons == 0

    def test_montants_sentinelles_recalcules(self, pipeline_charge):
        # Après transformation, plus aucune ligne ne doit porter un total nul
        # alors que quantité et prix unitaire sont renseignés.
        with pipeline_charge.connect() as conn:
            incoherentes = conn.execute(text("""
                SELECT COUNT(*) FROM schema_analytics.ligne_facture
                WHERE total_ligne = 0 AND quantite > 0 AND prix_unitaire > 0
            """)).scalar()
        assert incoherentes == 0

    def test_idempotence_du_rechargement(self, pipeline_charge):
        # TRUNCATE + INSERT : recharger deux fois doit produire le même état,
        # sans accumulation ni violation de contrainte d'unicité.
        from src.extract import extraire_tout
        from src.load import charger_analytics
        from src.transform import transformer_tout

        avant = {t: _compter(pipeline_charge, f"schema_analytics.{t}")
                 for t in ("client", "facture", "ligne_facture", "achat")}
        charger_analytics(transformer_tout(extraire_tout()))
        apres = {t: _compter(pipeline_charge, f"schema_analytics.{t}")
                 for t in ("client", "facture", "ligne_facture", "achat")}
        assert avant == apres


# ─────────────────────────────────────────────────────────────────────────────
# Couche Aggregate — séries temporelles de schema_ia
# ─────────────────────────────────────────────────────────────────────────────

class TestAgregation:

    def test_series_peuplees_au_format_prophet(self, pipeline_charge):
        with pipeline_charge.connect() as conn:
            for table in ("serie_ventes_journalieres", "serie_ventes_par_service"):
                lignes = conn.execute(text(
                    f"SELECT COUNT(*) FROM schema_ia.{table} "
                    "WHERE ds IS NOT NULL AND y IS NOT NULL"
                )).scalar()
                assert lignes > 0, table

    def test_ca_global_egale_somme_des_lignes_de_facture(self, pipeline_charge):
        # L'agrégation ne doit ni perdre ni dupliquer de chiffre d'affaires.
        with pipeline_charge.connect() as conn:
            source = conn.execute(text(
                "SELECT SUM(total_ligne) FROM schema_analytics.ligne_facture"
            )).scalar()
            serie = conn.execute(text(
                "SELECT SUM(y) FROM schema_ia.serie_ventes_journalieres"
            )).scalar()
        assert int(source) == int(serie)

    def test_serie_par_service_coherente_avec_la_serie_globale(self, pipeline_charge):
        with pipeline_charge.connect() as conn:
            globale = conn.execute(text(
                "SELECT SUM(y) FROM schema_ia.serie_ventes_journalieres"
            )).scalar()
            par_service = conn.execute(text(
                "SELECT SUM(y) FROM schema_ia.serie_ventes_par_service"
            )).scalar()
        assert int(globale) == int(par_service)

    def test_une_seule_ligne_par_jour_dans_la_serie_globale(self, pipeline_charge):
        with pipeline_charge.connect() as conn:
            doublons = conn.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT ds FROM schema_ia.serie_ventes_journalieres
                    GROUP BY ds HAVING COUNT(*) > 1
                ) d
            """)).scalar()
        assert doublons == 0

    def test_nb_commandes_compte_les_factures_distinctes(self, pipeline_charge):
        # COUNT(DISTINCT id_facture) et non COUNT(*) : le total doit égaler le
        # nombre de factures, pas le nombre de lignes de prestation.
        with pipeline_charge.connect() as conn:
            factures = conn.execute(text(
                "SELECT COUNT(*) FROM schema_analytics.facture"
            )).scalar()
            somme = conn.execute(text(
                "SELECT SUM(nb_commandes) FROM schema_ia.serie_ventes_journalieres"
            )).scalar()
        assert int(somme) == factures

    def test_idempotence_de_l_agregation(self, pipeline_charge):
        from src.aggregate import alimenter_series

        avant = _compter(pipeline_charge, "schema_ia.serie_ventes_journalieres")
        alimenter_series()
        apres = _compter(pipeline_charge, "schema_ia.serie_ventes_journalieres")
        assert avant == apres
