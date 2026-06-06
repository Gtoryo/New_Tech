"""
saisie.py — Page de saisie des commandes (Gestionnaire)
Formulaire Streamlit : insertion d'une nouvelle commande dans schema_analytics
en respectant le modèle relationnel (client → employe → service → facture → ligne_facture).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
import uuid
from datetime import date

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(ROOT / "variable.env")

# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _moteur():
    url = (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD').strip()}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}"
        f"/{os.getenv('DB_NAME')}?sslmode=require"
    )
    return create_engine(url)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS SQL (requêtes paramétrées — protection contre l'injection SQL)
# ─────────────────────────────────────────────────────────────────────────────

def _generer_facture_id(annee: int) -> str:
    """Génère un identifiant unique : FAC-YYYY-XXXXXX (6 chars hex aléatoires)."""
    return f"FAC-{annee}-{uuid.uuid4().hex[:6].upper()}"


def _obtenir_ou_creer_client(conn, nom_client: str, telephone: str) -> int:
    """
    Cherche le client par nom (insensible à la casse).
    S'il n'existe pas, l'insère et retourne son id généré.
    """
    row = conn.execute(
        text("SELECT id_client FROM schema_analytics.client WHERE LOWER(nom_client) = LOWER(:nom)"),
        {"nom": nom_client},
    ).fetchone()

    if row:
        return row[0]

    row = conn.execute(
        text("""
            INSERT INTO schema_analytics.client (nom_client, telephone)
            VALUES (:nom, :tel)
            RETURNING id_client
        """),
        {"nom": nom_client, "tel": telephone or None},
    ).fetchone()
    return row[0]


def _obtenir_ou_creer_employe(conn, nom_employe: str) -> int:
    """
    Cherche l'employé par nom (insensible à la casse).
    S'il n'existe pas, l'insère et retourne son id généré.
    """
    row = conn.execute(
        text("SELECT id_employe FROM schema_analytics.employe WHERE LOWER(nom_employe) = LOWER(:nom)"),
        {"nom": nom_employe},
    ).fetchone()

    if row:
        return row[0]

    row = conn.execute(
        text("""
            INSERT INTO schema_analytics.employe (nom_employe)
            VALUES (:nom)
            RETURNING id_employe
        """),
        {"nom": nom_employe},
    ).fetchone()
    return row[0]


def _obtenir_service(conn, libelle: str) -> int:
    """Retourne l'id_service correspondant au libellé sélectionné."""
    row = conn.execute(
        text("SELECT id_service FROM schema_analytics.service WHERE libelle = :lib"),
        {"lib": libelle},
    ).fetchone()
    if not row:
        raise ValueError(f"Service introuvable en base : {libelle}")
    return row[0]


def _inserer_commande(conn, *, facture_id, date_facture, statut_paiement,
                      id_client, id_employe, id_service,
                      description, quantite, prix_unitaire, total) -> None:
    """Insère la facture puis sa ligne — dans la même transaction ouverte."""
    conn.execute(
        text("""
            INSERT INTO schema_analytics.facture
                (id_facture, date_facture, statut_paiement, id_client, id_employe)
            VALUES
                (:fac_id, :date, :statut, :id_client, :id_employe)
        """),
        {
            "fac_id":    facture_id,
            "date":      date_facture,
            "statut":    statut_paiement,
            "id_client":  id_client,
            "id_employe": id_employe,
        },
    )
    conn.execute(
        text("""
            INSERT INTO schema_analytics.ligne_facture
                (description, quantite, prix_unitaire, total_ligne, id_facture, id_service)
            VALUES
                (:desc, :qte, :pu, :total, :fac_id, :id_service)
        """),
        {
            "desc":       description,
            "qte":        quantite,
            "pu":         prix_unitaire,
            "total":      total,
            "fac_id":     facture_id,
            "id_service": id_service,
        },
    )


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

    with st.form("form_saisie", clear_on_submit=True):

        # ── Bloc Client ───────────────────────────────────────────────────────
        st.subheader("👤 Client")
        col1, col2 = st.columns(2)
        with col1:
            client    = st.text_input("Nom du client *", placeholder="ex : Entreprise ABC")
        with col2:
            telephone = st.text_input("Téléphone", placeholder="ex : +242 06 000 00 00")

        # ── Bloc Commande ─────────────────────────────────────────────────────
        st.subheader("📦 Commande")
        col3, col4 = st.columns(2)
        with col3:
            date_cmd = st.date_input("Date *", value=date.today())
            service  = st.selectbox("Service *", options=SERVICES)
        with col4:
            employe = st.text_input("Employé en charge *", placeholder="ex : Jean Moukassa")
            statut  = st.selectbox("Statut paiement *", options=STATUTS)

        description = st.text_area(
            "Description *",
            placeholder="ex : Impression flyers A5 recto-verso, 1 000 exemplaires",
        )

        # ── Bloc Montants ─────────────────────────────────────────────────────
        st.subheader("💰 Montants")
        col5, col6, col7 = st.columns(3)
        with col5:
            quantite      = st.number_input("Quantité *", min_value=1, value=1, step=1)
        with col6:
            prix_unitaire = st.number_input("Prix Unitaire (FCFA) *", min_value=0, value=0, step=500)
        with col7:
            # Affiché en lecture seule — jamais saisi manuellement
            st.metric("Total calculé", f"{quantite * prix_unitaire:,} FCFA".replace(",", " "))

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

    # Calcul du total et génération de la référence
    total      = int(quantite) * float(prix_unitaire)
    facture_id = _generer_facture_id(date_cmd.year)

    try:
        with _moteur().begin() as conn:  # rollback automatique si exception
            id_client  = _obtenir_ou_creer_client(conn, client.strip(), telephone.strip())
            id_employe = _obtenir_ou_creer_employe(conn, employe.strip())
            id_service = _obtenir_service(conn, service)
            _inserer_commande(
                conn,
                facture_id=facture_id,
                date_facture=date_cmd,
                statut_paiement=statut,
                id_client=id_client,
                id_employe=id_employe,
                id_service=id_service,
                description=description.strip(),
                quantite=int(quantite),
                prix_unitaire=float(prix_unitaire),
                total=total,
            )

        st.success(f"Commande enregistrée — Référence : **{facture_id}**")
        st.balloons()

    except Exception as e:
        st.error(f"Erreur lors de l'enregistrement : {e}")
