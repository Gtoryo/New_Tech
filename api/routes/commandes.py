"""
commandes.py — Endpoint POST /api/v1/commandes/
Crée une nouvelle commande dans schema_analytics (transaction atomique).
Extrait la logique métier de app/saisie.py pour l'exposer via REST.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from api.auth import verifier_cle_api
from api.database import get_engine
from api.schemas import CommandeIn, CommandeOut

router = APIRouter(prefix="/commandes", tags=["Commandes"])


def _generer_facture_id(annee: int) -> str:
    return f"FAC-{annee}-{uuid.uuid4().hex[:6].upper()}"


@router.post(
    "/",
    response_model=CommandeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Enregistrer une nouvelle commande",
    description=(
        "Insère une commande complète dans schema_analytics en une transaction unique : "
        "upsert client, upsert employé, résolution du service, insertion facture + ligne_facture."
    ),
)
def creer_commande(
    commande: CommandeIn,
    _: str = Depends(verifier_cle_api),
) -> CommandeOut:
    engine = get_engine()
    facture_id = _generer_facture_id(commande.date_facture.year)
    total = commande.quantite * commande.prix_unitaire

    try:
        with engine.begin() as conn:
            # ── Upsert client (insensible à la casse) ────────────────────────
            row = conn.execute(
                text("SELECT id_client FROM schema_analytics.client WHERE LOWER(nom_client) = LOWER(:nom)"),
                {"nom": commande.client},
            ).fetchone()
            if row:
                id_client = row[0]
            else:
                id_client = conn.execute(
                    text("""
                        INSERT INTO schema_analytics.client (nom_client, telephone)
                        VALUES (:nom, :tel)
                        RETURNING id_client
                    """),
                    {"nom": commande.client, "tel": commande.telephone or None},
                ).fetchone()[0]

            # ── Upsert employé ────────────────────────────────────────────────
            row = conn.execute(
                text("SELECT id_employe FROM schema_analytics.employe WHERE LOWER(nom_employe) = LOWER(:nom)"),
                {"nom": commande.employe},
            ).fetchone()
            if row:
                id_employe = row[0]
            else:
                id_employe = conn.execute(
                    text("""
                        INSERT INTO schema_analytics.employe (nom_employe)
                        VALUES (:nom)
                        RETURNING id_employe
                    """),
                    {"nom": commande.employe},
                ).fetchone()[0]

            # ── Résolution du service ─────────────────────────────────────────
            row = conn.execute(
                text("SELECT id_service FROM schema_analytics.service WHERE libelle = :lib"),
                {"lib": commande.service},
            ).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service introuvable en base : {commande.service}",
                )
            id_service = row[0]

            # ── Insertion facture + ligne_facture (atomique) ──────────────────
            conn.execute(
                text("""
                    INSERT INTO schema_analytics.facture
                        (id_facture, date_facture, statut_paiement, id_client, id_employe)
                    VALUES
                        (:fac_id, :date, :statut, :id_client, :id_employe)
                """),
                {
                    "fac_id":     facture_id,
                    "date":       commande.date_facture,
                    "statut":     commande.statut_paiement,
                    "id_client":  id_client,
                    "id_employe": id_employe,
                },
            )
            conn.execute(
                text("""
                    INSERT INTO schema_analytics.ligne_facture
                        (description, quantite, prix_unitaire, total_ligne, id_facture, id_service)
                    VALUES
                        (:desc, :qte, :pu, :total, :fac_id, :id_service)
                """),
                {
                    "desc":       commande.description,
                    "qte":        commande.quantite,
                    "pu":         commande.prix_unitaire,
                    "total":      total,
                    "fac_id":     facture_id,
                    "id_service": id_service,
                },
            )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur base de données : {exc}",
        ) from exc

    return CommandeOut(facture_id=facture_id, total=total)
