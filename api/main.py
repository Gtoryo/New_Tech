"""
main.py — Point d'entrée de l'API REST FastAPI.
Lancement : uvicorn api.main:app --reload
Documentation interactive : http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import commandes, kpis, previsions

app = FastAPI(
    title="New Tech Services — API IA",
    description=(
        "API REST exposant les prévisions Prophet et la gestion des commandes "
        "du pôle Imprimerie & Sérigraphie. "
        "Cette couche découple la logique métier de l'interface Streamlit, "
        "permettant à toute application future (mobile, ERP) d'accéder aux mêmes services."
    ),
    version="1.0.0",
    contact={"name": "New Tech Services", "email": "contact@newtech-services.cg"},
    license_info={"name": "Propriétaire — usage interne uniquement"},
)

# ── CORS — autorise Streamlit Cloud et localhost en développement ─────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://newtech-services-interne.streamlit.app"],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(previsions.router, prefix="/api/v1")
app.include_router(commandes.router,  prefix="/api/v1")
app.include_router(kpis.router,       prefix="/api/v1")


@app.get("/health", tags=["Santé"], summary="Vérification de disponibilité")
def health() -> dict:
    """Endpoint de health-check pour les outils de supervision."""
    return {"status": "ok", "service": "New Tech Services API"}
