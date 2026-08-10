"""
test_model.py — Tests unitaires du modèle Prophet (model/train.py)
Couverture : slugification, entraînement, structure des prévisions, horizon.
Aucune connexion base de données requise.
"""

import pandas as pd
import pytest

from model.train import _entrainer_prophet, _preparer_previsions, _slugify

# ─────────────────────────────────────────────────────────────────────────────
# _slugify
# ─────────────────────────────────────────────────────────────────────────────

class TestSlugify:

    def test_serigraphie(self):
        assert _slugify("Sérigraphie") == "serigraphie"

    def test_videosurveillance(self):
        assert _slugify("Vidéosurveillance") == "videosurveillance"

    def test_imprimerie(self):
        assert _slugify("Imprimerie") == "imprimerie"

    def test_maintenance(self):
        assert _slugify("Maintenance") == "maintenance"

    def test_espaces_remplacees_par_underscore(self):
        assert _slugify("Maintenance informatique") == "maintenance_informatique"

    def test_global_inchange(self):
        assert _slugify("global") == "global"


# ─────────────────────────────────────────────────────────────────────────────
# _entrainer_prophet
# ─────────────────────────────────────────────────────────────────────────────

class TestEntrainementProphet:

    @pytest.fixture
    def serie_90_jours(self):
        dates = pd.date_range("2023-01-01", periods=90, freq="D")
        return pd.DataFrame({"ds": dates, "y": range(1, 91)})

    def test_retourne_instance_prophet(self, serie_90_jours):
        from prophet import Prophet
        modele = _entrainer_prophet(serie_90_jours, "test")
        assert isinstance(modele, Prophet)

    def test_historique_charge(self, serie_90_jours):
        modele = _entrainer_prophet(serie_90_jours, "test")
        assert modele.history is not None
        assert len(modele.history) == 90

    def test_colonnes_previsions_presentes(self, serie_90_jours):
        modele = _entrainer_prophet(serie_90_jours, "test")
        futur = modele.make_future_dataframe(periods=30, freq="D")
        previsions = modele.predict(futur)
        for col in ["ds", "yhat", "yhat_lower", "yhat_upper"]:
            assert col in previsions.columns

    def test_horizon_180_jours(self, serie_90_jours):
        modele = _entrainer_prophet(serie_90_jours, "test")
        futur = modele.make_future_dataframe(periods=180, freq="D")
        previsions = modele.predict(futur)
        previsions_futures = previsions[previsions["ds"] > serie_90_jours["ds"].max()]
        assert len(previsions_futures) == 180

    def test_yhat_upper_superieur_a_yhat_lower(self, serie_90_jours):
        modele = _entrainer_prophet(serie_90_jours, "test")
        futur = modele.make_future_dataframe(periods=30, freq="D")
        previsions = modele.predict(futur)
        assert (previsions["yhat_upper"] >= previsions["yhat_lower"]).all()


# ─────────────────────────────────────────────────────────────────────────────
# _preparer_previsions — écrêtage à zéro et format de sortie
# ─────────────────────────────────────────────────────────────────────────────

class TestPreparerPrevisions:

    @pytest.fixture
    def serie_declinante(self):
        # Tendance fortement décroissante : extrapolée à 180 jours, Prophet
        # descend largement sous zéro. C'est le cas que l'écrêtage doit couvrir.
        dates = pd.date_range("2023-01-01", periods=120, freq="D")
        return pd.DataFrame({"ds": dates, "y": range(600, 0, -5)})

    def test_previsions_jamais_negatives(self, serie_declinante):
        modele = _entrainer_prophet(serie_declinante, "declin")
        df = _preparer_previsions(modele, "test", horizon=180)
        for colonne in ("yhat", "yhat_lower", "yhat_upper"):
            assert (df[colonne] >= 0).all(), f"{colonne} contient des valeurs négatives"

    def test_format_de_sortie(self, serie_declinante):
        modele = _entrainer_prophet(serie_declinante, "declin")
        df = _preparer_previsions(modele, "Sérigraphie", horizon=180)
        assert list(df.columns) == ["service", "ds", "yhat", "yhat_lower", "yhat_upper"]
        assert (df["service"] == "Sérigraphie").all()

    def test_horizon_et_dates_futures_uniquement(self, serie_declinante):
        modele = _entrainer_prophet(serie_declinante, "declin")
        df = _preparer_previsions(modele, "test", horizon=180)
        assert len(df) == 180                                    # horizon respecté
        assert min(df["ds"]) > modele.history["ds"].max().date()  # aucun historique reprojeté
