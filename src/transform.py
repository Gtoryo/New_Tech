"""
transform.py — Couche Transformation du pipeline ETL
Responsabilité unique : nettoyer et typer les DataFrames bruts
produits par extract.py. Aucune écriture en base ici.
"""

import re
import pandas as pd
import numpy as np
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES PARTAGÉS
# ─────────────────────────────────────────────────────────────────────────────

# Mois français → numéro (pour les dates texte "Début Juin 2024")
_MOIS_FR = {
    "janvier": 1,  "février": 2,  "mars": 3,    "avril": 4,
    "mai": 5,      "juin": 6,     "juillet": 7, "août": 8,
    "septembre": 9,"octobre": 10, "novembre": 11,"décembre": 12,
}

# Dictionnaire de normalisation des types de service
_MAP_SERVICE = {
    "sérigraphie":       "Sérigraphie",
    "sérigrafe":         "Sérigraphie",
    "serigraphy":        "Sérigraphie",
    "sérigr.":           "Sérigraphie",
    "sérigrpahie":       "Sérigraphie",
    "imprimerie":        "Imprimerie",
    "imprimrie":         "Imprimerie",
    "imprimeri":         "Imprimerie",
    "vidéosurveillance": "Vidéosurveillance",
    "video surveillance":"Vidéosurveillance",
    "vidéo-surveillance":"Vidéosurveillance",
    "vidéosur.":         "Vidéosurveillance",
    "maintenance":       "Maintenance",
    "reparation":        "Maintenance",
    "maintenace":        "Maintenance",
    "maint.":            "Maintenance",
}

# Variantes connues de "Pointe-Noire" à normaliser
_VARIANTES_PN = {"pointe noire", "pn", "pte-noire", "pointenoire",
                 "pointe-noire", "p.noire", "pointe-noire"}


def _parser_date(valeur) -> datetime | None:
    """
    Convertit une valeur brute (str ou déjà datetime) en objet datetime.
    Gère 4 formats rencontrés dans les fichiers Excel sources :
      - "15/06/2024"   (format standard congolais)
      - "2024-06-15"   (ISO 8601)
      - "15-06-2024"   (tirets)
      - "Début Juin 2024" (texte libre → fixé au 1er du mois)
    Retourne None si la valeur est vide ou non parsable.
    """
    if pd.isna(valeur):
        return None

    if isinstance(valeur, (datetime, pd.Timestamp)):
        return pd.Timestamp(valeur)

    v = str(valeur).strip()

    try:
        return datetime.strptime(v, "%d/%m/%Y")
    except ValueError:
        pass

    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        pass

    try:
        return datetime.strptime(v, "%d-%m-%Y")
    except ValueError:
        pass

    # Format texte "Début Mois Année" — fixé au 1er du mois
    match = re.search(r"([A-Za-zÀ-ÿ]+)\s+(\d{4})", v, re.IGNORECASE)
    if match:
        mois_str = match.group(1).lower()
        annee    = int(match.group(2))
        mois_num = _MOIS_FR.get(mois_str)
        if mois_num:
            return datetime(annee, mois_num, 1)

    return None


def _normaliser_service(valeur) -> str | None:
    """Corrige les fautes de frappe des types de service vers le libellé canonique."""
    if pd.isna(valeur):
        return None
    cle = str(valeur).strip().lower()
    return _MAP_SERVICE.get(cle, str(valeur).strip())


def _normaliser_ville(valeur) -> str | None:
    """Normalise les variantes orthographiques de 'Pointe-Noire'."""
    if pd.isna(valeur):
        return None
    cle = str(valeur).strip().lower()
    if cle in _VARIANTES_PN:
        return "Pointe-Noire"
    return str(valeur).strip()
