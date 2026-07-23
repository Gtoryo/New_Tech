"""
train.py — Entraînement des modèles de prévision Prophet
Responsabilité unique : lire schema_ia, entraîner un modèle Prophet
par série temporelle et sauvegarder chaque modèle dans models/.

  entrainer_tout() → models/prophet_global.pkl
                      models/prophet_{service}.pkl  (un par pôle)
"""

import sys
import pickle
import re
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet
from sqlalchemy import text

# Racine du projet ajoutée au path : autorise `python model/train.py` (CI)
# comme l'import depuis la racine.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import creer_moteur

# Graine fixe : rend les intervalles de prédiction (yhat_lower/yhat_upper)
# reproductibles d'une exécution à l'autre. Prophet 1.1.6 échantillonne
# l'incertitude via le RNG global de numpy (np.random.*), qu'il suffit donc
# de fixer avant chaque predict().
SEED = 42
np.random.seed(SEED)

# Journalisation applicative (remplace les print) ; Stan reste silencieux.
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Dossier de sauvegarde des modèles (créé automatiquement s'il n'existe pas)
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(texte: str) -> str:
    """Convertit un libellé accentué en nom de fichier ASCII sûr."""
    texte = texte.lower().strip()
    texte = re.sub(r"[éèêë]", "e", texte)
    texte = re.sub(r"[àâä]", "a", texte)
    texte = re.sub(r"[îï]",   "i", texte)
    texte = re.sub(r"[ôö]",   "o", texte)
    texte = re.sub(r"[ùûü]",  "u", texte)
    texte = re.sub(r"[^a-z0-9]+", "_", texte)
    return texte.strip("_")


def _entrainer_prophet(df: pd.DataFrame, label: str) -> Prophet:
    """
    Instancie et entraîne un modèle Prophet sur un DataFrame (colonnes ds, y).

    Paramètres retenus :
      yearly_seasonality  = True   — capte les pics annuels (rentrée, fêtes)
      weekly_seasonality  = True   — capte les variations lundi-dimanche
      daily_seasonality   = False  — inutile avec des observations journalières
      changepoint_prior_scale=0.05 — souplesse modérée face aux ruptures de tendance
    """
    logger.info("Entraînement [%s] sur %d observations...", label, len(df))

    modele = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        stan_backend="CMDSTANPY",
    )
    modele.fit(df[["ds", "y"]])
    logger.info("Modèle [%s] entraîné.", label)
    return modele


def _sauvegarder(modele: Prophet, chemin: Path) -> None:
    """Sérialise le modèle entraîné dans un fichier .pkl."""
    with open(chemin, "wb") as f:
        pickle.dump(modele, f)
    logger.info("Sauvegarde -> %s", chemin.relative_to(chemin.parent.parent))


def _sauvegarder_previsions_db(modele: Prophet, service: str, horizon: int = 180) -> None:
    """
    Génère les prévisions sur `horizon` jours et les stocke dans
    schema_ia.previsions_prophet.
    Les anciennes prévisions du service sont supprimées avant insertion
    pour garantir l'idempotence (ré-exécutable sans créer de doublons).
    """
    moteur = creer_moteur()

    # Reproductibilité des bornes d'intervalle (échantillonnage numpy).
    np.random.seed(SEED)
    futur      = modele.make_future_dataframe(periods=horizon, freq="D")
    previsions = modele.predict(futur)

    derniere_date = modele.history["ds"].max()
    df = previsions.loc[
        previsions["ds"] > derniere_date,
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ].copy()

    df["yhat"]       = np.maximum(df["yhat"],       0).round(0).astype(int)
    df["yhat_lower"] = np.maximum(df["yhat_lower"], 0).round(0).astype(int)
    df["yhat_upper"] = np.maximum(df["yhat_upper"], 0).round(0).astype(int)
    df["service"]    = service
    df["ds"]         = df["ds"].dt.date

    with moteur.begin() as conn:
        conn.execute(
            text("DELETE FROM schema_ia.previsions_prophet WHERE service = :s"),
            {"s": service},
        )
        df[["service", "ds", "yhat", "yhat_lower", "yhat_upper"]].to_sql(
            "previsions_prophet", moteur,
            schema="schema_ia", if_exists="append", index=False, method="multi",
        )

    logger.info("-> %d prévisions [%s] sauvegardées en base.", len(df), service)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRAÎNEMENT PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def entrainer_tout() -> None:
    """
    Entraîne et sauvegarde tous les modèles Prophet :
      1. Un modèle global (toutes activités)
      2. Un modèle par pôle de service
    """
    moteur = creer_moteur()

    logger.info("== ENTRAÎNEMENT PROPHET ==")

    # ── MODÈLE GLOBAL ────────────────────────────────────────────────────────
    logger.info("[1/2] Série globale (toutes activités confondues)")
    with moteur.connect() as conn:
        df_global = pd.read_sql(
            "SELECT ds, y FROM schema_ia.serie_ventes_journalieres ORDER BY ds",
            conn,
        )
    df_global["ds"] = pd.to_datetime(df_global["ds"])
    df_global["y"]  = pd.to_numeric(df_global["y"])

    modele_global = _entrainer_prophet(df_global, "global")
    _sauvegarder(modele_global, MODELS_DIR / "prophet_global.pkl")
    _sauvegarder_previsions_db(modele_global, "global")

    # ── MODÈLES PAR SERVICE ───────────────────────────────────────────────────
    logger.info("[2/2] Séries par pôle de service")
    with moteur.connect() as conn:
        df_services = pd.read_sql(
            "SELECT ds, y, service FROM schema_ia.serie_ventes_par_service ORDER BY ds",
            conn,
        )
    df_services["ds"] = pd.to_datetime(df_services["ds"])
    df_services["y"]  = pd.to_numeric(df_services["y"])

    services = df_services["service"].unique()
    for service in sorted(services):
        df_serie = (
            df_services[df_services["service"] == service][["ds", "y"]]
            .reset_index(drop=True)
        )
        modele = _entrainer_prophet(df_serie, service)
        nom_fichier = f"prophet_{_slugify(service)}.pkl"
        _sauvegarder(modele, MODELS_DIR / nom_fichier)
        _sauvegarder_previsions_db(modele, service)

    logger.info("== FIN ENTRAÎNEMENT PROPHET ==")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    entrainer_tout()
