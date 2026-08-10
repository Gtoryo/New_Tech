"""
test_dashboard.py — Tests unitaires de l'agrégation mensuelle des prévisions.

Ces tests couvrent la reconstruction de l'intervalle de prédiction à la maille
mensuelle, seule opération statistique du tableau de bord. Elle mérite un test
dédié : la version initiale sommait les bornes journalières, ce qui suppose des
erreurs journalières parfaitement corrélées et élargissait l'intervalle d'un
facteur ~√30 sur un mois plein. Le défaut n'était pas visible parce que le
calcul vivait au milieu du code de rendu, donc hors de portée de tout test.

Aucune infrastructure requise : la fonction testée est pure.
"""

import numpy as np
import pandas as pd
import pytest

from app.dashboard import agreger_previsions_au_mois


def _previsions(n_jours: int, yhat: float = 100.0, demi: float = 30.0,
                debut: str = "2026-09-01") -> pd.DataFrame:
    """Série de prévisions journalières à demi-largeur d'intervalle constante."""
    dates = pd.date_range(debut, periods=n_jours, freq="D")
    return pd.DataFrame({
        "ds": dates,
        "yhat": [yhat] * n_jours,
        "yhat_lower": [yhat - demi] * n_jours,
        "yhat_upper": [yhat + demi] * n_jours,
    })


class TestPrevisionCentrale:

    def test_la_prevision_centrale_est_bien_la_somme_du_mois(self):
        # L'espérance d'une somme est la somme des espérances : yhat s'additionne.
        df = agreger_previsions_au_mois(_previsions(30, yhat=100.0))
        assert df["yhat"].iloc[0] == 3000.0

    def test_une_seule_ligne_par_mois(self):
        df = agreger_previsions_au_mois(_previsions(90))
        assert len(df) == df["mois"].nunique() == 3


class TestIntervalleMensuel:

    def test_la_demi_largeur_croit_en_racine_de_n_et_non_lineairement(self):
        # 30 jours à ±30 : la demi-largeur mensuelle attendue est 30 × √30 ≈ 164,
        # et surtout PAS 30 × 30 = 900, qui serait la somme des bornes.
        df = agreger_previsions_au_mois(_previsions(30, yhat=100.0, demi=30.0))
        demi_obtenue = (df["yhat_upper"].iloc[0] - df["yhat_lower"].iloc[0]) / 2
        assert demi_obtenue == pytest.approx(30.0 * np.sqrt(30))

    def test_l_intervalle_n_est_pas_la_somme_des_bornes(self):
        # Test de non-régression explicite sur le défaut corrigé : la somme des
        # bornes journalières produirait 900 de demi-largeur.
        df = agreger_previsions_au_mois(_previsions(30, yhat=100.0, demi=30.0))
        demi_obtenue = (df["yhat_upper"].iloc[0] - df["yhat_lower"].iloc[0]) / 2
        somme_naive = 30.0 * 30
        assert demi_obtenue < somme_naive / 5

    def test_l_intervalle_reste_centre_sur_la_prevision(self):
        df = agreger_previsions_au_mois(_previsions(30, yhat=1000.0, demi=200.0))
        centre = (df["yhat_upper"].iloc[0] + df["yhat_lower"].iloc[0]) / 2
        assert centre == pytest.approx(df["yhat"].iloc[0])

    def test_borne_basse_ecretee_a_zero(self):
        # Un chiffre d'affaires ne peut pas être négatif : même règle que
        # l'écrêtage appliqué aux prévisions journalières dans model/train.py.
        df = agreger_previsions_au_mois(_previsions(30, yhat=10.0, demi=500.0))
        assert (df["yhat_lower"] >= 0).all()


class TestMoisPartiels:

    def test_mois_partiel_en_bord_d_horizon_ecarte(self):
        # 40 jours à partir du 1er septembre : septembre est plein (30 jours),
        # octobre n'en compte que 10 et produirait une barre trompeuse.
        df = agreger_previsions_au_mois(_previsions(40))
        assert len(df) == 1
        assert df["mois"].iloc[0] == pd.Timestamp("2026-09-01")

    def test_filtre_leve_si_aucun_mois_plein(self):
        # Sur un horizon de 10 jours, tout filtrer laisserait le graphique vide :
        # mieux vaut afficher le mois partiel que rien.
        df = agreger_previsions_au_mois(_previsions(10))
        assert len(df) == 1
        assert df["n_jours"].iloc[0] == 10
