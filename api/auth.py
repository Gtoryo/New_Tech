"""
auth.py — Authentification par clé API (header X-API-Key).
La clé est stockée dans la variable d'environnement API_SECRET_KEY,
jamais dans le code source. Conformité OWASP A07 (Identification failures).
"""

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_cle_api(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """
    Dépendance FastAPI : vérifie que X-API-Key correspond à API_SECRET_KEY.
    Lève HTTP 401 si la clé est absente ou incorrecte.
    """
    cle_attendue = os.getenv("API_SECRET_KEY", "")
    if not cle_attendue or api_key != cle_attendue:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide ou manquante.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
