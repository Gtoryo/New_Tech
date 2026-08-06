"""
commandes.py — Endpoint POST /api/v1/commandes/
Crée une nouvelle commande dans schema_analytics (transaction atomique).
Concentre la logique métier de la saisie côté serveur : upsert client,
upsert employé, résolution du service, insertion facture + ligne_facture.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from api.auth import verifier_cle_api
from api.database import get_engine
from api.schemas import CommandeIn, CommandeOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commandes", tags=["Commandes"])


def _generer_facture_id(annee: int) -> str:
    return f"FAC-{annee}-{uuid.uuid4().hex[:8].upper()}"


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
            # Un SELECT suivi d'un INSERT laisserait une fenêtre entre les deux
            # requêtes : deux commandes concurrentes pour un client inconnu
            # créeraient deux lignes. ON CONFLICT rend l'opération atomique, en
            # s'appuyant sur l'index unique ux_client_nom_lower.
            # La casse enregistrée n'est pas écrasée : la première forme vue est
            # conservée, comme dans src/transform.py. Seul le téléphone est mis
            # à jour, et uniquement si la saisie en fournit un.
            id_client = conn.execute(
                text("""
                    INSERT INTO schema_analytics.client AS c (nom_client, telephone)
                    VALUES (:nom, :tel)
                    ON CONFLICT (LOWER(nom_client)) DO UPDATE
                        SET telephone = COALESCE(EXCLUDED.telephone, c.telephone)
                    RETURNING c.id_client
                """),
                {"nom": commande.client, "tel": commande.telephone or None},
            ).fetchone()[0]

            # ── Upsert employé ────────────────────────────────────────────────
            # DO UPDATE plutôt que DO NOTHING : ce dernier ne renvoie aucune
            # ligne en cas de conflit, donc RETURNING serait vide. La mise à
            # jour est volontairement neutre.
            id_employe = conn.execute(
                text("""
                    INSERT INTO schema_analytics.employe AS e (nom_employe)
                    VALUES (:nom)
                    ON CONFLICT (LOWER(nom_employe)) DO UPDATE
                        SET nom_employe = e.nom_employe
                    RETURNING e.id_employe
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
        # Le détail technique part dans les logs serveur, jamais dans la réponse
        # HTTP : un message SQLAlchemy expose le schéma, les tables, la requête
        # et parfois l'hôte de la base (OWASP API8:2023 — Security Misconfiguration).
        logger.exception("Echec d'enregistrement de la commande %s", facture_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Enregistrement impossible. L'incident a été journalisé.",
        ) from exc

    return CommandeOut(facture_id=facture_id, total=total)
