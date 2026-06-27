"""
dashboard.py — Tableau de Bord Direction
Page Streamlit : KPIs, historique CA mensuel, répartition par service,
et courbe de prévision Prophet avec intervalle de confiance.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

from model.predict import predire

load_dotenv(ROOT / "variable.env")

# ─────────────────────────────────────────────────────────────────────────────
# PALETTE COULEURS ET MOTIFS PAR SERVICE
# WCAG 1.4.1 — la couleur n'est pas le seul moyen de distinction
# ─────────────────────────────────────────────────────────────────────────────

COULEURS = {
    "Imprimerie":        "#3498DB",
    "Sérigraphie":       "#E74C3C",
    "Maintenance":       "#27AE60",
    "Vidéosurveillance": "#8E44AD",
    "global":            "#F39C12",
}

# Motifs de hachure Plotly (complément visuel à la couleur)
PATTERNS = {
    "Imprimerie":        "",
    "Sérigraphie":       "/",
    "Maintenance":       "\\",
    "Vidéosurveillance": "x",
    "global":            "",
}


def _hex_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convertit un code couleur #RRGGBB en chaîne rgba() pour Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _fmt(valeur: int) -> str:
    """Formate un entier avec des espaces comme séparateur de milliers."""
    return f"{valeur:,}".replace(",", " ")


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION & CACHE
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


@st.cache_data(ttl=3600)
def _serie_globale() -> pd.DataFrame:
    with _moteur().connect() as conn:
        df = pd.read_sql(
            "SELECT ds, y, nb_commandes "
            "FROM schema_ia.serie_ventes_journalieres ORDER BY ds",
            conn,
        )
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"])
    return df


@st.cache_data(ttl=3600)
def _serie_par_service() -> pd.DataFrame:
    with _moteur().connect() as conn:
        df = pd.read_sql(
            "SELECT ds, service, y, nb_commandes "
            "FROM schema_ia.serie_ventes_par_service ORDER BY ds",
            conn,
        )
    df["ds"] = pd.to_datetime(df["ds"])
    df["y"]  = pd.to_numeric(df["y"])
    return df


@st.cache_data(ttl=3600)
def _previsions(service: str, horizon: int) -> pd.DataFrame:
    return predire(service, horizon)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────

def afficher_dashboard() -> None:
    """Affiche le tableau de bord complet réservé à la Direction."""

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ Paramètres")
        st.divider()

        service_choisi = st.selectbox(
            "Pôle d'activité (prévision)",
            options=["global", "Imprimerie", "Sérigraphie", "Maintenance", "Vidéosurveillance"],
            help="Sélectionnez le pôle d'activité pour lequel afficher les prévisions Prophet.",
        )

        horizon = st.select_slider(
            "Horizon de prévision",
            options=[30, 60, 90, 120, 180],
            value=90,
            format_func=lambda x: f"{x} jours",
            help="Nombre de jours futurs à afficher sur la courbe de prévision (maximum 180 jours).",
        )

        st.divider()
        st.caption("🗄️ Source : Supabase / schema_ia")
        st.caption("🤖 Modèle : Prophet 1.1.6")

    # ── Chargement des données ────────────────────────────────────────────────
    df_global   = _serie_globale()
    df_services = _serie_par_service()
    df_prev     = _previsions(service_choisi, horizon)

    # ── En-tête ───────────────────────────────────────────────────────────────
    st.title("📊 Tableau de Bord — Direction")
    st.caption(
        f"Pôle Imprimerie & Sérigraphie  •  "
        f"Dernière donnée : **{df_global['ds'].max().strftime('%d/%m/%Y')}**"
    )
    st.divider()

    # ── Section 1 — KPI Cards ─────────────────────────────────────────────────
    ca_total     = int(df_global["y"].sum())
    nb_commandes = int(df_global["nb_commandes"].sum())
    ca_moyen     = int(df_global["y"].mean())
    top_service  = df_services.groupby("service")["y"].sum().idxmax()

    try:
        derniers_30 = df_global.sort_values("ds").tail(30)["y"].sum()
        avant_30    = df_global.sort_values("ds").iloc[-60:-30]["y"].sum()
        delta_ca    = f"{((derniers_30 - avant_30) / avant_30 * 100):+.1f} % vs mois préc."
    except Exception:
        delta_ca = None

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 CA Total historique", f"{_fmt(ca_total)} FCFA")
    with col2:
        st.metric("📦 Commandes totales", _fmt(nb_commandes))
    with col3:
        st.metric("📈 CA Moyen / Jour", f"{_fmt(ca_moyen)} FCFA", delta=delta_ca)
    with col4:
        st.metric("🏆 Pôle Leader", top_service)

    st.divider()

    # ── Section 2 — CA mensuel par service (barres empilées) ─────────────────
    st.subheader("📅 Évolution mensuelle du CA par pôle d'activité")

    df_mensuel = df_services.copy()
    df_mensuel["mois"] = df_mensuel["ds"].dt.to_period("M").dt.to_timestamp()
    df_mensuel = (
        df_mensuel.groupby(["mois", "service"])["y"]
        .sum()
        .reset_index()
        .rename(columns={"y": "ca_total"})
    )

    fig_bar = px.bar(
        df_mensuel,
        x="mois", y="ca_total", color="service",
        color_discrete_map=COULEURS,
        # WCAG 1.4.1 — motifs de hachure en complément de la couleur
        pattern_shape="service",
        pattern_shape_map=PATTERNS,
        labels={"mois": "Mois", "ca_total": "CA (FCFA)", "service": "Pôle d'activité"},
        barmode="stack", template="plotly_white",
    )
    fig_bar.update_traces(
        hovertemplate="<b>%{data.name}</b><br>Mois : %{x|%B %Y}<br>CA : %{y:,.0f} FCFA<extra></extra>",
    )
    fig_bar.update_layout(
        title_text="Chiffre d'affaires mensuel empilé par pôle d'activité",
        title_font_size=1,  # masqué visuellement, présent pour les lecteurs d'écran
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=10, b=10), height=380,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # WCAG 1.1.1 — alternative textuelle au graphique
    with st.expander("📋 Données — Évolution mensuelle du CA (tableau)"):
        st.caption("Tableau de données correspondant au graphique ci-dessus.")
        df_display = df_mensuel.copy()
        df_display["mois"] = df_display["mois"].dt.strftime("%B %Y")
        df_display["ca_total"] = df_display["ca_total"].apply(lambda x: f"{int(x):,} FCFA".replace(",", " "))
        st.dataframe(
            df_display.rename(columns={"mois": "Mois", "service": "Pôle", "ca_total": "CA"}),
            use_container_width=True, hide_index=True,
        )

    # ── Section 3 — Donut + Barres horizontales ───────────────────────────────
    col_donut, col_top = st.columns(2)

    with col_donut:
        st.subheader("🥧 Répartition du CA par pôle")
        ca_par_service = df_services.groupby("service")["y"].sum().reset_index()
        fig_donut = px.pie(
            ca_par_service, values="y", names="service",
            color="service", color_discrete_map=COULEURS,
            hole=0.45, template="plotly_white",
        )
        # WCAG 1.4.1 — libellé + pourcentage sur chaque secteur (pas seulement couleur)
        fig_donut.update_traces(
            textinfo="percent+label",
            textfont_size=13,
            hovertemplate="<b>%{label}</b><br>CA : %{value:,.0f} FCFA<br>Part : %{percent}<extra></extra>",
        )
        fig_donut.update_layout(
            title_text="Répartition du chiffre d'affaires total par pôle d'activité",
            title_font_size=1,
            showlegend=True,
            margin=dict(t=10, b=10), height=320,
        )
        st.plotly_chart(fig_donut, use_container_width=True)
        # WCAG 1.1.1 — alternative textuelle
        with st.expander("📋 Données — Répartition du CA (tableau)"):
            df_donut_display = ca_par_service.copy()
            df_donut_display["part"] = (df_donut_display["y"] / df_donut_display["y"].sum() * 100).round(1)
            df_donut_display["y"] = df_donut_display["y"].apply(lambda x: f"{int(x):,} FCFA".replace(",", " "))
            st.dataframe(
                df_donut_display.rename(columns={"service": "Pôle", "y": "CA Total", "part": "Part (%)"}),
                use_container_width=True, hide_index=True,
            )

    with col_top:
        st.subheader("🏅 CA total par pôle d'activité")
        df_top = (
            df_services.groupby("service")["y"]
            .sum().sort_values(ascending=True).reset_index()
        )
        fig_hbar = px.bar(
            df_top, x="y", y="service", color="service",
            color_discrete_map=COULEURS, orientation="h",
            # WCAG 1.4.1 — motifs en complément de la couleur
            pattern_shape="service",
            pattern_shape_map=PATTERNS,
            labels={"y": "CA Total (FCFA)", "service": ""},
            template="plotly_white", text_auto=".3s",
        )
        fig_hbar.update_traces(
            hovertemplate="<b>%{y}</b><br>CA total : %{x:,.0f} FCFA<extra></extra>",
        )
        fig_hbar.update_layout(
            title_text="Classement des pôles d'activité par chiffre d'affaires total",
            title_font_size=1,
            showlegend=False, margin=dict(t=10, b=10), height=320,
        )
        st.plotly_chart(fig_hbar, use_container_width=True)

    st.divider()

    # ── Section 4 — Prévision Prophet ─────────────────────────────────────────
    couleur = COULEURS.get(service_choisi, "#3498DB")
    st.subheader(f"🔮 Prévision Prophet — {service_choisi.capitalize()} — {horizon} jours")

    if service_choisi == "global":
        df_hist = df_global[["ds", "y"]].copy()
    else:
        df_hist = df_services[df_services["service"] == service_choisi][["ds", "y"]].copy()

    date_limite  = df_hist["ds"].max() - pd.Timedelta(days=180)
    df_hist_6m   = df_hist[df_hist["ds"] >= date_limite].copy()
    df_hist_6m["mois"] = df_hist_6m["ds"].dt.to_period("M").dt.to_timestamp()
    df_hist_mois = df_hist_6m.groupby("mois")["y"].sum().reset_index()

    fig_prev = go.Figure()
    fig_prev.add_trace(go.Bar(
        x=df_hist_mois["mois"], y=df_hist_mois["y"],
        name="Historique (mensuel)", marker_color=couleur, opacity=0.55,
        hovertemplate="Historique<br>Mois : %{x|%B %Y}<br>CA : %{y:,.0f} FCFA<extra></extra>",
    ))
    fig_prev.add_trace(go.Scatter(
        x=list(df_prev["ds"]) + list(df_prev["ds"])[::-1],
        y=list(df_prev["yhat_upper"]) + list(df_prev["yhat_lower"])[::-1],
        fill="toself", fillcolor=_hex_rgba(couleur, 0.18),
        line=dict(color="rgba(0,0,0,0)"),
        name="Intervalle de confiance (80 %)", hoverinfo="skip",
    ))
    fig_prev.add_trace(go.Scatter(
        x=df_prev["ds"], y=df_prev["yhat"],
        name="Prévision centrale (yhat)",
        line=dict(color=couleur, width=2.5, dash="dash"), mode="lines",
        hovertemplate="Date : %{x|%d/%m/%Y}<br>Prévision : %{y:,.0f} FCFA<extra></extra>",
    ))
    fig_prev.update_layout(
        title_text=f"Prévision Prophet — {service_choisi} — horizon {horizon} jours",
        title_font_size=1,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="Date", yaxis_title="CA (FCFA)",
        margin=dict(t=10, b=10), height=420,
    )
    st.plotly_chart(fig_prev, use_container_width=True)

    st.caption(
        f"Prévision centrale : **{_fmt(int(df_prev['yhat'].mean()))} FCFA/jour** en moyenne  •  "
        f"Seuil stock recommandé : **{_fmt(int(df_prev['yhat_upper'].max()))} FCFA/jour** (borne haute)"
    )

    # WCAG 1.1.1 — alternative textuelle au graphique de prévision
    with st.expander("📋 Données — Prévisions Prophet (tableau)"):
        st.caption(
            "Tableau des prévisions journalières avec intervalle de confiance à 80 %. "
            "Toutes les valeurs sont en FCFA."
        )
        df_prev_display = df_prev[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        df_prev_display["ds"] = df_prev_display["ds"].dt.strftime("%d/%m/%Y")
        df_prev_display = df_prev_display.rename(columns={
            "ds": "Date",
            "yhat": "Prévision (FCFA)",
            "yhat_lower": "Borne basse (FCFA)",
            "yhat_upper": "Borne haute (FCFA)",
        })
        st.dataframe(df_prev_display, use_container_width=True, hide_index=True)
