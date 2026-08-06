"""
login.py — Page d'authentification
Formulaire sécurisé : vérification bcrypt contre les secrets Streamlit.
"""

import bcrypt
import streamlit as st

# Hash leurre, de même facteur de coût que les hash réels (12). Il sert à
# vérifier un mot de passe même lorsque l'identifiant n'existe pas, afin que
# les deux cas consomment le même temps CPU. Sans lui, un retour anticipé sur
# identifiant inconnu répondrait en microsecondes là où un identifiant valide
# demande ~250 ms : l'écart suffit à énumérer les comptes au chronomètre.
_HASH_LEURRE = bcrypt.hashpw(b"leurre", bcrypt.gensalt(rounds=12))


def _verifier_credentials(identifiant: str, mot_de_passe: str) -> dict | None:
    """
    Cherche l'identifiant dans st.secrets["users"].
    Retourne {"role": ..., "identifiant": ...} si le mot de passe est correct,
    None sinon — sans laisser deviner lequel des deux champs est erroné.
    """
    utilisateurs = st.secrets.get("users", {})
    infos        = utilisateurs.get(identifiant)

    # Le hash vérifié est celui de l'utilisateur s'il existe, le leurre sinon :
    # bcrypt s'exécute dans les deux cas, pour une durée équivalente.
    hash_a_verifier = infos["hash"].encode("utf-8") if infos else _HASH_LEURRE
    mot_de_passe_ok = bcrypt.checkpw(mot_de_passe.encode("utf-8"), hash_a_verifier)

    if infos and mot_de_passe_ok:
        return {"role": infos["role"], "identifiant": identifiant}

    return None  # identifiant inconnu ou mot de passe incorrect


def afficher_login() -> None:
    """Affiche le formulaire de connexion et gère l'état de session."""

    # ── Centrage visuel ───────────────────────────────────────────────────────
    _, col, _ = st.columns([1, 2, 1])

    with col:
        st.image("https://img.icons8.com/color/96/lock.png", width=72)
        st.markdown("### Connexion — PME Multiservice")
        st.caption("Accès réservé au personnel autorisé. Les deux champs sont obligatoires.")
        st.divider()

        with st.form("form_login", clear_on_submit=False):
            identifiant = st.text_input(
                "Identifiant",
                placeholder="ex : directeur",
                help="Votre identifiant de connexion fourni par l'administrateur.",
                autocomplete="username",
            )
            mot_de_passe = st.text_input(
                "Mot de passe",
                type="password",
                placeholder="••••••••",
                help="Votre mot de passe personnel. La saisie est masquée.",
                autocomplete="current-password",
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
