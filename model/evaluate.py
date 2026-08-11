"""
evaluate.py — Calcul des métriques de cross-validation Prophet pour le rapport.

Lance :  python model/evaluate.py
Sortie : tableau MAE / MAPE / Coverage par horizon + comparaison changepoint_prior_scale.
Aucune connexion à Supabase requise : les modèles .pkl contiennent l'historique.
"""

import pickle
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics

warnings.filterwarnings("ignore")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# Graine fixe : Prophet échantillonne les bornes d'intervalle via le RNG global
# de numpy. Sans elle, le coverage varie d'un à deux points d'une exécution à
# l'autre et les chiffres publiés dans le rapport ne seraient pas reproductibles.
# Même valeur que model/train.py.
SEED = 42


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
    Cross-validation temporelle à fenêtre croissante (expanding window) : à
    chaque coupure, Prophet est réentraîné sur TOUT l'historique disponible
    jusqu'à cette date, et non sur une fenêtre de largeur fixe.
    Paramètres cohérents avec la section 4.3 du rapport :
      initial = 365 jours   (historique minimal d'entraînement)
      period  = 30  jours   (espacement entre les cutoffs)
      horizon = 90  jours   (fenêtre d'évaluation)
    """
    print(f"\n  Cross-validation [{label}] en cours...", end=" ", flush=True)

    np.random.seed(SEED)   # coverage reproductible d'une exécution à l'autre
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
# 2. ERREUR APRÈS AGRÉGATION TEMPORELLE (granularité de décision métier)
# ─────────────────────────────────────────────────────────────────────────────

def metriques_agregees(modele: Prophet, label: str) -> pd.DataFrame:
    """
    Recalcule l'erreur après agrégation des prévisions à la semaine et au mois.

    Justification méthodologique : la série journalière est intermittente
    (nombreux jours à faible chiffre d'affaires), ce qui gonfle mécaniquement
    le MAPE journalier — une erreur de 18 000 FCFA sur un jour réalisé à
    12 000 FCFA produit à elle seule 150 %. Or la décision métier
    (réapprovisionnement en consommables) se prend à la semaine ou au mois.
    Mesurer l'erreur à cette granularité reflète l'usage réel du modèle.

    Le réel (y) et la prévision (yhat) sont sommés sur exactement les mêmes
    jours au sein de chaque point de coupure : la comparaison reste donc
    non biaisée, y compris pour les périodes partielles en bord d'horizon.
    """
    print(f"\n  Agrégation temporelle [{label}] en cours...", end=" ", flush=True)

    np.random.seed(SEED)
    df_cv = cross_validation(
        modele,
        initial="365 days",
        period="30 days",
        horizon="90 days",
        parallel=None,
    )
    print("OK")

    lignes = []
    for libelle, regle in (("Journalière", "D"), ("Hebdomadaire", "W"), ("Mensuelle", "M")):
        df = df_cv.copy()
        df["periode"] = df["ds"].dt.to_period(regle)

        # Agrégation par (point de coupure, période) pour ne pas cumuler
        # plusieurs fois la même date issue de cutoffs différents.
        agg = (
            df.groupby(["cutoff", "periode"])[["y", "yhat"]]
            .sum()
            .reset_index()
        )
        agg = agg[agg["y"] > 0]   # MAPE indéfini sur une période à CA nul

        erreur_abs = (agg["y"] - agg["yhat"]).abs()
        lignes.append({
            "Granularité":  libelle,
            "N périodes":   len(agg),
            "MAE (FCFA)":   int(erreur_abs.mean().round(0)),
            "MAPE (%)":     round((erreur_abs / agg["y"]).mean() * 100, 1),
        })

    return pd.DataFrame(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMPARAISON À DES PRÉVISIONS DE RÉFÉRENCE (RelMAE)
# ─────────────────────────────────────────────────────────────────────────────

def metriques_vs_baselines(modele: Prophet, label: str) -> pd.DataFrame:
    """
    Compare Prophet à deux prévisions de référence sur les mêmes points de coupure.

    Un MAPE lu isolément ne dit rien de la valeur ajoutée d'un modèle : sur une
    série à forte dispersion, toute méthode affiche un pourcentage élevé. Le
    principe méthodologique (Hyndman & Koehler, 2006) consiste à rapporter
    l'erreur du modèle à celle d'une prévision naïve.

    La mesure calculée ici est un RelMAE (relative mean absolute error) et non
    le MASE au sens strict : le MASE met l'erreur à l'échelle de l'erreur naïve
    mesurée DANS l'échantillon d'entraînement, là où le rapport ci-dessous la
    mesure sur la fenêtre d'évaluation, aux mêmes dates que le modèle. Le seuil
    s'interprète de la même façon — sous 1, le modèle bat la référence — mais le
    dénominateur diffère, donc le nom aussi.

    Deux références sont évaluées sur les mêmes cutoffs et horizons que la
    cross-validation, et surtout à information strictement égale : chacune est
    bornée aux observations disponibles AU POINT DE COUPURE.
      - naïf saisonnier : rejoue la valeur du même jour de la semaine
        précédente (J-7), en remontant de semaine en semaine si la date est
        absente de la série (le pôle ferme certains jours), et à défaut la
        dernière observation connue au cutoff ;
      - moyenne historique : moyenne de tout l'historique disponible au cutoff.

    Un RelMAE inférieur à 1 établit que le modèle capture une structure que la
    prévision naïve ne reproduit pas.
    """
    print(f"\n  Comparaison aux références [{label}] en cours...", end=" ", flush=True)

    np.random.seed(SEED)
    df_cv = cross_validation(
        modele,
        initial="365 days",
        period="30 days",
        horizon="90 days",
        parallel=None,
    )
    print("OK")

    historique = modele.history.set_index("ds")["y"]

    # Historique tronqué au cutoff, mémoïsé : une prévision émise à la date de
    # coupure ne dispose de rien au-delà. Sans cette borne, la référence J-7
    # d'une date à cutoff+60 irait lire l'observation de cutoff+53, postérieure
    # à la coupure — la référence bénéficierait d'une information que le modèle
    # n'a pas, et la comparaison ne serait plus à information égale.
    _disponible: dict = {}

    def _historique_au_cutoff(cutoff) -> pd.Series:
        if cutoff not in _disponible:
            _disponible[cutoff] = historique[historique.index <= cutoff]
        return _disponible[cutoff]

    def _naif_saisonnier(date, cutoff) -> float:
        """Valeur du même jour de la semaine précédente, à défaut J-14, J-21, J-28."""
        dispo = _historique_au_cutoff(cutoff)
        for recul in (7, 14, 21, 28):
            valeur = dispo.get(date - pd.Timedelta(days=recul))
            if valeur is not None and not pd.isna(valeur):
                return valeur
        # Aucun antécédent hebdomadaire dans la fenêtre disponible : on rejoue
        # la dernière observation connue, ce que ferait un naïf de persistance.
        return dispo.iloc[-1] if len(dispo) else np.nan

    df_cv["naif"] = [
        _naif_saisonnier(d, c)
        for d, c in zip(df_cv["ds"], df_cv["cutoff"], strict=True)
    ]

    # Moyenne calculée une fois par cutoff plutôt qu'une fois par ligne
    moyennes = {c: _historique_au_cutoff(c).mean() for c in df_cv["cutoff"].unique()}
    df_cv["moyenne"] = df_cv["cutoff"].map(moyennes)

    # Garde-fou : une ligne sans référence calculable fausserait la comparaison.
    df_cv = df_cv.dropna(subset=["naif"])

    mae_naif = (df_cv["y"] - df_cv["naif"]).abs().mean()

    lignes = []
    for nom, colonne in (("Prophet",                "yhat"),
                         ("Naïf saisonnier (J-7)",  "naif"),
                         ("Moyenne historique",     "moyenne")):
        erreur_abs = (df_cv["y"] - df_cv[colonne]).abs()
        lignes.append({
            "Modèle":     nom,
            "MAE (FCFA)": int(erreur_abs.mean().round(0)),
            "MAPE (%)":   round((erreur_abs / df_cv["y"]).mean() * 100, 1),
            "RelMAE":     round(erreur_abs.mean() / mae_naif, 3),
        })

    return pd.DataFrame(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# 4. APPORT DE LA COMPOSANTE JOURNALIÈRE
# ─────────────────────────────────────────────────────────────────────────────

def comparer_daily_seasonality(modele_ref: Prophet) -> pd.DataFrame:
    """
    Mesure l'apport de la saisonnalité journalière, désactivée dans la
    configuration retenue (model/train.py).

    L'argument théorique est simple : les observations sont déjà agrégées par
    jour, une composante intra-journalière n'a donc aucune variation à
    modéliser et n'ajoute que des termes de Fourier sans information
    correspondante. Cette fonction le vérifie au lieu de l'affirmer.

    Même protocole que comparer_changepoint() — horizon de 30 jours, plus
    discriminant — afin que les deux tableaux se lisent sur la même base. Le
    MAE et le MAPE ne dépendent que de yhat, déterministe à ajustement donné :
    la graine ne joue ici que sur les bornes d'intervalle, non reprises.
    """
    df_train = modele_ref.history[["ds", "y"]].copy()
    resultats = []

    for actif in (False, True):
        print(f"  daily_seasonality={actif} ...", end=" ", flush=True)
        np.random.seed(SEED)
        m = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=actif,
            changepoint_prior_scale=0.05,
            stan_backend="CMDSTANPY",
        )
        m.fit(df_train)

        df_perf = performance_metrics(
            cross_validation(
                m, initial="365 days", period="30 days",
                horizon="30 days", parallel=None,
            ),
            rolling_window=1,
        )
        mae_30 = int(df_perf["mae"].mean().round(0))
        mape_30 = (df_perf["mape"].mean() * 100).round(1)
        print(f"MAPE 30j = {mape_30} %")

        resultats.append({
            "daily_seasonality":   actif,
            "MAE (horizon 30 j)":  mae_30,
            "MAPE (horizon 30 j)": f"{mape_30} %",
        })

    return pd.DataFrame(resultats)


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMPARAISON changepoint_prior_scale
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

    # ── Tableau 2 : erreur selon la granularité d'agrégation ─────────────────
    _afficher_titre("ERREUR SELON LA GRANULARITÉ DE DÉCISION — modèle global")
    df_agg = metriques_agregees(modele_global, "global")
    _afficher_df(df_agg)

    # ── Tableau 3 : comparaison aux prévisions de référence ──────────────────
    _afficher_titre("COMPARAISON AUX PRÉVISIONS DE RÉFÉRENCE (RelMAE) — modèle global")
    df_base = metriques_vs_baselines(modele_global, "global")
    _afficher_df(df_base)

    # ── Tableau 4 : apport de la composante journalière ──────────────────────
    _afficher_titre("APPORT DE LA COMPOSANTE JOURNALIÈRE (daily_seasonality)")
    print("  Réentraînement de 2 variantes en cours...\n")
    df_daily = comparer_daily_seasonality(modele_global)
    _afficher_df(df_daily)

    # ── Tableau 5 : comparaison changepoint_prior_scale ──────────────────────
    _afficher_titre("COMPARAISON changepoint_prior_scale")
    print("  Réentraînement de 3 variantes en cours (peut prendre 2-3 min)...\n")
    df_cp = comparer_changepoint(modele_global)
    _afficher_df(df_cp)

    print(f"\n{'=' * 60}\n  Terminé.\n{'=' * 60}\n")
