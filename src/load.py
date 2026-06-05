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
