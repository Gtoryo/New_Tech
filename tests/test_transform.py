"""
test_transform.py — Tests unitaires de la couche ETL (src/transform.py)
Couverture : parsing de dates, normalisation des libellés, dédoublonnage.
Aucune connexion base de données requise.
"""

import pytest
import pandas as pd
from src.transform import (
    _parser_date,
    _normaliser_service,
    _normaliser_ville,
    transformer_ventes,
)


# ─────────────────────────────────────────────────────────────────────────────
# _parser_date
# ─────────────────────────────────────────────────────────────────────────────

class TestParserDate:

    def test_format_slash_congolais(self):
        r = _parser_date("15/06/2024")
        assert r.day == 15 and r.month == 6 and r.year == 2024

    def test_format_iso(self):
        r = _parser_date("2024-06-15")
        assert r.year == 2024 and r.month == 6 and r.day == 15

    def test_format_tirets(self):
        r = _parser_date("15-06-2024")
        assert r.day == 15 and r.month == 6

    def test_format_texte_libre(self):
        r = _parser_date("Début Juin 2024")
        assert r.month == 6 and r.year == 2024 and r.day == 1

    def test_valeur_none_retourne_none(self):
        assert _parser_date(None) is None

    def test_valeur_nan_retourne_none(self):
        assert _parser_date(float("nan")) is None

    def test_texte_invalide_retourne_none(self):
        assert _parser_date("pas une date") is None


# ─────────────────────────────────────────────────────────────────────────────
# _normaliser_service
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliserService:

    def test_serigraphie_cible(self):
        assert _normaliser_service("sérigraphie") == "Sérigraphie"

    def test_serigraphie_faute_frappe(self):
        assert _normaliser_service("sérigrpahie") == "Sérigraphie"

    def test_imprimerie_cible(self):
        assert _normaliser_service("imprimerie") == "Imprimerie"

    def test_imprimerie_faute_frappe(self):
        assert _normaliser_service("imprimrie") == "Imprimerie"

    def test_maintenance_cible(self):
        assert _normaliser_service("maintenance") == "Maintenance"

    def test_maintenance_faute_frappe(self):
        assert _normaliser_service("maintenace") == "Maintenance"

    def test_videosurveillance(self):
        assert _normaliser_service("vidéosurveillance") == "Vidéosurveillance"

    def test_valeur_nulle_retourne_none(self):
        assert _normaliser_service(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# _normaliser_ville
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliserVille:

    def test_variante_espaces(self):
        assert _normaliser_ville("pointe noire") == "Pointe-Noire"

    def test_variante_abreviation(self):
        assert _normaliser_ville("pn") == "Pointe-Noire"

    def test_variante_pte_noire(self):
        assert _normaliser_ville("pte-noire") == "Pointe-Noire"

    def test_autre_ville_inchangee(self):
        assert _normaliser_ville("Brazzaville") == "Brazzaville"

    def test_valeur_nulle_retourne_none(self):
        assert _normaliser_ville(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# transformer_ventes
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformerVentes:

    @pytest.fixture
    def df_ventes_minimal(self):
        return pd.DataFrame({
            "Date":              ["15/06/2024", "16/06/2024", "16/06/2024"],
            "Client":            ["Client A",   "Client B",   "Client B"],
            "Telephone":         ["0600000001", "0600000002", "0600000002"],
            "Service_Type":      ["imprimerie", "sérigraphie","sérigraphie"],
            "Employe_En_Charge": ["Alice",      "Bob",        "Bob"],
            "Facture_ID":        ["F001",       "F002",       "F002"],
            "Prix_Unitaire":     [5000,         3000,         3000],
            "Quantite":          [2,            1,            1],
            "Total":             [10000,        3000,         3000],
            "Statut_Paiement":   ["Payé",       "En attente", "En attente"],
            "Description":       ["Flyers A5",  "T-shirt",    "T-shirt"],
        })

    def test_cles_retournees(self, df_ventes_minimal):
        result = transformer_ventes(df_ventes_minimal)
        assert set(result.keys()) == {"clients", "employes", "factures", "lignes"}

    def test_doublon_facture_supprime(self, df_ventes_minimal):
        result = transformer_ventes(df_ventes_minimal)
        assert len(result["factures"]) == 2  # F002 dédoublonné

    def test_services_normalises(self, df_ventes_minimal):
        result = transformer_ventes(df_ventes_minimal)
        services = result["lignes"]["service_libelle"].unique()
        assert "Imprimerie" in services
        assert "Sérigraphie" in services

    def test_colonnes_factures(self, df_ventes_minimal):
        result = transformer_ventes(df_ventes_minimal)
        for col in ["facture_id", "date_facture", "statut_paiement"]:
            assert col in result["factures"].columns

    def test_colonnes_lignes(self, df_ventes_minimal):
        result = transformer_ventes(df_ventes_minimal)
        for col in ["facture_id", "quantite", "prix_unitaire", "total_ligne"]:
            assert col in result["lignes"].columns
