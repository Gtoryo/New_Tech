# New_Tech — Système d'Information IA pour PME Multiservice

> **Projet de Fin de Cycle — Licence IA & Data Science**
> Modernisation d'une PME africaine (pôle Imprimerie & Sérigraphie) par un pipeline de données complet : ingestion ETL, entrepôt PostgreSQL, prévisions Prophet et interface Streamlit déployée sur le Cloud.

---

## Sommaire

1. [Contexte et problématique](#1-contexte-et-problématique)
2. [Architecture globale](#2-architecture-globale)
3. [Stack technique](#3-stack-technique)
4. [Structure du projet](#4-structure-du-projet)
5. [Schéma de base de données](#5-schéma-de-base-de-données)
6. [Installation et configuration locale](#6-installation-et-configuration-locale)
7. [Utilisation du pipeline ETL](#7-utilisation-du-pipeline-etl)
8. [Module IA — Prophet](#8-module-ia--prophet)
9. [Application Streamlit](#9-application-streamlit)
10. [Intégration continue — GitHub Actions](#10-intégration-continue--github-actions)
11. [Sécurité](#11-sécurité)
12. [Tests automatisés](#12-tests-automatisés)
13. [Perspectives d'évolution](#13-perspectives-dévolution)

---

## 1. Contexte et problématique

L'entreprise d'accueil est une PME multiservice implantée en Afrique proposant quatre pôles d'activité : **vidéosurveillance**, **sérigraphie & imprimerie**, **maintenance informatique** et prestations diverses.

**Problème identifié :** L'intégralité de l'activité était consignée dans des fichiers Excel dispersés sur un seul poste de travail, sans sauvegarde centralisée ni possibilité d'analyse transverse. Ce projet cible exclusivement le **pôle Imprimerie & Sérigraphie**, le plus stratégique en volume de commandes et en besoins de gestion de stocks.

**Trois transformations délivrées :**

| # | Transformation | Bénéficiaire |
|---|---|---|
| 1 | Saisie web unifiée — remplacement d'Excel | Gestionnaire |
| 2 | Tableau de bord BI avec KPIs Plotly | Directeur |
| 3 | Module IA de prévision de la demande (180 jours) | Directeur |

**Utilisateurs cibles :** 2 uniquement — le Directeur (propriétaire) et la Gestionnaire.

---

## 2. Architecture globale

Le pipeline suit une architecture en couches étanches, inspirée du patron *Medallion Architecture* :

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Sources Excel  │────▶│  Pipeline ETL    │────▶│  Supabase (PG)   │────▶│  App Streamlit   │
│                 │     │  (Python)        │     │                  │     │  (Cloud)         │
│ ventes.xlsx     │     │  extract.py      │     │  schema_brut     │     │  Saisie web      │
│ depenses.xlsx   │     │  transform.py    │     │  schema_analytics│     │  Tableau de bord │
│ clients.xlsx    │     │  load.py         │     │  schema_ia       │     │  Prévisions IA   │
└─────────────────┘     │  aggregate.py    │     └──────────────────┘     └──────────────────┘
                        └──────────────────┘
                                 │
                        ┌────────▼────────┐
                        │  model/train.py │
                        │  Prophet + pkl  │
                        │  → prévisions   │
                        │    en BDD       │
                        └─────────────────┘
```

**Point architectural clé :** `model/train.py` effectue deux opérations à chaque exécution : (1) il sauvegarde le modèle entraîné au format `.pkl` dans `models/`, et (2) il pousse les prévisions sur 180 jours dans `schema_ia.previsions_prophet`. Le dashboard Streamlit lit exclusivement les prévisions depuis la base de données — jamais directement depuis les fichiers `.pkl`.

---

## 3. Stack technique

| Couche | Technologie | Version | Rôle |
|---|---|---|---|
| Langage | Python | 3.11 | Unique langage du projet |
| Base de données | Supabase (PostgreSQL) | — | Entrepôt de données Cloud |
| ORM / Connexion | SQLAlchemy + psycopg2 | 2.0.36 | Accès BDD typé |
| Manipulation données | Pandas | 2.2.3 | ETL et feature engineering |
| Modèle IA | Prophet (Meta) | 1.1.6 | Prévision de séries temporelles |
| Backend Prophet | CmdStanPy | 1.3.0 | Moteur de calcul Stan |
| Interface web | Streamlit | ≥ 1.35 | Application fullstack Python |
| Visualisation | Plotly | ≥ 5.22 | Graphiques interactifs |
| Authentification | bcrypt | 4.2.1 | Hachage des mots de passe |
| Gestion secrets | python-dotenv | 1.0.1 | Variables d'environnement locales |
| CI/CD | GitHub Actions | — | Réentraînement mensuel automatisé |
| Tests | pytest | 8.3.5 | Tests unitaires ETL + Prophet |

---

## 4. Structure du projet

```
New_Tech/
│
├── main.py                     # Point d'entrée du pipeline ETL complet
├── streamlit_app.py            # Point d'entrée Streamlit Cloud
├── runtime.txt                 # Python 3.11 (imposé à Streamlit Cloud)
├── requirements.txt            # Dépendances runtime (Streamlit, Plotly…)
├── requirements-train.txt      # Dépendances CI (+ Prophet, pytest)
├── variable.env                # Variables d'environnement locales (non commité)
│
├── src/                        # Pipeline ETL — couches séparées
│   ├── extract.py              # Lecture des 3 fichiers Excel → DataFrames bruts
│   ├── transform.py            # Nettoyage, typage, normalisation
│   ├── load.py                 # Chargement schema_brut + schema_analytics
│   └── aggregate.py            # Agrégation schema_analytics → schema_ia
│
├── model/
│   └── train.py                # Entraînement Prophet + push prévisions en BDD
│
├── models/                     # Modèles sérialisés (.pkl) — générés à l'exécution
│   ├── prophet_global.pkl
│   ├── prophet_imprimerie.pkl
│   └── prophet_serigraphie.pkl
│
├── app/                        # Modules de l'application Streamlit
│   ├── dashboard.py            # Onglet tableau de bord (KPIs Plotly)
│   ├── login.py                # Page d'authentification (bcrypt)
│   └── saisie.py               # Onglet saisie des commandes
│
├── data/                       # Sources Excel (non commitées)
│   ├── ventes_historiques.xlsx
│   ├── depenses_et_achats.xlsx
│   └── suivi_clients_prospects.xlsx
│
├── tests/                      # Suite de tests automatisés
│   ├── test_transform.py       # 25 tests unitaires ETL
│   ├── test_model.py           # 11 tests unitaires Prophet
│   └── conftest.py             # Configuration sys.path pour pytest
│
├── info_projet/                # Documentation de cadrage
│   ├── MPR.md                  # Rapport de cadrage métier (contexte + vision)
│   ├── Architecture.md         # Document d'architecture technique
│   ├── conseil.md              # Notes de tutorat et arbitrages techniques
│   └── role.md                 # Directives de conduite du projet
│
└── .github/
    └── workflows/
        └── retrain_prophet.yml # Workflow CI/CD — réentraînement mensuel
```

---

## 5. Schéma de base de données

La base de données est organisée en **trois schémas PostgreSQL étanches**, chacun ayant une responsabilité unique dans le cycle de vie de la donnée.

### `schema_brut` — Archive des données brutes

Reçoit les données Excel à l'état natif, sans transformation. Permet de rejouer le pipeline en cas d'erreur.

| Table | Description |
|---|---|
| `ventes_raw` | Lignes de ventes brutes (toutes anomalies préservées) |
| `depenses_raw` | Achats fournisseurs bruts |
| `clients_raw` | Référentiel clients brut |

### `schema_analytics` — Données propres pour la BI

Données nettoyées, normalisées en 3NF, alimentant le tableau de bord Streamlit.

| Table | Colonnes principales |
|---|---|
| `client` | `id_client`, `nom_client`, `entreprise`, `telephone`, `email`, `ville` |
| `employe` | `id_employe`, `nom_employe` |
| `service` | `id_service`, `libelle` (Sérigraphie, Imprimerie, Vidéosurveillance, Maintenance) |
| `facture` | `id_facture`, `date_facture`, `statut_paiement`, `id_client` FK, `id_employe` FK |
| `ligne_facture` | `description`, `quantite`, `prix_unitaire`, `total_ligne`, `id_facture` FK, `id_service` FK |
| `fournisseur` | `id_fournisseur`, `nom` |
| `categorie_achat` | `id_categorie`, `libelle` |
| `achat` | `date_achat`, `libelle_article`, `quantite`, `prix_achat_total`, `mode_paiement`, `id_fournisseur` FK, `id_categorie` FK |

### `schema_ia` — Séries temporelles pour Prophet

Données agrégées au format natif Prophet (`ds` = date, `y` = valeur), alimentant l'entraînement du modèle.

| Table | Colonnes | Description |
|---|---|---|
| `serie_ventes_journalieres` | `ds`, `y`, `nb_commandes`, `rafraichi_le` | CA global par jour |
| `serie_ventes_par_service` | `ds`, `service`, `y`, `nb_commandes`, `rafraichi_le` | CA par jour et par pôle d'activité |
| `previsions_prophet` | `ds`, `yhat`, `yhat_lower`, `yhat_upper`, `service`, `charge_le` | Prévisions 180 jours (lecture par le dashboard) |

---

## 6. Installation et configuration locale

### Prérequis

- Python 3.11
- Un projet Supabase avec les 3 schémas initialisés

### Cloner et installer

```bash
git clone <url-du-repo>
cd New_Tech

# Créer et activer l'environnement virtuel
python -m venv .env
# Windows
.env\Scripts\activate
# Linux/Mac
source .env/bin/activate

# Installer les dépendances runtime
pip install -r requirements.txt
```

### Variables d'environnement

Créer un fichier `variable.env` à la racine (ne jamais le commiter) :

```env
DB_HOST=aws-0-eu-west-1.pooler.supabase.com
DB_PORT=6543
DB_NAME=postgres
DB_USER=postgres.xxxxxxxxxx
DB_PASSWORD=votre_mot_de_passe
```

> **Pourquoi `variable.env` et non `.env` ?** Le dossier de l'environnement virtuel Python s'appelle `.env` — un doublon de nom provoquerait une confusion dans l'IDE. Tous les scripts chargent explicitement `load_dotenv("variable.env")`.

---

## 7. Utilisation du pipeline ETL

Le pipeline complet (Extract → Transform → Load → Aggregate) s'exécute via :

```bash
python main.py
```

Il est également possible d'exécuter chaque couche indépendamment pour le débogage :

```bash
# Extraction seule
python -c "from src.extract import extraire_tout; extraire_tout()"

# Agrégation schema_ia seule
python src/aggregate.py
```

**Idempotence garantie :** chaque exécution tronque les tables avant d'insérer — relancer le script deux fois produit exactement le même état final en base.

---

## 8. Module IA — Prophet

### Entraînement

```bash
# Installer les dépendances d'entraînement (Prophet + CmdStan)
pip install -r requirements-train.txt

# Entraîner les modèles et pousser les prévisions en BDD
python model/train.py
```

`model/train.py` entraîne **3 modèles distincts** :
- `prophet_global` — toutes activités confondues
- `prophet_imprimerie` — pôle Imprimerie uniquement
- `prophet_serigraphie` — pôle Sérigraphie uniquement

Chaque modèle est sérialisé dans `models/*.pkl` et ses prévisions sur **180 jours** sont poussées dans `schema_ia.previsions_prophet` (DELETE puis INSERT — idempotent).

### Choix de Prophet

Prophet (Meta, 2017) a été retenu pour trois raisons :
1. **Robustesse aux données manquantes** — les historiques Excel comportaient des trous (weekends, jours fériés locaux).
2. **Gestion native des saisonnalités multiples** — annuelle (rentrées scolaires, fêtes) et hebdomadaire.
3. **Interprétabilité** — le modèle additif décompose explicitement tendance, saisonnalité et effets de jours fériés, ce qui facilite la validation métier avec le Directeur.

---

## 9. Application Streamlit

```bash
streamlit run streamlit_app.py
```

L'application expose trois onglets :

| Onglet | Utilisateur | Contenu |
|---|---|---|
| **Saisie** | Gestionnaire | Formulaire de saisie des commandes, envoi direct en BDD |
| **Tableau de bord** | Directeur | KPIs Plotly (CA, top services, évolution mensuelle) |
| **Prévisions IA** | Directeur | Courbes Prophet 180 jours avec intervalles de confiance |

**Déploiement :** l'application est hébergée sur Streamlit Cloud. Les secrets de connexion à Supabase sont injectés via le gestionnaire de secrets intégré de la plateforme — aucun identifiant n'est présent dans le dépôt.

---

## 10. Intégration continue — GitHub Actions

Le workflow `.github/workflows/retrain_prophet.yml` s'exécute automatiquement **le 1er de chaque mois à 02h00 UTC**, et peut être déclenché manuellement.

**Étapes du workflow :**

```
1. Checkout du dépôt
2. Installation Python 3.11
3. Installation des dépendances (requirements-train.txt)
4. Installation de CmdStan (moteur de calcul de Prophet)
5. Exécution de la suite de tests pytest (validation pré-entraînement)
6. Réentraînement Prophet + push des prévisions en BDD
7. Commit automatique des modèles .pkl mis à jour
```

Les secrets de connexion à Supabase (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) sont stockés dans GitHub Secrets — jamais en clair dans le code.

---

## 11. Sécurité

| Mesure | Implémentation |
|---|---|
| Chiffrement en transit | HTTPS/TLS natif sur Supabase et Streamlit Cloud |
| Gestion des secrets | `variable.env` local (hors dépôt) + GitHub Secrets (CI) + Streamlit Secrets (prod) |
| Hachage des mots de passe | `bcrypt` — les mots de passe ne sont jamais stockés en clair |
| Authentification | Page de login obligatoire avant tout accès à l'application |
| Isolation des schémas | Trois schémas PostgreSQL étanches — aucune requête ne traverse les frontières de schéma |

---

## 12. Tests automatisés

```bash
# Lancer la suite complète
pytest tests/ -v

# Résultats attendus : 36 tests (25 ETL + 11 Prophet)
```

| Fichier | Tests | Ce qui est vérifié |
|---|---|---|
| `tests/test_transform.py` | 25 | `parser_date` (4 formats), `normaliser_service` (7 variantes), `normaliser_ville`, `transformer_ventes` (doublons, totaux recalculés) |
| `tests/test_model.py` | 11 | `slugify`, entraînement Prophet end-to-end, colonnes de sortie, horizon de prévision 180 jours |

`conftest.py` à la racine ajoute le projet au `sys.path` pour que les imports fonctionnent sans installation en mode développement.

---

## 13. Perspectives d'évolution

| Axe | Description | Complexité |
|---|---|---|
| **API REST (FastAPI)** | Isoler le modèle Prophet derrière une API indépendante pour le rendre accessible à d'autres applications de la PME | Moyenne |
| **Multi-pôles** | Étendre le périmètre aux pôles Vidéosurveillance et Maintenance informatique | Faible |
| **Alertes automatiques** | Notifier le Directeur par email (SMTP) quand les prévisions détectent un risque de rupture de stock | Faible |
| **Tests de non-régression** | Étendre la suite pytest avec des tests d'intégration vérifiant le round-trip ETL complet contre une base de test dédiée | Moyenne |
| **Monitoring du modèle** | Mesurer la dérive du modèle (MAE, MAPE) après chaque réentraînement mensuel et logger les métriques en base | Moyenne |

---

*Projet réalisé dans le cadre d'un stage de Licence IA & Data Science — 2025/2026.*
