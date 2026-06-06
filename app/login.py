"""
login.py — Page d'authentification
Formulaire sécurisé : vérification bcrypt contre les secrets Streamlit.
"""

import bcrypt
import streamlit as st


def _verifier_credentials(identifiant: str, mot_de_passe: str) -> dict | None:
    """
    Cherche l'identifiant dans st.secrets["users"].
    Retourne {"role": ..., "identifiant": ...} si le mot de passe est correct,
    None sinon.
    """
    utilisateurs = st.secrets.get("users", {})

    if identifiant not in utilisateurs:
        return None  # identifiant inconnu

    infos        = utilisateurs[identifiant]
    hash_stocke  = infos["hash"].encode("utf-8")
    mdp_encode   = mot_de_passe.encode("utf-8")

    if bcrypt.checkpw(mdp_encode, hash_stocke):
        return {"role": infos["role"], "identifiant": identifiant}

    return None  # mot de passe incorrect


def afficher_login() -> None:
    """Affiche le formulaire de connexion et gère l'état de session."""

    # ── Centrage visuel ───────────────────────────────────────────────────────
    _, col, _ = st.columns([1, 2, 1])

    with col:
        st.image("https://img.icons8.com/color/96/lock.png", width=72)
        st.markdown("### Connexion — PME Multiservice")
        st.caption("Accès réservé au personnel autorisé")
        st.divider()

        with st.form("form_login", clear_on_submit=False):
            identifiant  = st.text_input("Identifiant", placeholder="ex : directeur")
            mot_de_passe = st.text_input(
                "Mot de passe", type="password", placeholder="••••••••"
            )
            soumettre = st.form_submit_button("Se connecter", use_container_width=True)

        # ── Traitement après soumission ───────────────────────────────────────
        if soumettre:
            if not identifiant or not mot_de_passe:
                st.warning("Veuillez remplir tous les champs.")
                return

            utilisateur = _verifier_credentials(identifiant, mot_de_passe)

            if utilisateur:
                st.session_state["connecte"]    = True
                st.session_state["role"]        = utilisateur["role"]
                st.session_state["identifiant"] = utilisateur["identifiant"]
                st.rerun()  # recharge main.py qui lit session_state et route
            else:
                st.error("Identifiant ou mot de passe incorrect.")
