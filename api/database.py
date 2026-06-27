"""
database.py — Moteur SQLAlchemy partagé pour l'API.
Utilise lru_cache pour maintenir une instance unique sur toute la durée
de vie du processus FastAPI, sans dépendance à Streamlit.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "variable.env")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD', '').strip()}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
        f"/{os.getenv('DB_NAME')}?sslmode=require"
    )
    return create_engine(url, pool_pre_ping=True)
