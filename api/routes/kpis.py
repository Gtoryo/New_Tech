"""
kpis.py — Endpoint GET /api/v1/kpis/
Agrège les indicateurs clés depuis schema_ia pour le tableau de bord.
"""

import pandas as pd
from fastapi import APIRouter, HTTPException, status

from api.database import get_engine
from api.schemas import KpiOut

router = APIRouter(prefix="/kpis", tags=["KPIs"])


@router.get(
    "/",
    response_model=KpiOut,
    summary="Obtenir les indicateurs clés de performance",
    description=(
        "Calcule en temps réel CA total, nombre de commandes, CA moyen journalier "
        "et pôle leader depuis les séries temporelles de schema_ia."
    ),
)
def obtenir_kpis() -> KpiOut:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            df_global = pd.read_sql(
                "SELECT y, nb_commandes FROM schema_ia.serie_ventes_journalieres",
                conn,
            )
            df_services = pd.read_sql(
                "SELECT service, y FROM schema_ia.serie_ventes_par_service",
                conn,
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Impossible d'accéder à la base de données : {exc}",
        ) from exc

    if df_global.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune donnée disponible. Vérifiez que le pipeline ETL a été exécuté.",
        )

    ca_total     = int(df_global["y"].sum())
    nb_commandes = int(df_global["nb_commandes"].sum())
    ca_moyen     = int(df_global["y"].mean())
    top_service  = df_services.groupby("service")["y"].sum().idxmax()

    return KpiOut(
        ca_total=ca_total,
        nb_commandes=nb_commandes,
        ca_moyen_jour=ca_moyen,
        top_service=top_service,
    )
