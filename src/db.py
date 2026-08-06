"""
db.py — Fabrique de moteur SQLAlchemy partagée (couches ETL, agrégation, IA).

Centralise la construction de l'URL de connexion Supabase afin d'éviter la
duplication de la logique de connexion dans load.py, aggregate.py, train.py
et dashboard.py (principe DRY — Don't Repeat Yourself).

Les identifiants sont lus depuis variable.env en local, ou depuis les
variables d'environnement du runner en CI (GitHub Secrets).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "variable.env")


def build_db_url() -> str:
    """
    Construit l'URL de connexion PostgreSQL/Supabase depuis l'environnement.

    DB_SSLMODE vaut « require » par défaut : le chiffrement en transit reste
    donc exigé partout où la variable n'est pas définie, c'est-à-dire en
    production. Les tests d'intégration la positionnent à « disable » pour
    joindre un PostgreSQL éphémère, qui n'expose pas de certificat.
    """
    return (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD', '').strip()}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
        f"/{os.getenv('DB_NAME')}"
        f"?sslmode={os.getenv('DB_SSLMODE', 'require')}"
    )


def creer_moteur() -> Engine:
    """
    Retourne un moteur SQLAlchemy connecté à Supabase.

    pool_pre_ping=True : teste la connexion avant chaque emprunt au pool,
    ce qui évite les erreurs « server closed the connection » après une
    période d'inactivité (utile face au cold start Supabase/pooler).
    """
    return create_engine(build_db_url(), pool_pre_ping=True)
