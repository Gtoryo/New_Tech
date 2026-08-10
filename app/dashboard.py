"""
dashboard.py — Tableau de Bord Direction
Page Streamlit : KPIs, historique CA mensuel, répartition par service,
et courbe de prévision Prophet avec intervalle de prédiction à 80 %.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from model.predict import predire
from src.db import creer_moteur

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


def agreger_previsions_au_mois(df_prev: pd.DataFrame, jours_min: int = 20) -> pd.DataFrame:
    """
    Agrège des prévisions journalières (ds, yhat, yhat_lower, yhat_upper) au mois.

    La prévision centrale s'additionne : l'espérance d'une somme est la somme des
    espérances. Les bornes de l'intervalle, non — les sommer reviendrait à
    supposer les erreurs journalières parfaitement corrélées. C'est faux, et la
    section 4.3 du rapport le mesure : le MAPE tombe de 133 % en journalier à
    17,4 % en mensuel précisément parce que les écarts de signes opposés se
    compensent. Sous indépendance approximative, la demi-largeur d'un cumul de
    n jours croît en √n et non en n — sommer les bornes élargirait l'intervalle
    d'un facteur ~√30 ≈ 5,5 sur un mois plein, et gonflerait d'autant le seuil
    de stock lu par le Directeur.

    Les mois comptant moins de `jours_min` jours de prévision sont écartés :
    en bord d'horizon, un mois partiel produit une barre trompeuse. Le filtre
    est levé s'il ne laisserait aucune ligne.

    Fonction pure, sans dépendance à Streamlit : testable sans rendu.
    """
    df = df_prev.assign(
        mois=df_prev["ds"].dt.to_period("M").dt.to_timestamp(),
        _demi=(df_prev["yhat_upper"] - df_prev["yhat_lower"]) / 2,
    )
    agg = (
        df.groupby("mois")
        .agg(yhat=("yhat", "sum"), _demi_moyenne=("_demi", "mean"), n_jours=("ds", "size"))
        .reset_index()
    )

    pleins = agg[agg["n_jours"] >= jours_min]
    if not pleins.empty:
        agg = pleins

    demi = np.sqrt(agg["n_jours"]) * agg["_demi_moyenne"]
    # Un chiffre d'affaires ne peut pas être négatif : même écrêtage que celui
    # appliqué aux prévisions journalières dans model/train.py.
    agg["yhat_lower"] = (agg["yhat"] - demi).clip(lower=0)
    agg["yhat_upper"] = agg["yhat"] + demi
    return agg.drop(columns=["_demi_moyenne"]).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION & CACHE
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _moteur():
    """Moteur SQLAlchemy mis en cache pour toute la session Streamlit."""
    return creer_moteur()


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
            help="Nombre de jours futurs à afficher sur la courbe de prévision "
                 "(maximum 180 jours).",
        )

        st.divider()
        st.caption("🗄️ Source : Supabase / schema_ia")
        st.caption("🤖 Modèle : Prophet 1.1.6")

    # ── Chargement des données ────────────────────────────────────────────────
    # Les prévisions (appel API) sont chargées plus bas, juste avant la section 4,
    # pour ne pas bloquer l'affichage des KPI et graphiques pendant un éventuel
    # cold start de l'instance Render.
    df_global   = _serie_globale()
    df_services = _serie_par_service()

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
        hovertemplate=(
            "<b>%{data.name}</b><br>Mois : %{x|%B %Y}"
            "<br>CA : %{y:,.0f} FCFA<extra></extra>"
        ),
    )
    # Pas de titre dans la figure : le st.subheader ci-dessus est un vrai <h3>,
    # donc un point d'entrée réel pour un lecteur d'écran. Un titre Plotly réduit
    # à 1 px resterait visible à l'écran sans pour autant nommer le graphique
    # dans l'arbre d'accessibilité — l'alternative textuelle est l'expander.
    fig_bar.update_layout(
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=10, b=10), height=380,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # WCAG 1.1.1 — alternative textuelle au graphique
    with st.expander("📋 Données — Évolution mensuelle du CA (tableau)"):
        st.caption("Tableau de données correspondant au graphique ci-dessus.")
        df_display = df_mensuel.copy()
        df_display["mois"] = df_display["mois"].dt.strftime("%B %Y")
        df_display["ca_total"] = df_display["ca_total"].apply(
            lambda x: f"{int(x):,} FCFA".replace(",", " ")
        )
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
            hovertemplate=(
                "<b>%{label}</b><br>CA : %{value:,.0f} FCFA"
                "<br>Part : %{percent}<extra></extra>"
            ),
        )
        fig_donut.update_layout(
            showlegend=True,
            margin=dict(t=10, b=10), height=320,
        )
        st.plotly_chart(fig_donut, use_container_width=True)
        # WCAG 1.1.1 — alternative textuelle
        with st.expander("📋 Données — Répartition du CA (tableau)"):
            df_donut_display = ca_par_service.copy()
            df_donut_display["part"] = (
                df_donut_display["y"] / df_donut_display["y"].sum() * 100
            ).round(1)
            df_donut_display["y"] = df_donut_display["y"].apply(
                lambda x: f"{int(x):,} FCFA".replace(",", " ")
            )
            st.dataframe(
                df_donut_display.rename(
                    columns={"service": "Pôle", "y": "CA Total", "part": "Part (%)"}
                ),
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
            showlegend=False, margin=dict(t=10, b=10), height=320,
        )
        st.plotly_chart(fig_hbar, use_container_width=True)

    st.divider()

    # ── Section 4 — Prévision Prophet ─────────────────────────────────────────
    # Appel API chargé ici (et non en tête) : les sections 1 à 3 s'affichent
    # immédiatement même si l'instance Render doit se réveiller (jusqu'à ~50 s).
    df_prev = predire(service_choisi, horizon)
    if df_prev.empty:
        st.warning(
            "Prévisions momentanément indisponibles — l'API se réveille "
            "(cold start Render). Rechargez la page dans ~30 secondes."
        )
        return

    couleur = COULEURS.get(service_choisi, "#3498DB")
    st.subheader(f"🔮 Prévision Prophet — {service_choisi.capitalize()} — {horizon} jours")

    if service_choisi == "global":
        df_hist = df_global[["ds", "y"]].copy()
    else:
        df_hist = df_services[df_services["service"] == service_choisi][["ds", "y"]].copy()

    date_limite  = df_hist["ds"].max() - pd.Timedelta(days=180)
    df_hist_6m   = df_hist[df_hist["ds"] >= date_limite].copy()
    df_hist_6m["mois"] = df_hist_6m["ds"].dt.to_period("M").dt.to_timestamp()
    df_hist_mois = (
        df_hist_6m.groupby("mois")
        .agg(y=("y", "sum"), n_jours=("ds", "size"))
        .reset_index()
    )
    # On écarte les mois partiels en bord de série (barre trompeuse : un mois
    # à 3 jours d'activité paraîtrait un effondrement du chiffre d'affaires).
    df_hist_pleins = df_hist_mois[df_hist_mois["n_jours"] >= 20]
    mois_ecartes = []
    if not df_hist_pleins.empty:
        mois_ecartes = (
            df_hist_mois.loc[df_hist_mois["n_jours"] < 20, "mois"]
            .dt.strftime("%B %Y").tolist()
        )
        df_hist_mois = df_hist_pleins

    # Prévision agrégée au mois : même granularité que l'historique. Sans cela,
    # la prévision journalière (~20x plus petite qu'une somme mensuelle) est
    # écrasée sous les barres mensuelles et paraît absente du graphique.
    # La reconstruction de l'intervalle est isolée dans une fonction pure, donc
    # testable sans rendu — voir tests/test_dashboard.py.
    df_prev_mois = agreger_previsions_au_mois(df_prev)

    fig_prev = go.Figure()
    fig_prev.add_trace(go.Bar(
        x=df_hist_mois["mois"], y=df_hist_mois["y"],
        name="Historique (CA mensuel)", marker_color=couleur, opacity=0.55,
        hovertemplate="Historique<br>Mois : %{x|%B %Y}<br>CA : %{y:,.0f} FCFA<extra></extra>",
    ))
    fig_prev.add_trace(go.Scatter(
        x=list(df_prev_mois["mois"]) + list(df_prev_mois["mois"])[::-1],
        y=list(df_prev_mois["yhat_upper"]) + list(df_prev_mois["yhat_lower"])[::-1],
        fill="toself", fillcolor=_hex_rgba(couleur, 0.18),
        line=dict(color="rgba(0,0,0,0)"),
        name="Intervalle de prédiction (80 %)", hoverinfo="skip",
    ))
    fig_prev.add_trace(go.Scatter(
        x=df_prev_mois["mois"], y=df_prev_mois["yhat"],
        name="Prévision (CA mensuel)",
        line=dict(color=couleur, width=2.5, dash="dash"), mode="lines+markers",
        hovertemplate="Mois : %{x|%B %Y}<br>Prévision : %{y:,.0f} FCFA<extra></extra>",
    ))
    fig_prev.update_layout(
        template="plotly_white",
        # Légende sous le graphique : au-dessus, elle chevauchait la barre
        # d'outils Plotly ancrée en haut à droite.
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        xaxis_title="Mois", yaxis_title="CA mensuel (FCFA)",
        margin=dict(t=30, b=10), height=440,
    )
    st.plotly_chart(fig_prev, use_container_width=True)

    # Sans cette mention, le trou laissé par un mois écarté se lit comme un arrêt
    # d'activité alors qu'il ne traduit qu'un mois incomplet en bord de série.
    if mois_ecartes:
        st.caption(
            f"Mois incomplet(s) écarté(s) de l'historique — moins de 20 jours "
            f"d'activité relevés : {', '.join(mois_ecartes)}."
        )

    st.caption(
        f"Prévision moyenne : **{_fmt(int(df_prev_mois['yhat'].mean()))} FCFA/mois**  •  "
        f"Borne haute du mois le plus chargé : "
        f"**{_fmt(int(df_prev_mois['yhat_upper'].max()))} FCFA**  \n"
        "L'intervalle mensuel est reconstruit en √n à partir des bornes journalières "
        "(erreurs journalières supposées peu corrélées), et non par simple addition, "
        "qui le surestimerait d'environ un facteur 5."
    )

    # WCAG 1.1.1 — alternative textuelle au graphique de prévision
    with st.expander("📋 Données — Prévisions Prophet (tableau)"):
        st.caption(
            "Tableau des prévisions journalières avec intervalle de prédiction à 80 %. "
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
