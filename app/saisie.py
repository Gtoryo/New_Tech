"""
saisie.py — Page de saisie des commandes (Gestionnaire)
Formulaire Streamlit : envoi d'une nouvelle commande via l'API REST
(POST /api/v1/commandes/). La logique métier (upsert client/employé,
transaction atomique) est déléguée à l'API.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
from datetime import date

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv(ROOT / "variable.env")

_API_URL = os.getenv("API_URL", "http://localhost:8000")
_API_KEY = os.getenv("API_SECRET_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DU FORMULAIRE
# ─────────────────────────────────────────────────────────────────────────────

SERVICES = ["Imprimerie", "Sérigraphie", "Maintenance", "Vidéosurveillance"]
STATUTS  = ["Non payé", "Payé", "Partiel"]


# ─────────────────────────────────────────────────────────────────────────────
# PAGE PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def afficher_saisie() -> None:
    """Affiche le formulaire de saisie d'une nouvelle commande."""

    st.title("📋 Saisie d'une Commande")
    st.caption("Pôle Imprimerie & Sérigraphie — Nouvelle entrée")
    st.divider()

    # WCAG 1.3.1 — identification explicite des champs obligatoires
    st.caption("Les champs marqués d'un astérisque (*) sont obligatoires.")

    with st.form("form_saisie", clear_on_submit=True):

        # ── Bloc Client ───────────────────────────────────────────────────────
        st.subheader("👤 Client")
        col1, col2 = st.columns(2)
        with col1:
            client = st.text_input(
                "Nom du client *",
                placeholder="ex : Entreprise ABC",
                help="Nom complet du client ou de l'entreprise. La recherche est insensible à la casse.",
            )
        with col2:
            telephone = st.text_input(
                "Téléphone",
                placeholder="ex : +242 06 000 00 00",
                help="Numéro de téléphone du client (optionnel).",
            )

        # ── Bloc Commande ─────────────────────────────────────────────────────
        st.subheader("📦 Commande")
        col3, col4 = st.columns(2)
        with col3:
            date_cmd = st.date_input(
                "Date *",
                value=date.today(),
                help="Date de la commande. Par défaut : date du jour.",
            )
            service = st.selectbox(
                "Service *",
                options=SERVICES,
                help="Pôle d'activité concerné par cette commande.",
            )
        with col4:
            employe = st.text_input(
                "Employé en charge *",
                placeholder="ex : Jean Moukassa",
                help="Nom de l'employé responsable de cette commande.",
            )
            statut = st.selectbox(
                "Statut paiement *",
                options=STATUTS,
                help="Indiquez si la commande a été réglée, reste à payer, ou a été partiellement payée.",
            )

        description = st.text_area(
            "Description *",
            placeholder="ex : Impression flyers A5 recto-verso, 1 000 exemplaires",
            help="Décrivez précisément la nature de la commande (produit, format, quantité, finition…).",
        )

        # ── Bloc Montants ─────────────────────────────────────────────────────
        st.subheader("💰 Montants")
        col5, col6, col7 = st.columns(3)
        with col5:
            quantite = st.number_input(
                "Quantité *",
                min_value=1, value=1, step=1,
                help="Nombre d'unités commandées.",
            )
        with col6:
            prix_unitaire = st.number_input(
                "Prix Unitaire (FCFA) *",
                min_value=0, value=0, step=500,
                help="Prix unitaire hors taxe en Francs CFA. Le total est calculé automatiquement.",
            )
        with col7:
            st.metric(
                "Total calculé",
                f"{quantite * prix_unitaire:,} FCFA".replace(",", " "),
                help="Calculé automatiquement : Quantité × Prix Unitaire.",
            )

        soumettre = st.form_submit_button("✅ Enregistrer la commande", use_container_width=True)

    # ── Traitement après soumission ───────────────────────────────────────────
    if not soumettre:
        return

    # Validation des champs obligatoires
    erreurs = []
    if not client.strip():       erreurs.append("Nom du client")
    if not employe.strip():      erreurs.append("Employé en charge")
    if not description.strip():  erreurs.append("Description")
    if prix_unitaire == 0:       erreurs.append("Prix Unitaire (ne peut pas être 0)")

    if erreurs:
        st.error(f"Champs obligatoires manquants ou invalides : **{', '.join(erreurs)}**")
        return

    # Envoi à l'API
    payload = {
        "client":           client.strip(),
        "telephone":        telephone.strip(),
        "date_facture":     date_cmd.isoformat(),
        "service":          service,
        "employe":          employe.strip(),
        "statut_paiement":  statut,
        "description":      description.strip(),
        "quantite":         int(quantite),
        "prix_unitaire":    float(prix_unitaire),
    }

    try:
        response = httpx.post(
            f"{_API_URL}/api/v1/commandes/",
            json=payload,
            headers={"X-API-Key": _API_KEY},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = exc.response.text[:200] or str(exc)
        st.error(f"Erreur API ({exc.response.status_code}) : {detail}")
        return
    except httpx.RequestError:
        st.error(
            f"API injoignable ({_API_URL}). "
            "Vérifiez que le serveur est démarré (`uvicorn api.main:app --reload`)."
        )
        return

    data = response.json()
    st.success(f"Commande enregistrée — Référence : **{data['facture_id']}**")
    st.balloons()
