"""
streamlit_app.py — Point d'entrée unique de l'application Streamlit PME Multiservice.
Gère l'initialisation, l'authentification et le routage par rôle.
Convention Streamlit Cloud : ce fichier doit s'appeler streamlit_app.py.
"""

import streamlit as st

from app.login import afficher_login
from app.dashboard import afficher_dashboard
from app.saisie import afficher_saisie

# ── Configuration globale (doit être le 1er appel Streamlit) ──────────────────
st.set_page_config(
    page_title="PME Multiservice",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Initialisation de la session (valeurs par défaut au 1er chargement) ───────
st.session_state.setdefault("connecte",    False)
st.session_state.setdefault("role",        None)
st.session_state.setdefault("identifiant", None)

# ── Barre latérale : infos utilisateur + déconnexion ─────────────────────────
if st.session_state["connecte"]:
    with st.sidebar:
        st.caption(f"👤 **{st.session_state['identifiant']}**")
        role_label = "Direction" if st.session_state["role"] == "directeur" else "Gestion"
        st.caption(f"🎭 Rôle : {role_label}")
        st.divider()
        if st.button("🚪 Se déconnecter", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# ── Routage principal ─────────────────────────────────────────────────────────
if not st.session_state["connecte"]:
    afficher_login()

elif st.session_state["role"] == "directeur":
    afficher_dashboard()

elif st.session_state["role"] == "gestionnaire":
    afficher_saisie()
