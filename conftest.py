"""
conftest.py — Configuration partagée de la suite de tests.

Deux responsabilités : rendre les modules du projet importables depuis tests/,
et refuser d'exécuter la suite contre une base hébergée.
"""

import os
import pathlib
import sys

import pytest

# Garantit que les modules src/ et model/ sont importables depuis tests/
sys.path.insert(0, str(pathlib.Path(__file__).parent))

# Importer src.db exécute son load_dotenv(variable.env) : les variables DB_*
# lues plus bas sont donc exactement celles dont creer_moteur() et get_engine()
# se serviraient. Les relire sans cet import donnerait des valeurs vides en
# local, et le garde-fou laisserait passer précisément le cas qu'il doit
# intercepter.
import src.db  # noqa: F401

# Marqueurs d'hébergeurs. Une base jetable tourne sur localhost ou sur un
# service éphémère de CI ; aucun de ces noms n'y apparaît.
_HOTES_HEBERGES = ("supabase", "pooler", "amazonaws", "render.com", "neon.tech")


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Interrompt la session si la connexion configurée désigne une base hébergée.

    Le risque n'est pas théorique. tests/test_api.py envoie des POST valides et
    authentifiés sur /api/v1/commandes/ : sans ce contrôle, chaque exécution
    locale de `pytest` insère de vraies commandes dans la base de production,
    puisque variable.env y pointe et que src/db.py le charge à l'import. Le
    défaut est silencieux — l'API répond 201, les tests passent au vert, et les
    lignes fantômes ne se découvrent qu'en comptant les factures en base.

    Le contrôle est placé ici plutôt que dans un fichier de tests, et dans
    pytest_sessionstart plutôt que dans une fixture : il s'exécute une fois,
    avant toute collecte, et couvre l'intégralité de la suite — y compris les
    fichiers de tests qui seront ajoutés plus tard.

    Le garde-fou de tests/test_integration_pipeline.py reste en place : il
    vérifie en plus que DB_NAME contient « test », condition propre aux tests
    qui exécutent des TRUNCATE.
    """
    hote = (os.getenv("DB_HOST") or "").lower()

    if any(marqueur in hote for marqueur in _HOTES_HEBERGES):
        pytest.exit(
            f"REFUS : DB_HOST='{hote}' designe une base hebergee. La suite "
            "ecrit des commandes et vide des tables ; elle ne doit jamais "
            "viser la production. Faites pointer les variables DB_* vers une "
            "base jetable avant de relancer.",
            returncode=1,
        )
