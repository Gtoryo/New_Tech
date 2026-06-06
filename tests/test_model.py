"""
test_model.py — Tests unitaires du modèle Prophet (model/train.py)
Couverture : slugification, entraînement, structure des prévisions, horizon.
Aucune connexion base de données requise.
"""

import pytest
import pandas as pd
from model.train import _slugify, _entrainer_prophet


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
