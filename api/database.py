"""
database.py — Moteur SQLAlchemy partagé pour l'API.

La construction de l'URL de connexion est déléguée à src.db.build_db_url() :
une seule source de vérité pour toute l'application, ETL et API comprises.
Toute évolution de la chaîne de connexion (TLS, pooling, timeout) n'a ainsi
qu'un seul point d'application.

lru_cache maintient une instance unique de moteur sur toute la durée de vie
du processus FastAPI, sans dépendance à Streamlit.
"""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from src.db import build_db_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Retourne le moteur SQLAlchemy partagé de l'API (pool_pre_ping activé)."""
    return create_engine(build_db_url(), pool_pre_ping=True)
