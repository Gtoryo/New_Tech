"""
previsions.py — Endpoint GET /api/v1/previsions/{service}
Lit les prévisions Prophet pré-calculées depuis schema_ia.previsions_prophet.
Aucune dépendance à Prophet à l'exécution : simple SELECT SQL.
"""

from typing import List, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from api.database import get_engine
from api.schemas import PrevisionPoint

router = APIRouter(prefix="/previsions", tags=["Prévisions"])

ServiceType = Literal["global", "Imprimerie", "Sérigraphie", "Maintenance", "Vidéosurveillance"]


@router.get(
    "/{service}",
    response_model=List[PrevisionPoint],
    summary="Obtenir les prévisions Prophet pour un pôle d'activité",
    description=(
        "Retourne jusqu'à `horizon` points de prévision journaliers. "
        "Les valeurs sont pré-calculées lors du réentraînement mensuel "
        "(GitHub Actions) et stockées dans schema_ia.previsions_prophet."
    ),
)
def obtenir_previsions(
    service: ServiceType,
    horizon: int = Query(default=90, ge=1, le=180, description="Nombre de jours futurs (max 180)"),
) -> List[PrevisionPoint]:
    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            """
            SELECT ds, yhat, yhat_lower, yhat_upper
            FROM schema_ia.previsions_prophet
            WHERE service = %(service)s
            ORDER BY ds
            LIMIT %(horizon)s
            """,
            conn,
            params={"service": service, "horizon": horizon},
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucune prévision disponible pour le service '{service}'. "
                   "Vérifiez que le réentraînement mensuel a été exécuté.",
        )

    df["ds"] = pd.to_datetime(df["ds"]).dt.date
    return df.to_dict(orient="records")
