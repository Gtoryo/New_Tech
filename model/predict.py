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
def _fetch_previsions(service: str, horizon_jours: int) -> pd.DataFrame:
    """
    Appel HTTP vers l'API, mis en cache 1 h **en cas de succès uniquement**.

    Lève une exception si l'API est injoignable ou renvoie une erreur : comme
    st.cache_data ne met pas les exceptions en cache, une panne transitoire
    (cold start Render) est automatiquement réessayée au rechargement suivant,
    au lieu d'être figée pendant une heure.

    Le timeout de 60 s absorbe le réveil de l'instance Render gratuite, qui
    s'endort après 15 min d'inactivité et met jusqu'à ~50 s à redémarrer.
    """
    response = httpx.get(
        f"{_API_URL}/api/v1/previsions/{service}",
        params={"horizon": horizon_jours},
        headers={"X-API-Key": _API_KEY},
        timeout=60.0,
    )
    response.raise_for_status()
    df = pd.DataFrame(response.json())
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def predire(service: str, horizon_jours: int = 90) -> pd.DataFrame:
    """
    Interroge l'API REST pour obtenir les prévisions Prophet pré-calculées.

    Paramètres :
        service       — "global", "Imprimerie", "Sérigraphie", etc.
        horizon_jours — nombre de jours futurs à retourner (max 180)

    Retourne un DataFrame (ds, yhat, yhat_lower, yhat_upper), ou un DataFrame
    vide si l'API est injoignable ou renvoie une erreur — le dashboard reste
    alors fonctionnel et affiche un avertissement, sans lever d'exception.
    """
    try:
        return _fetch_previsions(service, horizon_jours)
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = exc.response.text[:200] or str(exc)
        st.error(f"Erreur API ({exc.response.status_code}) : {detail}")
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"])
    except httpx.RequestError:
        # Panne réseau / cold start : silencieux ici, le dashboard affiche
        # déjà un avertissement dédié quand le DataFrame est vide.
        return pd.DataFrame(columns=["ds", "yhat", "yhat_lower", "yhat_upper"])
