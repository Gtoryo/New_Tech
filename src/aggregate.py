"""
aggregate.py — Couche Agrégation IA du pipeline ETL
Responsabilité unique : lire schema_analytics et alimenter les deux
tables de séries temporelles dans schema_ia pour l'entraînement Prophet.

  alimenter_series() → schema_ia.serie_ventes_journalieres
                        schema_ia.serie_ventes_par_service

Colonnes produites (format natif Prophet) :
  ds            DATE    — date d'observation (une par jour)
  y             NUMERIC — chiffre d'affaires agrégé
  nb_commandes  INT     — nombre de factures distinctes ce jour
  rafraichi_le  TIMESTAMP — horodatage du dernier chargement
"""

import os
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

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


# ─────────────────────────────────────────────────────────────────────────────
# REQUÊTES D'AGRÉGATION
# ─────────────────────────────────────────────────────────────────────────────

# Série globale : CA + nb commandes par jour, toutes activités confondues
# COUNT DISTINCT sur id_facture car une facture peut avoir plusieurs lignes
_SQL_JOURNALIERE = """
    SELECT
        f.date_facture              AS ds,
        SUM(lf.total_ligne)         AS y,
        COUNT(DISTINCT f.id_facture) AS nb_commandes
    FROM schema_analytics.facture f
    JOIN schema_analytics.ligne_facture lf
         ON f.id_facture = lf.id_facture
    GROUP BY f.date_facture
    ORDER BY f.date_facture
"""

# Série par service : CA + nb commandes par (jour, pôle d'activité)
# 'service' stocke le libellé textuel, pas de FK vers service pour cette table
_SQL_PAR_SERVICE = """
    SELECT
        f.date_facture              AS ds,
        s.libelle                   AS service,
        SUM(lf.total_ligne)         AS y,
        COUNT(DISTINCT f.id_facture) AS nb_commandes
    FROM schema_analytics.facture f
    JOIN schema_analytics.ligne_facture lf
         ON f.id_facture = lf.id_facture
    JOIN schema_analytics.service s
         ON lf.id_service = s.id_service
    GROUP BY f.date_facture, s.libelle
    ORDER BY f.date_facture, s.libelle
"""


# ─────────────────────────────────────────────────────────────────────────────
# CHARGEMENT SCHEMA_IA
# ─────────────────────────────────────────────────────────────────────────────

def alimenter_series() -> None:
    """
    Lit les données agrégées depuis schema_analytics et charge les deux
    tables de séries temporelles dans schema_ia.

    Idempotente : TRUNCATE avant chaque INSERT, donc re-exécutable sans doublons.
    """
    moteur      = _creer_moteur()
    horodatage  = datetime.now()

    print("\n-- AGRÉGATION SCHEMA_IA ----------------------------------------")

    # ── ÉTAPE 1 : Lecture et agrégation depuis schema_analytics ─────────────
    with moteur.connect() as conn:
        df_journaliere = pd.read_sql(_SQL_JOURNALIERE, conn)
        df_par_service = pd.read_sql(_SQL_PAR_SERVICE, conn)

    print(f"  Jours distincts (série globale)      : {len(df_journaliere)}")
    print(f"  Lignes (série par service)           : {len(df_par_service)}")

    # ── ÉTAPE 2 : Ajout de l'horodatage de chargement ───────────────────────
    df_journaliere["rafraichi_le"] = horodatage
    df_par_service["rafraichi_le"] = horodatage

    # ── ÉTAPE 3 : Vidage des tables cibles avant rechargement ───────────────
    with moteur.connect() as conn:
        conn.execute(text(
            "TRUNCATE schema_ia.serie_ventes_journalieres RESTART IDENTITY"
        ))
        conn.execute(text(
            "TRUNCATE schema_ia.serie_ventes_par_service RESTART IDENTITY"
        ))
        conn.commit()

    # ── ÉTAPE 4 : Insertion dans schema_ia ──────────────────────────────────
    df_journaliere[["ds", "y", "nb_commandes", "rafraichi_le"]].to_sql(
        "serie_ventes_journalieres",
        moteur,
        schema="schema_ia",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    print(f"[AGGREGATE] serie_ventes_journalieres : {len(df_journaliere):>5} lignes chargées")

    df_par_service[["ds", "y", "service", "nb_commandes", "rafraichi_le"]].to_sql(
        "serie_ventes_par_service",
        moteur,
        schema="schema_ia",
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    print(f"[AGGREGATE] serie_ventes_par_service  : {len(df_par_service):>5} lignes chargées")

    print("-- FIN AGRÉGATION SCHEMA_IA -------------------------------------\n")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    alimenter_series()
