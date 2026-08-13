"""
monitor.py — Surveillance de la dérive du modèle après réentraînement.

Le workflow mensuel vérifiait jusqu'ici que l'entraînement se terminait sans
erreur. Rien de plus : un modèle qui s'entraînerait proprement sur des données
dégradées publiait ses prévisions sans qu'aucune alerte ne le signale.

Ce script mesure la compétence prédictive réelle sur une fenêtre de validation
retenue à la fin de l'historique. Pour chaque modèle : on réentraîne sur
l'historique privé de ses N derniers jours CALENDAIRES, on prédit cette fenêtre,
et on compare aux valeurs observées. Le découpage porte sur la date et non sur
le rang : les séries ne contiennent que les jours d'activité, si bien qu'un
prélèvement de 30 lignes couvrirait de 44 à 100 jours calendaires selon le pôle
et ne correspondrait plus au cycle de réentraînement qu'il prétend simuler.

Le seuil porte sur le RelMAE et non sur le MAPE. Le MAPE n'a pas de valeur de
référence absolue — 130 % est normal sur cette série, comme le montre la section
4.3 du rapport — alors qu'un RelMAE supérieur à 1 signifie littéralement que le
modèle fait moins bien qu'une prévision naïve qui rejoue la semaine précédente.
C'est un critère interprétable sans connaître la série.

Le script s'exécute APRÈS la publication des prévisions : il alerte, il ne
bloque pas. Sur une PME, mieux vaut des prévisions dégradées et signalées que
pas de prévisions du tout — le Directeur garde une projection, et l'exploitant
sait qu'elle mérite un regard.

Lancement :  python model/monitor.py
Sortie      : code 0 si tous les modèles restent sous le seuil, 1 sinon.
Aucune connexion à Supabase requise : les .pkl contiennent l'historique.
"""

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODELS_DIR = ROOT / "models"

SEED = 42

# Étendue CALENDAIRE, en jours, de la fenêtre de validation retenue en fin
# d'historique. Trente jours correspondent à un cycle de réentraînement complet :
# c'est la période pendant laquelle les prévisions publiées seront consommées.
FENETRE_VALIDATION = int(os.getenv("DRIFT_FENETRE_JOURS", "30"))

# RelMAE au-delà duquel le modèle n'apporte plus rien face à une prévision naïve.
SEUIL_ERREUR = float(os.getenv("DRIFT_SEUIL_RELMAE", "1.0"))

# Seuil d'avertissement : le modèle reste meilleur que le naïf, mais sa marge
# se réduit. Sert de signal précoce avant que la dérive ne devienne bloquante.
SEUIL_ALERTE = float(os.getenv("DRIFT_SEUIL_ALERTE", "0.85"))

# Effectif minimal de points de comparaison pour qu'un RelMAE soit opposable.
# Le contrôle porte sur n_relmae et non sur la taille de la fenêtre : le ratio
# se calcule sur le premier, c'est donc lui qui conditionne sa fiabilité.
# En exploitation normale, une série dense fournit une vingtaine de points ; en
# deçà de dix, la valeur ne distingue plus une dérive du modèle d'une simple
# absence d'activité sur la période, et ne peut pas fonder une alerte.
MIN_POINTS_RELMAE = int(os.getenv("DRIFT_MIN_POINTS", "10"))


def _annoter(niveau: str, message: str) -> None:
    """
    Émet une annotation GitHub Actions, qui remonte dans le résumé du run et
    dans la notification par courriel. En exécution locale, la syntaxe reste
    lisible comme une simple ligne de texte.
    """
    print(
        f"::{niveau}::{message}" if os.getenv("GITHUB_ACTIONS")
        else f"[{niveau.upper()}] {message}"
    )


def _relmae(reel: pd.Series, prevu: pd.Series, historique: pd.Series) -> tuple[float, int]:
    """
    Erreur absolue du modèle rapportée à celle d'une prévision naïve saisonnière
    (même jour de la semaine précédente), calculée sur la même fenêtre.

    C'est un RelMAE (relative mean absolute error) et non le MASE d'Hyndman &
    Koehler (2006) : ce dernier met l'erreur à l'échelle de l'erreur naïve
    mesurée DANS l'échantillon d'entraînement, là où le rapport ci-dessous la
    mesure sur la fenêtre d'évaluation. L'interprétation du seuil est la même —
    au-dessus de 1, le modèle fait moins bien que la prévision naïve — mais le
    dénominateur diffère, donc le nom aussi.

    La référence ne lit que `historique`, borné à la fin de la période
    d'entraînement : elle ne dispose d'aucune observation postérieure à la
    bascule, exactement comme le modèle. Cette borne a une conséquence qu'il
    faut publier plutôt que taire : au-delà du 28e jour de la fenêtre, aucun
    des quatre reculs hebdomadaires ne retombe dans l'historique disponible, et
    la date est écartée du calcul. Le ratio porte donc sur un sous-ensemble de
    la fenêtre, dont la taille est retournée avec lui — sans quoi le tableau
    afficherait un effectif qui n'est pas celui de la mesure.

    Retourne (RelMAE, nombre d'observations réellement comparées).
    """
    naif = []
    for date in reel.index:
        for recul in (7, 14, 21, 28):
            valeur = historique.get(date - pd.Timedelta(days=recul))
            if valeur is not None and not pd.isna(valeur):
                naif.append(valeur)
                break
        else:
            naif.append(np.nan)

    naif = pd.Series(naif, index=reel.index)
    valides = naif.notna()
    n_valides = int(valides.sum())

    if n_valides == 0:
        return float("nan"), 0

    erreur_modele = (reel[valides] - prevu[valides]).abs().mean()
    erreur_naif = (reel[valides] - naif[valides]).abs().mean()

    ratio = float("inf") if erreur_naif == 0 else erreur_modele / erreur_naif
    return ratio, n_valides


def evaluer_derive(chemin_pkl: Path) -> dict:
    """
    Réentraîne le modèle sur l'historique amputé de sa fenêtre de validation,
    puis mesure l'erreur sur cette fenêtre.
    """
    import pickle

    with open(chemin_pkl, "rb") as f:
        modele_publie = pickle.load(f)

    historique = modele_publie.history[["ds", "y"]].copy().sort_values("ds")
    label = chemin_pkl.stem.replace("prophet_", "")

    # Découpage sur la DATE et non sur le rang. Les séries ne contiennent que
    # les jours d'activité : un `iloc[-30:]` prélève 30 OBSERVATIONS, ce qui
    # couvre 44 à 100 jours calendaires selon le pôle. La fenêtre doit
    # correspondre au cycle de réentraînement réel, qui se compte en jours.
    fin = historique["ds"].max()
    debut = historique["ds"].min()
    bascule = fin - pd.Timedelta(days=FENETRE_VALIDATION)

    # Il faut au moins trois fenêtres calendaires pour que le reste de
    # l'historique permette un entraînement représentatif.
    span_jours = (fin - debut).days
    if span_jours < FENETRE_VALIDATION * 3:
        return {"modele": label, "statut": "ignore",
                "detail": f"historique trop court pour une validation "
                          f"({span_jours} jours calendaires)"}

    entrainement = historique[historique["ds"] <= bascule]
    validation = historique[historique["ds"] > bascule]

    if len(validation) < 5:
        return {"modele": label, "statut": "ignore",
                "detail": f"fenêtre de {FENETRE_VALIDATION} jours : seulement "
                          f"{len(validation)} observation(s), mesure non significative"}

    np.random.seed(SEED)
    temoin = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        stan_backend="CMDSTANPY",
    )
    temoin.fit(entrainement)

    futur = temoin.make_future_dataframe(periods=FENETRE_VALIDATION, freq="D")
    previsions = temoin.predict(futur).set_index("ds")["yhat"]

    reel = validation.set_index("ds")["y"]
    prevu = previsions.reindex(reel.index)
    serie_entrainement = entrainement.set_index("ds")["y"]

    erreur_abs = (reel - prevu).abs()
    relmae, n_relmae = _relmae(reel, prevu, serie_entrainement)
    return {
        "modele": label,
        "statut": "mesure",
        "n_obs": len(reel),
        "n_jours": FENETRE_VALIDATION,
        "mae": float(erreur_abs.mean()),
        "mape": float((erreur_abs / reel.replace(0, np.nan)).mean() * 100),
        "relmae": relmae,
        # Effectif réellement comparé à la référence naïve, inférieur à n_obs :
        # au-delà du 28e jour de la fenêtre, aucun recul hebdomadaire ne
        # retombe dans l'historique d'entraînement (cf. _relmae).
        "n_relmae": n_relmae,
        # Ce qui rend une saisonnalité annuelle estimable, c'est l'ÉTENDUE
        # CALENDAIRE de l'historique — la série de Fourier est indexée sur le
        # jour de l'année — et non le nombre d'observations. Un pôle à faible
        # fréquence peut couvrir deux cycles annuels avec 295 observations
        # seulement : la composante reste identifiable, simplement estimée sur
        # des points épars, donc plus bruitée.
        "span_jours": span_jours,
        "historique_court": span_jours < 365,
        # Densité d'observation sur l'ensemble de l'historique : signale une
        # estimation saisonnière éparse, cas distinct du « moins d'un an ».
        "n_obs_total": len(historique),
        "densite": len(historique) / max(span_jours, 1),
    }


def main() -> int:
    pkl_global = MODELS_DIR / "prophet_global.pkl"
    if not pkl_global.exists():
        _annoter("error", f"Modèle introuvable : {pkl_global}. Lancez d'abord model/train.py.")
        return 1

    print(f"Surveillance de dérive — fenêtre de validation : "
          f"{FENETRE_VALIDATION} jours calendaires")
    print(f"Seuils RelMAE — alerte {SEUIL_ALERTE}, erreur {SEUIL_ERREUR}\n")

    resultats = [evaluer_derive(p) for p in sorted(MODELS_DIR.glob("prophet_*.pkl"))]

    mesures = [r for r in resultats if r["statut"] == "mesure"]
    if mesures:
        # « N obs. » et non « N jours » : la colonne compte les observations
        # tombant dans la fenêtre, dont l'étendue calendaire est fixée par
        # FENETRE_VALIDATION et rappelée en en-tête. « N réf. » compte celles
        # que la référence naïve peut couvrir : MAE et MAPE portent sur la
        # fenêtre entière, le RelMAE sur ce sous-ensemble.
        tableau = pd.DataFrame(mesures)[
            ["modele", "n_obs", "mae", "mape", "relmae", "n_relmae"]
        ]
        tableau.columns = ["Modèle", "N obs.", "MAE (FCFA)", "MAPE (%)", "RelMAE", "N réf."]
        tableau["MAE (FCFA)"] = tableau["MAE (FCFA)"].round(0).astype(int)
        tableau["MAPE (%)"] = tableau["MAPE (%)"].round(1)
        tableau["RelMAE"] = tableau["RelMAE"].round(3)
        print(tableau.to_string(index=False))
        print()

    for r in resultats:
        if r["statut"] == "ignore":
            _annoter("notice", f"[{r['modele']}] non evalue : {r['detail']}")
            continue
        if r.get("historique_court"):
            _annoter("notice", f"[{r['modele']}] historique de {r['span_jours']} jours "
                               f"calendaires, soit moins d un cycle annuel : la saisonnalite "
                               f"annuelle n est pas identifiable, ses previsions relevent "
                               f"surtout de la tendance.")
        elif r.get("densite", 1.0) < 0.5:
            _annoter("notice", f"[{r['modele']}] {r['n_obs_total']} observations pour "
                               f"{r['span_jours']} jours calendaires (densite "
                               f"{r['densite']:.2f}) : la saisonnalite annuelle reste "
                               f"identifiable mais est estimee sur des points epars, "
                               f"donc plus bruitee.")

    # Le modèle global conditionne le statut du run : c'est celui sur lequel le
    # Directeur lit sa tendance d'ensemble. Les modèles par pôle, entraînés sur
    # des séries plus courtes et plus bruitées, ne remontent qu'un avertissement.
    global_ = next((r for r in mesures if r["modele"] == "global"), None)
    en_echec = False
    global_evalue = False

    for r in mesures:
        relmae = r["relmae"]
        est_global = r is global_

        # Effectif insuffisant : la valeur reste publiée dans le tableau, mais
        # elle ne déclenche rien. Une fenêtre peut compter assez d'observations
        # pour être mesurée et trop peu de reculs hebdomadaires retombant dans
        # l'historique pour que le ratio soit stable — c'est le cas dès que
        # l'activité récente se raréfie.
        if r["n_relmae"] < MIN_POINTS_RELMAE:
            _annoter("notice", f"[{r['modele']}] RelMAE {relmae:.3f} calcule sur "
                               f"{r['n_relmae']} point(s) de comparaison, minimum "
                               f"{MIN_POINTS_RELMAE} : effectif insuffisant, seuil non "
                               f"applique. Mesure a reconduire au prochain cycle.")
            continue

        if est_global:
            global_evalue = True

        if relmae >= SEUIL_ERREUR:
            message = (f"[{r['modele']}] RelMAE {relmae:.3f} >= {SEUIL_ERREUR} : le modele "
                       f"ne fait plus mieux qu une prevision naive. Reentrainement a inspecter.")
            if est_global:
                _annoter("error", message)
                en_echec = True
            else:
                _annoter("warning", message)
        elif relmae >= SEUIL_ALERTE:
            _annoter("warning", f"[{r['modele']}] RelMAE {relmae:.3f} au-dela du seuil d alerte "
                                f"{SEUIL_ALERTE} : marge en reduction face a la prevision naive.")

    if en_echec:
        return 1

    # Ne pas confondre « pas de dérive » et « pas de mesure » : annoncer le
    # premier quand le modèle global n'a pas pu être évalué donnerait une
    # assurance que le cycle n'a pas produite.
    if global_evalue:
        print("Aucune derive detectee sur le modele global.")
    else:
        print("Modele global non evalue sur ce cycle : effectif de comparaison insuffisant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
