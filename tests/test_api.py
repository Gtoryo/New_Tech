"""
test_api.py — Tests d'intégration de l'API REST (FastAPI).

Contrairement aux tests unitaires de test_transform.py, ces tests exercent la
chaîne complète de l'API : routage, injection de dépendances, authentification
par clé, validation des contrats Pydantic et codes de statut HTTP.

Ils s'exécutent sans serveur ni base de données : le client de test Starlette
appelle l'application ASGI en mémoire, et tous les cas couverts sont rejetés
par l'API (401/422) avant qu'aucune requête SQL ne soit émise. Les scénarios
nécessitant une écriture réelle en base relèvent du test de bout en bout sur
une instance PostgreSQL dédiée (perspective documentée en section 5.1).
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

CLE_TEST = "cle-de-test-integration"

# Payload conforme au contrat CommandeIn (api/schemas.py)
COMMANDE_VALIDE = {
    "client":          "Mairie de Brazzaville",
    "telephone":       "+242 06 000 00 00",
    "date_facture":    "2026-06-15",
    "service":         "Imprimerie",
    "employe":         "Jean Moukassa",
    "statut_paiement": "Payé",
    "description":     "Impression flyers A5 recto-verso, 1 000 exemplaires",
    "quantite":        1000,
    "prix_unitaire":   150,
}


@pytest.fixture
def cle_api(monkeypatch):
    """Injecte une clé API connue le temps du test (jamais de secret en dur)."""
    monkeypatch.setenv("API_SECRET_KEY", CLE_TEST)
    return CLE_TEST


# ─────────────────────────────────────────────────────────────────────────────
# Health-check
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:

    def test_health_repond_200(self):
        assert client.get("/health").status_code == 200

    def test_health_ne_requiert_pas_authentification(self):
        # Endpoint de supervision : doit rester joignable sans clé
        assert client.get("/health").json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Authentification par clé API (api/auth.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthentification:

    def test_ecriture_sans_cle_rejetee_401(self):
        r = client.post("/api/v1/commandes/", json=COMMANDE_VALIDE)
        assert r.status_code == 401

    def test_ecriture_cle_invalide_rejetee_401(self, cle_api):
        r = client.post(
            "/api/v1/commandes/",
            json=COMMANDE_VALIDE,
            headers={"X-API-Key": "cle-erronee"},
        )
        assert r.status_code == 401

    def test_authentification_precede_validation_du_corps(self):
        # Un payload invalide SANS clé doit échouer en 401 (et non 422) :
        # la dépendance d'authentification s'exécute avant la validation.
        payload_invalide = dict(COMMANDE_VALIDE, service="Plomberie")
        r = client.post("/api/v1/commandes/", json=payload_invalide)
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Authentification des endpoints de LECTURE
# ─────────────────────────────────────────────────────────────────────────────
# Les prévisions de chiffre d'affaires et les KPI agrégés sont des données
# commerciales : les exposer en lecture libre revient à publier le chiffre
# d'affaires de la PME à qui connaît l'URL de l'instance Render. C'est la
# catégorie API2:2023 (Broken Authentication) de l'OWASP API Security Top 10.
# Seul /health reste ouvert, parce que c'est sa fonction.

class TestAuthentificationLecture:

    def test_previsions_sans_cle_rejetees_401(self):
        assert client.get("/api/v1/previsions/global").status_code == 401

    def test_previsions_cle_invalide_rejetee_401(self, cle_api):
        r = client.get("/api/v1/previsions/global",
                       headers={"X-API-Key": "cle-erronee"})
        assert r.status_code == 401

    def test_kpis_sans_cle_rejetes_401(self):
        assert client.get("/api/v1/kpis/").status_code == 401

    def test_kpis_cle_invalide_rejetes_401(self, cle_api):
        r = client.get("/api/v1/kpis/", headers={"X-API-Key": "cle-erronee"})
        assert r.status_code == 401

    def test_health_reste_ouvert(self, cle_api):
        # Contre-épreuve : la généralisation de l'authentification ne doit pas
        # avoir fermé le health-check, que Render et la supervision interrogent.
        assert client.get("/health").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Contrat d'entrée CommandeIn — référentiel contrôlé et contraintes métier
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationCommande:

    def test_service_hors_referentiel_rejete_422(self, cle_api):
        payload = dict(COMMANDE_VALIDE, service="Plomberie")
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422

    def test_statut_paiement_hors_referentiel_rejete_422(self, cle_api):
        payload = dict(COMMANDE_VALIDE, statut_paiement="Remboursé")
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422

    def test_quantite_nulle_rejetee_422(self, cle_api):
        payload = dict(COMMANDE_VALIDE, quantite=0)   # contrainte ge=1
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422

    def test_prix_unitaire_nul_rejete_422(self, cle_api):
        payload = dict(COMMANDE_VALIDE, prix_unitaire=0)   # contrainte gt=0
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422

    def test_champ_obligatoire_manquant_rejete_422(self, cle_api):
        payload = {k: v for k, v in COMMANDE_VALIDE.items() if k != "client"}
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Bornes de longueur — alignement du contrat sur les colonnes VARCHAR
# ─────────────────────────────────────────────────────────────────────────────
# Sans max_length, une saisie trop longue traverse la validation et n'est
# rejetée que par PostgreSQL (StringDataRightTruncation), que le gestionnaire
# d'exception convertit en 500 générique : la Gestionnaire perd sa saisie sans
# savoir quel champ corriger. Ces tests verrouillent le rejet en amont, en 422.

class TestBornesDeLongueur:

    @pytest.mark.parametrize(
        "champ, limite",
        [("client", 150), ("employe", 150), ("description", 255), ("telephone", 20)],
    )
    def test_depassement_de_borne_rejete_422(self, cle_api, champ, limite):
        payload = dict(COMMANDE_VALIDE, **{champ: "x" * (limite + 1)})
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422, f"{champ} au-dela de {limite} doit etre rejete"

    @pytest.mark.parametrize(
        "champ, limite",
        [("client", 150), ("employe", 150), ("description", 255), ("telephone", 20)],
    )
    def test_valeur_a_la_borne_exacte_acceptee(self, cle_api, champ, limite):
        # Contre-épreuve : la borne est inclusive, une valeur pile à la limite
        # ne doit pas être rejetée par le contrat. La requête échoue plus loin,
        # faute de base de données — tout sauf 422 prouve que le contrat passe.
        payload = dict(COMMANDE_VALIDE, **{champ: "x" * limite})
        r = client.post("/api/v1/commandes/", json=payload,
                        headers={"X-API-Key": CLE_TEST})
        assert r.status_code != 422, f"{champ} a exactement {limite} doit passer"


# ─────────────────────────────────────────────────────────────────────────────
# Contrat de lecture des prévisions
# ─────────────────────────────────────────────────────────────────────────────

class TestContratPrevisions:
    """
    Ces cas portent sur la validation du contrat, pas sur l'authentification :
    ils fournissent donc une clé valide, faute de quoi la dépendance
    d'authentification rejetterait la requête en 401 avant toute validation.
    """

    def test_service_inconnu_rejete_422(self, cle_api):
        r = client.get("/api/v1/previsions/Plomberie",
                       headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422

    def test_horizon_superieur_au_maximum_rejete_422(self, cle_api):
        r = client.get("/api/v1/previsions/global", params={"horizon": 999},
                       headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422   # borne le=180

    def test_horizon_nul_rejete_422(self, cle_api):
        r = client.get("/api/v1/previsions/global", params={"horizon": 0},
                       headers={"X-API-Key": CLE_TEST})
        assert r.status_code == 422   # borne ge=1


# ─────────────────────────────────────────────────────────────────────────────
# Documentation OpenAPI générée automatiquement
# ─────────────────────────────────────────────────────────────────────────────

class TestDocumentationOpenAPI:

    def test_schema_openapi_disponible(self):
        assert client.get("/openapi.json").status_code == 200

    def test_les_quatre_endpoints_sont_exposes(self):
        chemins = client.get("/openapi.json").json()["paths"]
        for endpoint in (
            "/health",
            "/api/v1/previsions/{service}",
            "/api/v1/commandes/",
            "/api/v1/kpis/",
        ):
            assert endpoint in chemins

    def test_contrat_commande_documente(self):
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert "CommandeIn" in schemas
