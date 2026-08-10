"""
auth.py — Authentification par clé API (header X-API-Key).

La clé est stockée dans la variable d'environnement API_SECRET_KEY,
jamais dans le code source. Conformité OWASP A07 (Identification failures).

Cette dépendance protège l'écriture ET la lecture. Les prévisions de chiffre
d'affaires et les KPI agrégés sont des données commerciales : les laisser en
accès libre reviendrait à publier l'activité de la PME à qui connaît l'URL de
l'instance, ce que l'OWASP API Security Top 10 classe en API2:2023 (Broken
Authentication). Seul /health reste ouvert, puisque sa fonction est justement
d'être interrogeable sans identification.
"""

import os
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_cle_api(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """
    Dépendance FastAPI : vérifie que X-API-Key correspond à API_SECRET_KEY.
    Lève HTTP 401 si la clé est absente ou incorrecte.
    """
    cle_attendue = os.getenv("API_SECRET_KEY", "")
    # Comparaison en temps constant — protège contre les timing attacks
    if not cle_attendue or not secrets.compare_digest(api_key or "", cle_attendue):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide ou manquante.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
