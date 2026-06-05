"""
load.py — Couche Chargement du pipeline ETL
Responsabilité unique : envoyer les DataFrames dans Supabase.

  charger_brut()      → schema_brut      (données brutes, archive)
  charger_analytics() → schema_analytics (données propres, à venir)
"""

import os
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Chargement des identifiants depuis variable.env (jamais écrits en dur)
load_dotenv("variable.env")


def _creer_moteur():
    """Construit et retourne un moteur SQLAlchemy connecté à Supabase."""
    url = (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD').strip()}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
        f"/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)


def charger_brut(dfs: dict[str, pd.DataFrame]) -> None:
    """
    Envoie les 3 DataFrames bruts dans schema_brut.
    Tronque les tables avant insertion pour garantir l'idempotence
    (re-exécuter le script ne crée pas de doublons).

    Paramètre :
        dfs — dictionnaire retourné par extract.extraire_tout()
              clés attendues : 'ventes', 'depenses', 'clients'
    """
    moteur = _creer_moteur()
    horodatage = datetime.now()

    # Correspondance clé du dictionnaire → nom de table dans schema_brut
    tables = {
        "ventes":   "ventes_raw",
        "depenses": "depenses_raw",
        "clients":  "clients_raw",
    }

    print("\n-- CHARGEMENT BRUT ---------------------------------------------")

    with moteur.connect() as conn:
        for cle, nom_table in tables.items():
            df = dfs[cle].copy()

            # Noms de colonnes en minuscules pour correspondre au schéma DB
            df.columns = df.columns.str.lower()

            # Horodatage de chargement (colonne charge_le dans schema_brut)
            df["charge_le"] = horodatage

            # Vidage avant rechargement — garantit qu'on ne cumule pas
            conn.execute(
                text(f"TRUNCATE TABLE schema_brut.{nom_table} RESTART IDENTITY")
            )
            conn.commit()

            # Envoi en bulk : une seule requête pour tout le DataFrame
            df.to_sql(
                nom_table,
                moteur,
                schema="schema_brut",
                if_exists="append",
                index=False,
                method="multi",  # regroupe les lignes en un seul INSERT
                chunksize=500,
            )

            print(f"[LOAD BRUT] {nom_table:<20} : {len(df):>5} lignes chargées")

    print("-- FIN CHARGEMENT BRUT -----------------------------------------\n")


# ─────────────────────────────────────────────────────────────────────────────
# CHARGEMENT ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def _inserer_et_lire(
    df: pd.DataFrame,
    nom_table: str,
    col_id: str,
    col_nom: str,
    moteur,
) -> dict:
    """
    Insère un DataFrame dans schema_analytics puis relit la table
    pour retourner le dictionnaire {nom → id} généré par la base.
    """
    df.to_sql(
        nom_table, moteur,
        schema="schema_analytics",
        if_exists="append",
        index=False,
        method="multi",
    )
    with moteur.connect() as conn:
        df_ids = pd.read_sql(
            f"SELECT {col_id}, {col_nom} FROM schema_analytics.{nom_table}",
            conn,
        )
    return dict(zip(df_ids[col_nom], df_ids[col_id]))


def charger_analytics(data: dict) -> None:
    """
    Insère les données transformées dans schema_analytics.

    Paramètre :
        data — dictionnaire retourné par transform.transformer_tout()
               clés : 'ventes', 'depenses', 'clients'
    """
    moteur  = _creer_moteur()
    ventes  = data["ventes"]
    depenses = data["depenses"]

    print("\n-- CHARGEMENT ANALYTICS ----------------------------------------")

    # ── ÉTAPE 0 : Vidage des tables dans l'ordre inverse des FK ─────────────
    with moteur.connect() as conn:
        conn.execute(text("""
            TRUNCATE
                schema_analytics.ligne_facture,
                schema_analytics.facture,
                schema_analytics.achat,
                schema_analytics.client,
                schema_analytics.employe,
                schema_analytics.fournisseur,
                schema_analytics.categorie_achat
            RESTART IDENTITY CASCADE
        """))
        conn.commit()

    # ── ÉTAPE 1 : Clients (fusion ventes + fichier clients) ──────────────────
    # Le fichier clients contient plus d'infos (email, ville, entreprise)
    df_clients_complets = data["clients"].copy()

    df_clients_ventes = ventes["clients"].copy()
    df_clients_ventes["entreprise"] = None
    df_clients_ventes["email"]      = None
    df_clients_ventes["ville"]      = None

    df_all_clients = pd.concat(
        [df_clients_complets, df_clients_ventes], ignore_index=True
    )
    df_all_clients = df_all_clients.drop_duplicates(subset=["nom_client"], keep="first")

    map_client = _inserer_et_lire(df_all_clients, "client", "id_client", "nom_client", moteur)
    print(f"[LOAD ANALYTICS] client          : {len(df_all_clients):>5} lignes")

    # ── ÉTAPE 2 : Employés ───────────────────────────────────────────────────
    map_employe = _inserer_et_lire(
        ventes["employes"], "employe", "id_employe", "nom_employe", moteur
    )
    print(f"[LOAD ANALYTICS] employe         : {len(ventes['employes']):>5} lignes")

    # ── ÉTAPE 3 : Services (table déjà peuplée — lecture seule) ─────────────
    with moteur.connect() as conn:
        df_services = pd.read_sql(
            "SELECT id_service, libelle FROM schema_analytics.service", conn
        )
    map_service = dict(zip(df_services["libelle"], df_services["id_service"]))

    # ── ÉTAPE 4 : Factures (avec IDs résolus) ────────────────────────────────
    df_factures = ventes["factures"].copy()
    df_factures["id_client"]  = df_factures["nom_client"].map(map_client)
    df_factures["id_employe"] = df_factures["nom_employe"].map(map_employe)
    df_factures = df_factures[
        ["facture_id", "date_facture", "statut_paiement", "id_client", "id_employe"]
    ].rename(columns={"facture_id": "id_facture"})
    df_factures.to_sql(
        "facture", moteur, schema="schema_analytics",
        if_exists="append", index=False, method="multi", chunksize=500,
    )
    print(f"[LOAD ANALYTICS] facture         : {len(df_factures):>5} lignes")

    # ── ÉTAPE 5 : Lignes de facture (avec IDs résolus) ───────────────────────
    df_lignes = ventes["lignes"].copy()
    df_lignes["id_service"] = df_lignes["service_libelle"].map(map_service)
    # Les prix en FCFA sont des entiers — cast pour correspondre au type DB
    df_lignes["prix_unitaire"] = df_lignes["prix_unitaire"].round(0).astype("Int64")
    df_lignes["total_ligne"]   = df_lignes["total_ligne"].round(0).astype("Int64")
    df_lignes = df_lignes[
        ["description", "quantite", "prix_unitaire", "total_ligne", "facture_id", "id_service"]
    ].rename(columns={"facture_id": "id_facture"})
    df_lignes.to_sql(
        "ligne_facture", moteur, schema="schema_analytics",
        if_exists="append", index=False, method="multi", chunksize=500,
    )
    print(f"[LOAD ANALYTICS] ligne_facture   : {len(df_lignes):>5} lignes")

    # ── ÉTAPE 6 : Fournisseurs ───────────────────────────────────────────────
    map_fournisseur = _inserer_et_lire(
        depenses["fournisseurs"], "fournisseur", "id_fournisseur", "nom", moteur
    )
    print(f"[LOAD ANALYTICS] fournisseur     : {len(depenses['fournisseurs']):>5} lignes")

    # ── ÉTAPE 7 : Catégories d'achat ─────────────────────────────────────────
    map_categorie = _inserer_et_lire(
        depenses["categories"], "categorie_achat", "id_categorie", "libelle", moteur
    )
    print(f"[LOAD ANALYTICS] categorie_achat : {len(depenses['categories']):>5} lignes")

    # ── ÉTAPE 8 : Achats (avec IDs résolus) ──────────────────────────────────
    df_achats = depenses["achats"].copy()
    df_achats["id_fournisseur"] = df_achats["nom_fournisseur"].map(map_fournisseur)
    df_achats["id_categorie"]   = df_achats["libelle_categorie"].map(map_categorie)
    df_achats["prix_achat_total"] = df_achats["prix_achat_total"].round(0).astype("Int64")
    df_achats = df_achats[
        ["date_achat", "libelle_article", "quantite",
         "prix_achat_total", "mode_paiement", "id_fournisseur", "id_categorie"]
    ]
    df_achats.to_sql(
        "achat", moteur, schema="schema_analytics",
        if_exists="append", index=False, method="multi", chunksize=500,
    )
    print(f"[LOAD ANALYTICS] achat           : {len(df_achats):>5} lignes")

    print("-- FIN CHARGEMENT ANALYTICS ------------------------------------\n")
