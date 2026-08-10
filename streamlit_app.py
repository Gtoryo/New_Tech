"""
streamlit_app.py — Point d'entrée unique de l'application Streamlit PME Multiservice.
Gère l'initialisation, l'authentification et le routage par rôle.
Convention Streamlit Cloud : ce fichier doit s'appeler streamlit_app.py.
"""

import streamlit as st
import streamlit.components.v1 as components

from app.dashboard import afficher_dashboard
from app.login import afficher_login
from app.saisie import afficher_saisie

# ── Configuration globale (doit être le 1er appel Streamlit) ──────────────────
st.set_page_config(
    page_title="Tableau de bord IA — Pôle Imprimerie & Sérigraphie",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Accessibilité — attribut lang de la page (RGAA 8.3) ──────────────────────
# st.markdown() n'exécute PAS le JavaScript qu'on lui passe : Streamlit insère
# le fragment via innerHTML, et un navigateur n'exécute jamais un <script>
# inséré de cette façon. L'attribut lang restait donc absent malgré le code.
# st.components.v1.html(), lui, crée une véritable iframe dont le script
# s'exécute ; on remonte au document parent pour y poser l'attribut.
components.html(
    "<script>window.parent.document.documentElement.lang = 'fr';</script>",
    height=0,
)

# ── Accessibilité — indicateurs de focus (WCAG 2.4.7 / RGAA) ─────────────────
# Le CSS, lui, s'applique bien par cette voie : une balise <style> insérée dans
# le DOM est prise en compte par le navigateur, contrairement à <script>.
st.markdown("""
<style>
/* WCAG 2.4.7 — Focus visible sur tous les éléments interactifs */
button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[role="button"]:focus-visible,
[tabindex]:focus-visible {
    outline: 3px solid #0066CC !important;
    outline-offset: 2px !important;
}
/* Amélioration du contraste des captions (WCAG 1.4.3) */
.stCaption { color: #444444 !important; }
</style>
""", unsafe_allow_html=True)

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
