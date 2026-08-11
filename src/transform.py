"""
transform.py — Couche Transformation du pipeline ETL
Responsabilité unique : nettoyer et typer les DataFrames bruts
produits par extract.py. Aucune écriture en base ici.
"""

import re
from datetime import datetime

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES PARTAGÉS
# ─────────────────────────────────────────────────────────────────────────────

# Mois français → numéro (pour les dates texte "Début Juin 2024")
_MOIS_FR = {
    "janvier": 1,  "février": 2,  "mars": 3,    "avril": 4,
    "mai": 5,      "juin": 6,     "juillet": 7, "août": 8,
    "septembre": 9,"octobre": 10, "novembre": 11,"décembre": 12,
}

# Dictionnaire de normalisation des types de service
_MAP_SERVICE = {
    "sérigraphie":       "Sérigraphie",
    "sérigrafe":         "Sérigraphie",
    "serigraphy":        "Sérigraphie",
    "sérigr.":           "Sérigraphie",
    "sérigrpahie":       "Sérigraphie",
    "imprimerie":        "Imprimerie",
    "imprimrie":         "Imprimerie",
    "imprimeri":         "Imprimerie",
    "vidéosurveillance": "Vidéosurveillance",
    "video surveillance":"Vidéosurveillance",
    "vidéo-surveillance":"Vidéosurveillance",
    "vidéosur.":         "Vidéosurveillance",
    "maintenance":       "Maintenance",
    "reparation":        "Maintenance",
    "maintenace":        "Maintenance",
    "maint.":            "Maintenance",
}

# Statuts de paiement ramenés au référentiel contrôlé de l'API. Le contrat
# CommandeIn (api/schemas.py) n'admet que trois libellés — Payé, Non payé,
# Partiel — là où les classeurs en portent un quatrième, « En attente », de même
# sens que « Non payé ». Sans cette table, schema_analytics.facture accumulerait
# deux vocabulaires selon la voie d'écriture, pipeline ETL ou API, que plus rien
# ne réconcilierait ensuite. La contrainte ck_facture_statut (sql/02_tables.sql)
# verrouille le résultat côté base.
_MAP_STATUT = {
    "payé":      "Payé",
    "paye":      "Payé",
    "non payé":  "Non payé",
    "non paye":  "Non payé",
    "en attente":"Non payé",
    "impayé":    "Non payé",
    "partiel":   "Partiel",
}

# Variantes connues de "Pointe-Noire" à normaliser
_VARIANTES_PN = {"pointe noire", "pn", "pte-noire", "pointenoire",
                 "pointe-noire", "p.noire"}

# Valeurs de saisie signifiant « montant non calculé » plutôt qu'un montant
# réellement nul.
# Le zéro est la SEULE forme présente dans le jeu de travail versionné
# (121 lignes) — voir la limitation documentée dans generated_data/
# generate_data.py, qui explique pourquoi les trois formes prévues au cadrage
# ne s'y trouvent pas toutes.
# 999 relève donc de la programmation défensive : c'est une convention de
# saisie relevée au cadrage sur les classeurs en service, traitée ici au cas où
# elle apparaîtrait en source, et couverte par tests/test_transform.py sur un
# DataFrame construit pour l'occasion. Elle n'est pas exercée par le jeu de
# travail lui-même. Le cas « valeur absente » est traité par la même règle, via
# le test isna() du masque plus bas.
_SENTINELLES_TOTAL = {0, 999}


def _parser_date(valeur) -> datetime | None:
    """
    Convertit une valeur brute (str ou déjà datetime) en objet datetime.
    Gère 4 formats rencontrés dans les fichiers Excel sources :
      - "15/06/2024"   (format standard français)
      - "2024-06-15"   (ISO 8601)
      - "15-06-2024"   (tirets)
      - "Début Juin 2024" (texte libre → fixé au 1er du mois)
    Retourne None si la valeur est vide ou non parsable.
    """
    if pd.isna(valeur):
        return None

    if isinstance(valeur, (datetime, pd.Timestamp)):
        return pd.Timestamp(valeur)

    v = str(valeur).strip()

    try:
        return datetime.strptime(v, "%d/%m/%Y")
    except ValueError:
        pass

    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        pass

    try:
        return datetime.strptime(v, "%d-%m-%Y")
    except ValueError:
        pass

    # Format texte "Début Mois Année" — fixé au 1er du mois
    match = re.search(r"([A-Za-zÀ-ÿ]+)\s+(\d{4})", v, re.IGNORECASE)
    if match:
        mois_str = match.group(1).lower()
        annee    = int(match.group(2))
        mois_num = _MOIS_FR.get(mois_str)
        if mois_num:
            return datetime(annee, mois_num, 1)

    return None


def _normaliser_service(valeur) -> str | None:
    """Corrige les fautes de frappe des types de service vers le libellé canonique."""
    if pd.isna(valeur):
        return None
    cle = str(valeur).strip().lower()
    return _MAP_SERVICE.get(cle, str(valeur).strip())


def _normaliser_statut(valeur) -> str | None:
    """Ramène un statut de paiement au référentiel contrôlé de l'API."""
    if pd.isna(valeur):
        return None
    cle = str(valeur).strip().lower()
    return _MAP_STATUT.get(cle, str(valeur).strip())


def _normaliser_ville(valeur) -> str | None:
    """Normalise les variantes orthographiques de 'Pointe-Noire'."""
    if pd.isna(valeur):
        return None
    cle = str(valeur).strip().lower()
    if cle in _VARIANTES_PN:
        return "Pointe-Noire"
    return str(valeur).strip()


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMATION VENTES
# ─────────────────────────────────────────────────────────────────────────────

def transformer_ventes(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Nettoie et restructure le DataFrame brut des ventes.

    Retourne un dictionnaire de 4 DataFrames prêts pour l'insertion
    dans schema_analytics (sans résolution des IDs — rôle de load.py) :
        'clients'  → table client
        'employes' → table employe
        'factures' → table facture
        'lignes'   → table ligne_facture
    """
    print("\n-- TRANSFORMATION VENTES ---------------------------------------")
    df = df.copy()
    n_initial = len(df)

    # ── ÉTAPE 1 : Parsage des dates ──────────────────────────────────────────
    df["date_facture"] = df["Date"].apply(_parser_date)

    # ── ÉTAPE 2 : Normalisation des libellés à référentiel contrôlé ──────────
    # Service et statut de paiement sont les deux champs que l'API contraint par
    # un type Literal. Le pipeline doit produire le même vocabulaire, sans quoi
    # les deux voies d'écriture divergent dans la même colonne.
    df["service"] = df["Service_Type"].apply(_normaliser_service)
    df["Statut_Paiement"] = df["Statut_Paiement"].apply(_normaliser_statut)

    # ── ÉTAPE 3 : Suppression des lignes sans date ni client ─────────────────
    # Ces lignes sont inutilisables : impossible de les rattacher à une facture
    df = df.dropna(subset=["date_facture", "Client"])
    print(f"  Lignes supprimées (date ou client manquant) : {n_initial - len(df)}")

    # L'employé, lui, n'est pas obligatoire. Une facture sans employé assigné
    # reste exploitable : la commande a eu lieu et son chiffre d'affaires
    # compte. Elle est donc conservée, et son lien vers employe restera NULL —
    # ce que le schéma autorise. On le compte ici plutôt que de le laisser
    # apparaître en aval comme une clé étrangère non résolue.
    sans_employe = df["Employe_En_Charge"].isna().sum()
    print(f"  Factures sans employé assigné (id_employe NULL) : {sans_employe}")

    # ── ÉTAPE 4 : Dédoublonnage sur Facture_ID ───────────────────────────────
    # On garde la première occurrence de chaque facture (doublons Excel ~5%)
    n_avant = len(df)
    df = df.drop_duplicates(subset=["Facture_ID"], keep="first")
    print(f"  Doublons supprimés                         : {n_avant - len(df)}")

    # ── ÉTAPE 5 : Recalcul du Total quand incohérent ─────────────────────────
    # Les sentinelles de saisie et les valeurs absentes sont remplacées par
    # Quantite × Prix. Supprimer ces lignes appauvrirait l'historique : la
    # commande a bien eu lieu, seul son montant n'a pas été calculé.
    df["Prix_Unitaire"] = pd.to_numeric(df["Prix_Unitaire"], errors="coerce")
    df["Quantite"]      = pd.to_numeric(df["Quantite"],      errors="coerce")
    df["Total"]         = pd.to_numeric(df["Total"],          errors="coerce")

    masque_incoherent = df["Total"].isna() | df["Total"].isin(_SENTINELLES_TOTAL)
    df.loc[masque_incoherent, "Total"] = (
        df.loc[masque_incoherent, "Quantite"] *
        df.loc[masque_incoherent, "Prix_Unitaire"]
    )
    print(f"  Totaux recalculés                          : {masque_incoherent.sum()}")

    # ── ÉTAPE 6 : Cast des types numériques finaux ───────────────────────────
    df["Quantite"]      = df["Quantite"].astype("Int64")   # Int64 tolère les NaN
    df["Prix_Unitaire"] = df["Prix_Unitaire"].round(2)
    df["Total"]         = df["Total"].round(2)

    print(f"  Lignes propres conservées                  : {len(df)}")

    # ── ÉTAPE 7 : Extraction des 4 DataFrames normalisés ─────────────────────

    # Clients uniques extraits des ventes
    df_clients = (
        df[["Client", "Telephone"]]
        .drop_duplicates(subset=["Client"])
        .rename(columns={"Client": "nom_client", "Telephone": "telephone"})
        .reset_index(drop=True)
    )

    # Employés uniques (on ignore les lignes sans employé assigné)
    df_employes = (
        df[["Employe_En_Charge"]]
        .dropna(subset=["Employe_En_Charge"])
        .drop_duplicates()
        .rename(columns={"Employe_En_Charge": "nom_employe"})
        .reset_index(drop=True)
    )

    # Factures : une ligne par commande
    df_factures = (
        df[["Facture_ID", "date_facture", "Statut_Paiement", "Client", "Employe_En_Charge"]]
        .rename(columns={
            "Facture_ID":        "facture_id",
            "Statut_Paiement":   "statut_paiement",
            "Client":            "nom_client",
            "Employe_En_Charge": "nom_employe",
        })
        .reset_index(drop=True)
    )

    # Lignes de facture : description, quantités, prix, service
    df_lignes = (
        df[["Facture_ID", "Description", "Quantite", "Prix_Unitaire", "Total", "service"]]
        .rename(columns={
            "Facture_ID":    "facture_id",
            "Description":   "description",
            "Quantite":      "quantite",
            "Prix_Unitaire": "prix_unitaire",
            "Total":         "total_ligne",
            "service":       "service_libelle",
        })
        .reset_index(drop=True)
    )

    print("-- FIN TRANSFORMATION VENTES -----------------------------------\n")

    return {
        "clients":  df_clients,
        "employes": df_employes,
        "factures": df_factures,
        "lignes":   df_lignes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMATION DÉPENSES
# ─────────────────────────────────────────────────────────────────────────────

def transformer_depenses(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Nettoie et restructure le DataFrame brut des dépenses.

    Retourne un dictionnaire de 3 DataFrames :
        'fournisseurs'  → table fournisseur
        'categories'    → table categorie_achat
        'achats'        → table achat
    """
    print("\n-- TRANSFORMATION DÉPENSES -------------------------------------")
    df = df.copy()
    n_initial = len(df)

    # ── ÉTAPE 1 : Suppression des lignes entièrement vides ───────────────────
    # Une ligne vide n'a aucune colonne exploitable
    df = df.dropna(how="all")
    print(f"  Lignes vides supprimées                    : {n_initial - len(df)}")

    # ── ÉTAPE 2 : Suppression des lignes sans fournisseur ni article ─────────
    n_avant = len(df)
    df = df.dropna(subset=["Fournisseur", "Article"])
    print(f"  Lignes incomplètes supprimées              : {n_avant - len(df)}")

    # ── ÉTAPE 3 : Parsage des dates ──────────────────────────────────────────
    df["date_achat"] = df["Date"].apply(_parser_date)
    df = df.dropna(subset=["date_achat"])

    # ── ÉTAPE 4 : Correction des montants négatifs ───────────────────────────
    df["Prix_Achat_Total"] = pd.to_numeric(df["Prix_Achat_Total"], errors="coerce")
    masque_negatif = df["Prix_Achat_Total"] < 0
    df.loc[masque_negatif, "Prix_Achat_Total"] = df.loc[masque_negatif, "Prix_Achat_Total"].abs()
    print(f"  Montants négatifs corrigés                 : {masque_negatif.sum()}")

    # ── ÉTAPE 5 : Cast des types ─────────────────────────────────────────────
    df["Quantite"]         = pd.to_numeric(df["Quantite"], errors="coerce").astype("Int64")
    df["Prix_Achat_Total"] = df["Prix_Achat_Total"].round(2)

    # Nettoyage des chaînes de caractères
    for col in ["Fournisseur", "Article", "Categorie", "Mode_Paiement"]:
        df[col] = df[col].astype(str).str.strip()

    print(f"  Lignes propres conservées                  : {len(df)}")

    # ── ÉTAPE 6 : Extraction des 3 DataFrames normalisés ─────────────────────

    df_fournisseurs = (
        df[["Fournisseur"]]
        .drop_duplicates()
        .rename(columns={"Fournisseur": "nom"})
        .reset_index(drop=True)
    )

    df_categories = (
        df[["Categorie"]]
        .drop_duplicates()
        .rename(columns={"Categorie": "libelle"})
        .reset_index(drop=True)
    )

    df_achats = (
        df[["date_achat", "Fournisseur", "Article", "Categorie", "Quantite",
            "Prix_Achat_Total", "Mode_Paiement"]]
        .rename(columns={
            "Fournisseur":      "nom_fournisseur",
            "Article":          "libelle_article",
            "Categorie":        "libelle_categorie",
            "Quantite":         "quantite",
            "Prix_Achat_Total": "prix_achat_total",
            "Mode_Paiement":    "mode_paiement",
        })
        .reset_index(drop=True)
    )

    print("-- FIN TRANSFORMATION DÉPENSES ---------------------------------\n")

    return {
        "fournisseurs": df_fournisseurs,
        "categories":   df_categories,
        "achats":       df_achats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRANSFORMATION CLIENTS
# ─────────────────────────────────────────────────────────────────────────────

def transformer_clients(df: pd.DataFrame) -> pd.DataFrame:
    """
    Nettoie le DataFrame brut des clients/prospects.

    Retourne un DataFrame unique prêt pour la table client de schema_analytics.
    Colonnes : nom_client, entreprise, telephone, email, ville
    """
    print("\n-- TRANSFORMATION CLIENTS --------------------------------------")
    df = df.copy()
    n_initial = len(df)

    # ── ÉTAPE 1 : Nettoyage des chaînes ─────────────────────────────────────
    for col in ["Nom_Client", "Entreprise", "Telephone", "Email", "Ville"]:
        df[col] = df[col].astype(str).str.strip()
        # Remettre NaN les chaînes vides et les "nan" issus du cast
        df[col] = df[col].replace({"": None, "nan": None, "None": None})

    # ── ÉTAPE 2 : Normalisation de la ville ──────────────────────────────────
    df["Ville"] = df["Ville"].apply(_normaliser_ville)

    # ── ÉTAPE 3 : Déduplication insensible à la casse ────────────────────────
    # Les doublons ont le nom en MAJUSCULES ; on conserve la version en casse
    # mixte, plus lisible. Un tri alphabétique simple ne suffit pas : en ASCII
    # les majuscules précèdent les minuscules ("PHARMACIE X" < "Pharmacie X"),
    # ce qui conserverait justement la variante à écarter. On trie donc sur un
    # indicateur de casse explicite (False = casse mixte, retenue en premier).
    df["_nom_lower"]     = df["Nom_Client"].str.lower()
    df["_est_majuscule"] = df["Nom_Client"].str.isupper()
    df = df.sort_values(["_nom_lower", "_est_majuscule"])
    df = df.drop_duplicates(subset=["_nom_lower"], keep="first")
    df = df.drop(columns=["_nom_lower", "_est_majuscule"])
    print(f"  Doublons supprimés                         : {n_initial - len(df)}")

    # ── ÉTAPE 4 : Renommage et sélection des colonnes finales ────────────────
    df_clients = (
        df[["Nom_Client", "Entreprise", "Telephone", "Email", "Ville"]]
        .rename(columns={
            "Nom_Client": "nom_client",
            "Entreprise": "entreprise",
            "Telephone":  "telephone",
            "Email":      "email",
            "Ville":      "ville",
        })
        .reset_index(drop=True)
    )

    print(f"  Clients propres conservés                  : {len(df_clients)}")
    print("-- FIN TRANSFORMATION CLIENTS ----------------------------------\n")

    return df_clients


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def transformer_tout(dfs: dict[str, pd.DataFrame]) -> dict:
    """
    Lance les 3 transformations et retourne toutes les données propres.

    Paramètre :
        dfs — dictionnaire retourné par extract.extraire_tout()

    Retourne un dictionnaire avec les clés :
        'ventes'   → dict (clients, employes, factures, lignes)
        'depenses' → dict (fournisseurs, categories, achats)
        'clients'  → DataFrame
    """
    return {
        "ventes":   transformer_ventes(dfs["ventes"]),
        "depenses": transformer_depenses(dfs["depenses"]),
        "clients":  transformer_clients(dfs["clients"]),
    }
