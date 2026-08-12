"""
schemas.py — Modèles Pydantic de l'API (contrats d'entrée/sortie).
Chaque modèle constitue une documentation auto-générée via /docs (OpenAPI).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Commandes
# ─────────────────────────────────────────────────────────────────────────────

class CommandeIn(BaseModel):
    # Les longueurs maximales reprennent exactement les bornes VARCHAR de
    # schema_analytics (sql/02_tables.sql). Sans elles, une saisie trop longue
    # traverse la validation, part en base, et PostgreSQL la rejette en
    # StringDataRightTruncation — que le gestionnaire d'exception de
    # api/routes/commandes.py convertit en 500 générique. La Gestionnaire perd
    # alors sa saisie sans savoir quel champ corriger. Avec la borne, le rejet
    # se produit ici, en 422, en nommant le champ fautif.
    client: str = Field(..., min_length=1, max_length=150,
                        description="Nom du client ou de l'entreprise")
    telephone: str = Field(default="", max_length=20,
                           description="Numéro de téléphone (optionnel)")
    date_facture: date = Field(default_factory=date.today, description="Date de la commande")
    service: Literal["Imprimerie", "Sérigraphie", "Maintenance", "Vidéosurveillance"] = Field(
        ..., description="Pôle d'activité"
    )
    employe: str = Field(..., min_length=1, max_length=150,
                         description="Nom de l'employé en charge")
    statut_paiement: Literal["Non payé", "Payé", "Partiel"] = Field(
        default="Non payé", description="Statut du règlement"
    )
    description: str = Field(..., min_length=1, max_length=255,
                             description="Description de la prestation")
    quantite: int = Field(..., ge=1, description="Nombre d'unités")
    # Entier et non flottant : le FCFA n'a pas de subdivision en usage, et les
    # colonnes prix_unitaire / total_ligne sont des INTEGER. Accepter un flottant
    # laissait PostgreSQL arrondir silencieusement à l'insertion ; un rejet
    # explicite en 422 vaut mieux qu'une donnée corrigée sans trace.
    prix_unitaire: int = Field(..., gt=0, description="Prix unitaire en FCFA (entier)")

    model_config = {"json_schema_extra": {"example": {
        "client": "Mairie de Brazzaville",
        "telephone": "+242 06 000 00 00",
        "date_facture": "2026-06-15",
        "service": "Imprimerie",
        "employe": "Jean Moukassa",
        "statut_paiement": "Payé",
        "description": "Impression flyers A5 recto-verso, 1 000 exemplaires",
        "quantite": 1000,
        "prix_unitaire": 150,
    }}}


class CommandeOut(BaseModel):
    facture_id: str = Field(..., description="Référence générée automatiquement")
    total: int = Field(..., description="Montant total calculé (FCFA)")


# ─────────────────────────────────────────────────────────────────────────────
# Prévisions
# ─────────────────────────────────────────────────────────────────────────────

class PrevisionPoint(BaseModel):
    ds: date = Field(..., description="Date de prévision")
    yhat: float = Field(..., description="Prévision centrale (FCFA)")
    yhat_lower: float = Field(..., description="Borne basse de l'intervalle à 80 %")
    yhat_upper: float = Field(..., description="Borne haute de l'intervalle à 80 %")


# ─────────────────────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────────────────────

class KpiOut(BaseModel):
    ca_total: int = Field(..., description="Chiffre d'affaires total historique (FCFA)")
    nb_commandes: int = Field(..., description="Nombre total de commandes")
    ca_moyen_jour: int = Field(..., description="CA moyen journalier (FCFA)")
    top_service: str = Field(..., description="Pôle d'activité générant le plus de CA")
