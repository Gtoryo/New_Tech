"""
kpis.py — Endpoint GET /api/v1/kpis/
Agrège les indicateurs clés via SQL direct depuis schema_ia.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from api.auth import verifier_cle_api
from api.database import get_engine
from api.schemas import KpiOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kpis", tags=["KPIs"])


@router.get(
    "/",
    response_model=KpiOut,
    summary="Obtenir les indicateurs clés de performance",
    description=(
        "Calcule en temps réel CA total, nombre de commandes, CA moyen journalier "
        "et pôle leader depuis les séries temporelles de schema_ia. "
        "Authentification par clé API requise (en-tête X-API-Key)."
    ),
)
def obtenir_kpis(_: str = Depends(verifier_cle_api)) -> KpiOut:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            row_global = conn.execute(text("""
                SELECT
                    SUM(y)::bigint          AS ca_total,
                    SUM(nb_commandes)::bigint AS nb_commandes,
                    AVG(y)::bigint          AS ca_moyen_jour
                FROM schema_ia.serie_ventes_journalieres
            """)).mappings().fetchone()

            row_top = conn.execute(text("""
                SELECT service
                FROM schema_ia.serie_ventes_par_service
                GROUP BY service
                ORDER BY SUM(y) DESC
                LIMIT 1
            """)).fetchone()

    except Exception as exc:
        # Détail technique en logs uniquement (cf. commentaire dans commandes.py)
        logger.exception("Echec de calcul des KPIs")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de données momentanément indisponible. Réessayez dans quelques instants.",
        ) from exc

    if not row_global or row_global["ca_total"] is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune donnée disponible. Vérifiez que le pipeline ETL a été exécuté.",
        )

    return KpiOut(
        ca_total=row_global["ca_total"],
        nb_commandes=row_global["nb_commandes"],
        ca_moyen_jour=row_global["ca_moyen_jour"],
        top_service=row_top[0] if row_top else "N/A",
    )
