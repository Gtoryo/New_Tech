"""
extract.py — Couche Extraction du pipeline ETL
Responsabilité unique : lire les fichiers Excel sources et retourner
les données BRUTES sans aucune transformation.
"""

import pandas as pd
from pathlib import Path

# Dossier data/ situé à la racine du projet (deux niveaux au-dessus de src/)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Correspondance nom logique → (chemin fichier, nom de la feuille Excel)
SOURCES = {
    "ventes":   (DATA_DIR / "ventes_historiques.xlsx",     "Ventes"),
    "depenses": (DATA_DIR / "depenses_et_achats.xlsx",     "Dépenses"),
    "clients":  (DATA_DIR / "suivi_clients_prospects.xlsx", "Clients"),
}


def extraire_ventes() -> pd.DataFrame:
    path, sheet = SOURCES["ventes"]
    # dtype=str : tout est lu comme texte pour préserver les anomalies
    # (dates malformées, montants incohérents, cellules vides)
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = df.columns.str.strip()
    print(f"[EXTRACT] ventes_historiques   : {len(df):>5} lignes lues")
    return df


def extraire_depenses() -> pd.DataFrame:
    path, sheet = SOURCES["depenses"]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = df.columns.str.strip()
    print(f"[EXTRACT] depenses_et_achats   : {len(df):>5} lignes lues")
    return df


def extraire_clients() -> pd.DataFrame:
    path, sheet = SOURCES["clients"]
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = df.columns.str.strip()
    print(f"[EXTRACT] suivi_clients        : {len(df):>5} lignes lues")
    return df


def extraire_tout() -> dict[str, pd.DataFrame]:
    """
    Point d'entrée principal de la couche Extract.
    Retourne un dictionnaire contenant les 3 DataFrames bruts.
    """
    print("\n-- EXTRACTION --------------------------------------------------")
    return {
        "ventes":   extraire_ventes(),
        "depenses": extraire_depenses(),
        "clients":  extraire_clients(),
    }
