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
9. [API REST — FastAPI](#9-api-rest--fastapi)
10. [Application Streamlit](#10-application-streamlit)
11. [Intégration continue — GitHub Actions](#11-intégration-continue--github-actions)
12. [Sécurité](#12-sécurité)
13. [Tests automatisés](#13-tests-automatisés)
14. [Perspectives d'évolution](#14-perspectives-dévolution)

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
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Sources Excel  │────▶│  Pipeline ETL    │────▶│  Supabase (PG)   │
│                 │     │  (Python)        │     │                  │
│ ventes.xlsx     │     │  extract.py      │     │  schema_brut     │
│ depenses.xlsx   │     │  transform.py    │     │  schema_analytics│
│ clients.xlsx    │     │  load.py         │     │  schema_ia       │
└─────────────────┘     │  aggregate.py    │     └───────┬──────────┘
                        └──────────────────┘             │ SQL
                                 │                       ▼
                        ┌────────▼────────┐     ┌──────────────────┐
                        │  GitHub Actions │     │  API REST FastAPI│
                        │  (mensuel)      │     │  (Render)        │
                        │  model/train.py │     │  GET /previsions │
                        │  → prévisions   │     │  POST /commandes │
                        │    en BDD       │     └────────┬─────────┘
                        └─────────────────┘              │ HTTPS (httpx)
                                                         ▼
                                                ┌──────────────────┐
                                                │  App Streamlit   │
                                                │ (Streamlit Cloud)│
                                                │  Saisie web      │
                                                │  Tableau de bord │
                                                │  Prévisions IA   │
                                                └──────────────────┘
```

**Points architecturaux clés :**

- `model/train.py` effectue deux opérations à chaque exécution : (1) il sauvegarde le modèle entraîné au format `.pkl` dans `models/`, et (2) il pousse les prévisions sur 180 jours dans `schema_ia.previsions_prophet`. Le dashboard Streamlit lit exclusivement les prévisions depuis la base de données — jamais directement depuis les fichiers `.pkl`.
- **L'API REST FastAPI (déployée sur Render) constitue la couche de service entre l'interface et la base de données** : `model/predict.py` récupère les prévisions via `GET /api/v1/previsions/{service}` et `app/saisie.py` soumet les nouvelles commandes via `POST /api/v1/commandes/` (authentifié par clé API). Ces deux modules ne contiennent aucune dépendance à SQLAlchemy ni à Supabase.
- Exception documentée : `app/dashboard.py` lit encore les séries historiques directement dans `schema_ia` via SQLAlchemy (lecture seule, cache 1 h). Le raccordement à un futur endpoint `GET /api/v1/historique/` est identifié comme prochaine évolution.

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
| API REST | FastAPI | ≥ 0.115 | Couche de service (prévisions + commandes) |
| Serveur ASGI | Uvicorn | ≥ 0.30 | Exécution de l'API |
| Hébergement API | Render | — | Déploiement PaaS de l'API (plan gratuit) |
| Client HTTP | httpx | ≥ 0.27 | Appels Streamlit → API |
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
├── conftest.py                 # Configuration sys.path pour pytest
├── runtime.txt                 # Python 3.11 (Streamlit Cloud + Render)
├── requirements.txt            # Dépendances runtime (Streamlit, Plotly, httpx…)
├── requirements-train.txt      # Dépendances CI (+ Prophet, pytest)
├── requirements-api.txt        # Dépendances API Render (FastAPI, sans pandas)
├── variable.env                # Variables d'environnement locales (non commité)
│
├── src/                        # Pipeline ETL — couches séparées
│   ├── extract.py              # Lecture des 3 fichiers Excel → DataFrames bruts
│   ├── transform.py            # Nettoyage, typage, normalisation
│   ├── load.py                 # Chargement schema_brut + schema_analytics
│   └── aggregate.py            # Agrégation schema_analytics → schema_ia
│
├── model/
│   ├── train.py                # Entraînement Prophet + push prévisions en BDD
│   ├── predict.py              # Client API — GET prévisions (httpx + cache Streamlit)
│   └── evaluate.py             # Cross-validation MAE/MAPE/Coverage (évaluation)
│
├── models/                     # Modèles sérialisés (.pkl) — générés à l'exécution
│   ├── prophet_global.pkl
│   ├── prophet_imprimerie.pkl
│   ├── prophet_serigraphie.pkl
│   ├── prophet_maintenance.pkl
│   └── prophet_videosurveillance.pkl
│
├── api/                        # API REST FastAPI (déployée sur Render)
│   ├── main.py                 # Point d'entrée — CORS, routes, /health
│   ├── auth.py                 # Authentification X-API-Key (temps constant)
│   ├── database.py             # Moteur SQLAlchemy partagé
│   ├── schemas.py              # Contrats Pydantic (CommandeIn, PrevisionPoint…)
│   └── routes/
│       ├── commandes.py        # POST /api/v1/commandes/ (transaction atomique)
│       ├── previsions.py       # GET /api/v1/previsions/{service}
│       └── kpis.py             # GET /api/v1/kpis/
│
├── app/                        # Modules de l'application Streamlit
│   ├── dashboard.py            # Onglet tableau de bord (KPIs Plotly)
│   ├── login.py                # Page d'authentification (bcrypt)
│   └── saisie.py               # Onglet saisie — client API (httpx POST)
│
├── data/                       # Sources Excel (non commitées)
│   ├── ventes_historiques.xlsx
│   ├── depenses_et_achats.xlsx
│   └── suivi_clients_prospects.xlsx
│
├── tests/                      # Suite de tests automatisés
│   ├── test_transform.py       # 25 tests unitaires ETL
│   └── test_model.py           # 11 tests unitaires Prophet
│
├── info_projet/                # Documentation de cadrage
│   ├── MPR.md                  # Rapport de cadrage métier (contexte + vision)
│   └── Architecture.md         # Document d'architecture technique
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

`model/train.py` entraîne **5 modèles distincts** :
- `prophet_global` — toutes activités confondues
- `prophet_imprimerie` — pôle Imprimerie
- `prophet_serigraphie` — pôle Sérigraphie
- `prophet_maintenance` — pôle Maintenance
- `prophet_videosurveillance` — pôle Vidéosurveillance

Chaque modèle est sérialisé dans `models/*.pkl` et ses prévisions sur **180 jours** sont poussées dans `schema_ia.previsions_prophet` (DELETE puis INSERT — idempotent).

### Évaluation

```bash
# Cross-validation temporelle (MAE / MAPE / Coverage par horizon 30/60/90 j)
python model/evaluate.py
```

`model/evaluate.py` exécute une cross-validation à fenêtre croissante (`initial=365j`, `period=30j`, `horizon=90j`) sur le modèle global et compare trois valeurs de `changepoint_prior_scale` (0.01 / 0.05 / 0.50) — la valeur 0.05 retenue minimise le MAPE.

### Choix de Prophet

Prophet (Meta, 2017) a été retenu pour trois raisons :
1. **Robustesse aux données manquantes** — les historiques Excel comportaient des trous (weekends, jours fériés locaux).
2. **Gestion native des saisonnalités multiples** — annuelle (rentrées scolaires, fêtes) et hebdomadaire.
3. **Interprétabilité** — le modèle additif décompose explicitement tendance, saisonnalité et effets de jours fériés, ce qui facilite la validation métier avec le Directeur.

---

## 9. API REST — FastAPI

L'API constitue la **couche de service** entre l'interface Streamlit et la base de données : elle expose les prévisions Prophet pré-calculées et reçoit les nouvelles commandes. Tout client HTTP futur (application mobile, ERP, logiciel de caisse) peut consommer les mêmes endpoints sans accès direct à Supabase.

### Endpoints exposés

| Méthode | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | Non | Health-check (supervision, réveil de l'instance Render) |
| GET | `/api/v1/previsions/{service}` | Non | Prévisions Prophet pré-calculées (`global`, `Imprimerie`, `Sérigraphie`, `Maintenance`, `Vidéosurveillance`) |
| POST | `/api/v1/commandes/` | `X-API-Key` | Enregistre une commande — transaction atomique : upsert client + upsert employé + insertion facture + ligne_facture |
| GET | `/api/v1/kpis/` | Non | CA total, nombre de commandes, CA moyen journalier, pôle leader |

Les contrats d'entrée/sortie sont définis par des modèles **Pydantic** (`api/schemas.py`) : validation automatique des types et des valeurs (`Literal` sur les libellés de service), réponse `422` en cas de payload invalide, documentation OpenAPI auto-générée.

### Lancement local

```bash
pip install -r requirements-api.txt
uvicorn api.main:app --reload
# Documentation interactive : http://localhost:8000/docs
```

### Déploiement sur Render

| Élément | Valeur |
|---|---|
| Fichier de dépendances | `requirements-api.txt` — **sans pandas ni `uvicorn[standard]`** (limite mémoire 512 Mo du plan gratuit ; leur inclusion provoquait un crash SIGSEGV / exit 139) |
| Version Python | `runtime.txt` → 3.11 |
| Commande de démarrage | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Documentation en production | `https://new-tech-d91x.onrender.com/docs` |

> **Cold start :** sur le plan gratuit, l'instance s'endort après 15 minutes d'inactivité et met jusqu'à 30 secondes à redémarrer. Les clients httpx configurent un timeout de 15 s pour absorber partiellement ce délai.

### Sécurité de l'API

- **Authentification** : l'endpoint d'écriture exige une clé secrète dans l'en-tête `X-API-Key`, vérifiée **en temps constant** (`secrets.compare_digest`) contre la variable d'environnement `API_SECRET_KEY` — clé stockée dans les variables Render côté serveur et les secrets Streamlit côté client.
- **CORS** : origines restreintes à l'URL Streamlit Cloud de production, méthodes limitées à GET/POST.

---

## 10. Application Streamlit

```bash
streamlit run streamlit_app.py
```

L'application expose trois vues, routées selon le rôle de l'utilisateur authentifié :

| Vue | Utilisateur | Contenu |
|---|---|---|
| **Saisie** | Gestionnaire | Formulaire de commandes — envoi à l'API via `POST /api/v1/commandes/` (authentifié `X-API-Key`) |
| **Tableau de bord** | Directeur | KPIs Plotly (CA, top services, évolution mensuelle) |
| **Prévisions IA** | Directeur | Courbes Prophet 180 jours via `GET /api/v1/previsions/{service}`, avec intervalles de prédiction à 80 % |

Les appels API sont mis en cache une heure (`@st.cache_data(ttl=3600)`) pour limiter les requêtes vers Render. L'interface intègre des mesures d'accessibilité WCAG / RGAA (alternatives textuelles aux graphiques, motifs de hachure en complément de la couleur, focus visible, attribut `lang="fr"`).

**Déploiement :** l'application est hébergée sur Streamlit Cloud. Les secrets (identifiants bcrypt, URL et clé de l'API) sont injectés via le gestionnaire de secrets intégré de la plateforme — aucun identifiant n'est présent dans le dépôt.

---

## 11. Intégration continue — GitHub Actions

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

## 12. Sécurité

| Mesure | Implémentation |
|---|---|
| Chiffrement en transit | HTTPS/TLS natif sur Supabase, Render et Streamlit Cloud |
| Gestion des secrets | `variable.env` local (hors dépôt) + GitHub Secrets (CI) + Streamlit Secrets + variables Render (prod) |
| Hachage des mots de passe | `bcrypt` — les mots de passe ne sont jamais stockés en clair |
| Authentification application | Page de login obligatoire avant tout accès, contrôle d'accès par rôle (directeur / gestionnaire) |
| Authentification API | Clé `X-API-Key` vérifiée en temps constant (`secrets.compare_digest`) sur l'endpoint d'écriture |
| CORS | Origines restreintes à l'URL Streamlit Cloud de production |
| Isolation des schémas | Trois schémas PostgreSQL étanches — aucune requête ne traverse les frontières de schéma |

---

## 13. Tests automatisés

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

## 14. Perspectives d'évolution

| Axe | Description | Complexité |
|---|---|---|
| **OAuth 2.0** | Remplacer la clé API statique par des tokens à durée de vie limitée (FastAPI `OAuth2PasswordBearer` / Supabase Auth) pour ouvrir l'API à des consommateurs tiers | Moyenne |
| **Endpoint `/historique`** | Raccorder `dashboard.py` à l'API pour éliminer le dernier accès SQL direct depuis l'interface | Faible |
| **Alertes automatiques** | Notifier le Directeur par email (SMTP) quand les prévisions détectent un risque de rupture de stock | Faible |
| **Tests de non-régression** | Étendre la suite pytest avec des tests d'intégration vérifiant le round-trip ETL complet contre une base de test dédiée | Moyenne |
| **Monitoring du modèle** | Mesurer la dérive du modèle (MAE, MAPE) après chaque réentraînement mensuel et logger les métriques en base | Moyenne |
| **Git LFS / DVC** | Délocaliser les artefacts binaires `.pkl` hors de l'historique Git tout en conservant la traçabilité des versions | Faible |

---

*Projet réalisé dans le cadre d'un stage de Licence IA & Data Science — 2025/2026.*
