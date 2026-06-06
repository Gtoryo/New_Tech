"""
predict.py — Lecture des prévisions Prophet depuis Supabase.
Les prévisions sont pré-calculées par model/train.py et stockées dans
schema_ia.previsions_prophet. Cette approche découple l'exécution de
Prophet (local / CI) de l'application Streamlit (cloud).

  predire(service, horizon_jours) → DataFrame (ds, yhat, yhat_lower, yhat_upper)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv(ROOT / "variable.env")

SERVICES_DISPONIBLES = [
    "global",
    "Imprimerie",
    "Maintenance",
    "Sérigraphie",
    "Vidéosurveillance",
]


@st.cache_resource
def _moteur():
    url = (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD').strip()}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
        f"/{os.getenv('DB_NAME')}?sslmode=require"
    )
    return create_engine(url)


def predire(service: str, horizon_jours: int = 90) -> pd.DataFrame:
    """
    Lit les prévisions pré-calculées depuis schema_ia.previsions_prophet.

    Paramètres :
        service       — "global", "Imprimerie", "Sérigraphie", etc.
        horizon_jours — nombre de jours futurs à retourner (max 180)

    Retourne un DataFrame avec les colonnes :
        ds          — date de prévision
        yhat        — prévision centrale (FCFA)
        yhat_lower  — borne basse de l'intervalle de confiance
        yhat_upper  — borne haute
    """
    with _moteur().connect() as conn:
        df = pd.read_sql(
            """
            SELECT ds, yhat, yhat_lower, yhat_upper
            FROM schema_ia.previsions_prophet
            WHERE service = %(service)s
            ORDER BY ds
            LIMIT %(horizon)s
            """,
            conn,
            params={"service": service, "horizon": horizon_jours},
        )

    df["ds"] = pd.to_datetime(df["ds"])
    return df
