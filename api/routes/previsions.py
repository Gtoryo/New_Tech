"""
previsions.py — Endpoint GET /api/v1/previsions/{service}
Lit les prévisions Prophet pré-calculées depuis schema_ia.previsions_prophet.
Aucune dépendance à Prophet ni à pandas à l'exécution : simple SELECT SQL.
"""

from datetime import date
from typing import List, Literal

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
        result = conn.execute(
            text("""
                SELECT ds, yhat, yhat_lower, yhat_upper
                FROM schema_ia.previsions_prophet
                WHERE service = :service
                ORDER BY ds
                LIMIT :horizon
            """),
            {"service": service, "horizon": horizon},
        )
        rows = result.mappings().all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aucune prévision disponible pour le service '{service}'. "
                   "Vérifiez que le réentraînement mensuel a été exécuté.",
        )

    return [
        {
            "ds": row["ds"] if isinstance(row["ds"], date) else row["ds"].date(),
            "yhat": float(row["yhat"]),
            "yhat_lower": float(row["yhat_lower"]),
            "yhat_upper": float(row["yhat_upper"]),
        }
        for row in rows
    ]
