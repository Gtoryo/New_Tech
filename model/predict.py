"""
predict.py — Accès aux prévisions Prophet via l'API REST.

Le tableau de bord Streamlit appelle cette fonction ; elle interroge
l'API (GET /api/v1/previsions/{service}) plutôt que la base de données
directement. Ce découplage permet à tout client futur (mobile, ERP)
d'utiliser le même endpoint sans accès direct à Supabase.

  predire(service, horizon_jours) → DataFrame (ds, yhat, yhat_lower, yhat_upper)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv(ROOT / "variable.env")

SERVICES_DISPONIBLES = [
    "global",
    "Imprimerie",
    "Maintenance",
    "Sérigraphie",
    "Vidéosurveillance",
]

_API_URL = os.getenv("API_URL", "http://localhost:8000")
_API_KEY = os.getenv("API_SECRET_KEY", "")


@st.cache_data(ttl=3600)
def predire(service: str, horizon_jours: int = 90) -> pd.DataFrame:
    """
    Interroge l'API REST pour obtenir les prévisions Prophet pré-calculées.

    Paramètres :
        service       — "global", "Imprimerie", "Sérigraphie", etc.
        horizon_jours — nombre de jours futurs à retourner (max 180)

    Retourne un DataFrame avec les colonnes :
        ds          — date de prévision
        yhat        — prévision centrale (FCFA)
        yhat_lower  — borne basse de l'intervalle de prédiction à 80 %
        yhat_upper  — borne haute de l'intervalle de prédiction à 80 %

    Lève une exception Streamlit si l'API est injoignable ou renvoie une erreur.
    """
    try:
        response = httpx.get(
            f"{_API_URL}/api/v1/previsions/{service}",
            params={"horizon": horizon_jours},
            headers={"X-API-Key": _API_KEY},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = exc.response.text[:200] or str(exc)
        st.error(f"Erreur API ({exc.response.status_code}) : {detail}")
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"])
    except httpx.RequestError as exc:
        st.error(
            f"API injoignable ({_API_URL}). "
            "Vérifiez que le serveur est démarré (`uvicorn api.main:app --reload`)."
        )
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"])

    df = pd.DataFrame(response.json())
    df["ds"] = pd.to_datetime(df["ds"])
    return df
