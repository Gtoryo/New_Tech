"""
evaluate.py — Calcul des métriques de cross-validation Prophet pour le rapport.

Lance :  python model/evaluate.py
Sortie : tableau MAE / MAPE / Coverage par horizon + comparaison changepoint_prior_scale.
Aucune connexion à Supabase requise : les modèles .pkl contiennent l'historique.
"""

import pickle
import warnings
from pathlib import Path

import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics

warnings.filterwarnings("ignore")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _charger_modele(chemin: Path) -> Prophet:
    with open(chemin, "rb") as f:
        return pickle.load(f)


def _afficher_titre(titre: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {titre}")
    print(f"{'=' * 60}")


def _afficher_df(df: pd.DataFrame) -> None:
    print(df.to_string(index=False))


# ─────────────────────────────────────────────────────────────────────────────
# 1. MÉTRIQUES GLOBALES PAR HORIZON (MAE / MAPE / Coverage)
# ─────────────────────────────────────────────────────────────────────────────

def metriques_par_horizon(modele: Prophet, label: str) -> pd.DataFrame:
    """
    Cross-validation temporelle à fenêtre glissante.
    Paramètres cohérents avec la section 4.3 du rapport :
      initial = 365 jours   (historique minimal d'entraînement)
      period  = 30  jours   (espacement entre les cutoffs)
      horizon = 90  jours   (fenêtre d'évaluation)
    """
    print(f"\n  Cross-validation [{label}] en cours...", end=" ", flush=True)
    
    df_cv = cross_validation(
        modele,
        initial="365 days", # période d'entraînement initiale minimale
        period="30 days",   # nouveau point de coupure toutes les 4 semaines
        horizon="90 days",  # évaluation sur les 90 jours suivant chaque coupure
        parallel=None,
    )
    print("OK")

    df_perf = performance_metrics(df_cv, rolling_window=0.1)

    # Sélection des horizons représentatifs : 30 / 60 / 90 jours
    horizons_cibles = [30, 60, 90]
    df_perf["horizon_j"] = df_perf["horizon"].dt.days
    df_filtre = df_perf[df_perf["horizon_j"].isin(horizons_cibles)][
        ["horizon_j", "mae", "mape", "coverage"]
    ].copy()
    df_filtre.columns = ["Horizon (jours)", "MAE (FCFA)", "MAPE (%)", "Coverage (%)"]
    df_filtre["MAE (FCFA)"] = df_filtre["MAE (FCFA)"].round(0).astype(int)
    df_filtre["MAPE (%)"]   = (df_filtre["MAPE (%)"] * 100).round(1)
    df_filtre["Coverage (%)"] = (df_filtre["Coverage (%)"] * 100).round(1)

    return df_filtre


# ─────────────────────────────────────────────────────────────────────────────
# 2. COMPARAISON changepoint_prior_scale
# ─────────────────────────────────────────────────────────────────────────────

def comparer_changepoint(modele_ref: Prophet) -> pd.DataFrame:
    """
    Réentraîne 3 variantes du modèle avec des changepoint_prior_scale différents
    et compare leur MAPE sur un horizon de 30 jours (horizon court = plus discriminant).
    Utilise l'historique du modèle de référence comme données d'entraînement.
    """
    df_train = modele_ref.history[["ds", "y"]].copy()
    valeurs = [0.01, 0.05, 0.50]
    resultats = []

    for cps in valeurs:
        print(f"  changepoint_prior_scale={cps} ...", end=" ", flush=True)
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=cps,
            stan_backend="CMDSTANPY",
        )
        m.fit(df_train)

        df_cv = cross_validation(
            m,
            initial="365 days",
            period="30 days",
            horizon="30 days",
            parallel=None,
        )
        df_perf = performance_metrics(df_cv, rolling_window=1)
        mape_30 = (df_perf["mape"].mean() * 100).round(1)
        print(f"MAPE 30j = {mape_30} %")

        if cps == 0.01:
            comportement = "Trop rigide — sous-ajustement (underfitting)"
        elif cps == 0.05:
            comportement = "Souplesse modérée — meilleur équilibre biais/variance"
        else:
            comportement = "Trop réactif — sur-ajustement (overfitting)"

        resultats.append({
            "changepoint_prior_scale": cps,
            "Comportement": comportement,
            "MAPE (horizon 30 j)": f"{mape_30} %",
        })

    return pd.DataFrame(resultats)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pkl_global = MODELS_DIR / "prophet_global.pkl"

    if not pkl_global.exists():
        print(f"[ERREUR] Modèle introuvable : {pkl_global}")
        print("Lancez d'abord : python model/train.py")
        raise SystemExit(1)

    modele_global = _charger_modele(pkl_global)

    # ── Tableau 1 : métriques par horizon ────────────────────────────────────
    _afficher_titre("MÉTRIQUES DE CROSS-VALIDATION — modèle global")
    df_metriques = metriques_par_horizon(modele_global, "global")
    _afficher_df(df_metriques)

    # ── Tableau 2 : comparaison changepoint_prior_scale ──────────────────────
    _afficher_titre("COMPARAISON changepoint_prior_scale")
    print("  Réentraînement de 3 variantes en cours (peut prendre 2-3 min)...\n")
    df_cp = comparer_changepoint(modele_global)
    _afficher_df(df_cp)

    print(f"\n{'=' * 60}\n  Terminé.\n{'=' * 60}\n")
