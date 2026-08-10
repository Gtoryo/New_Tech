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
| CI/CD | GitHub Actions | — | Réentraînement mensuel automatisé + keep-alive Supabase |
| Tests | pytest | 8.3.5 | Tests unitaires (ETL, Prophet) et d'intégration (API) |

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
├── ruff.toml                   # Configuration de l'analyse statique (PEP 8, imports)
├── variable.env                # Variables d'environnement locales (non commité)
│
├── sql/                        # Schéma exécutable, idempotent, fidèle à la production
│   ├── 01_schemas.sql          # Les trois schémas logiques
│   ├── 02_tables.sql           # Tables, types bornés, contraintes et index
│   └── 03_contraintes_unicite.sql # Index uniques sur LOWER(...) — requis par l'API
│
├── generated_data/
│   └── generate_data.py        # Générateur du jeu de travail (graines fixes)
│
├── src/                        # Pipeline ETL — couches séparées
│   ├── db.py                   # Fabrique de moteur SQLAlchemy partagée (DRY)
│   ├── extract.py              # Lecture des 3 fichiers Excel → DataFrames bruts
│   ├── transform.py            # Nettoyage, typage, normalisation
│   ├── load.py                 # Chargement schema_brut + schema_analytics
│   └── aggregate.py            # Agrégation schema_analytics → schema_ia
│
├── model/
│   ├── train.py                # Entraînement Prophet + push prévisions en BDD
│   ├── predict.py              # Client API — GET prévisions (httpx + cache Streamlit)
│   ├── evaluate.py             # Cross-validation MAE/MAPE/Coverage + RelMAE
│   └── monitor.py              # Surveillance de dérive après réentraînement
│
├── models/                     # Modèles sérialisés (.pkl) — versionnés dans Git
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
├── data/                       # Jeu de travail synthétique — versionné volontairement
│   ├── ventes_historiques.xlsx
│   ├── depenses_et_achats.xlsx
│   └── suivi_clients_prospects.xlsx
│
├── tests/                      # Suite de tests automatisés — 103 tests
│   ├── test_transform.py       # 36 unitaires — couche Transform
│   ├── test_api.py             # 29 d'intégration API (sans base de données)
│   ├── test_model.py           # 14 unitaires — entraînement Prophet
│   ├── test_dashboard.py       # 8 unitaires — agrégation mensuelle des prévisions
│   └── test_integration_pipeline.py # 16 d'intégration ETL sur PostgreSQL
│
├── info_projet/                # Documentation de cadrage
│   ├── MPR.md                  # Rapport de cadrage métier (contexte + vision)
│   └── Architecture.md         # Document d'architecture technique
│
└── .github/
    └── workflows/
        ├── tests.yml               # Lint + suite complète à chaque push et PR
        ├── retrain_prophet.yml     # Workflow CI/CD — réentraînement mensuel
        └── keep_alive_supabase.yml # Ping tous les 4 jours — évite la mise en veille
```

---

## 5. Schéma de base de données

La base de données est organisée en **trois schémas PostgreSQL étanches**, chacun ayant une responsabilité unique dans le cycle de vie de la donnée.

> **`sql/` décrit la production à l'identique.** Les types, longueurs, obligatoriété, valeurs par défaut, contraintes d'unicité et index ont été relevés sur l'instance Supabase en service, puis recopiés dans `sql/02_tables.sql`. Un repreneur qui applique les trois fichiers sur une base vierge obtient exactement le schéma qui tourne — et non une variante permissive dans laquelle une donnée refusée en production passerait sans bruit. La conformité est vérifiable : comparer `information_schema.columns` et `pg_constraint` entre les deux bases donne 82 colonnes, 25 contraintes et 3 index identiques.

### `schema_brut` — Archive des données brutes

Reçoit les données Excel à l'état natif, sans transformation. Permet de rejouer le pipeline en cas d'erreur.

| Table | Description |
|---|---|
| `ventes_raw` | Lignes de ventes brutes (toutes anomalies préservées) |
| `depenses_raw` | Achats fournisseurs bruts |
| `clients_raw` | Référentiel clients brut |

### `schema_analytics` — Données propres pour la BI

Données nettoyées, normalisées en 3NF, alimentant le tableau de bord Streamlit.

| Table | Colonnes principales | Contrainte notable |
|---|---|---|
| `client` | `id_client` PK, `nom_client` (150), `entreprise` (150), `telephone` (20), `email` (100), `ville` (100) | unique sur `LOWER(nom_client)` |
| `employe` | `id_employe` PK, `nom_employe` (150) | unique sur `LOWER(nom_employe)` |
| `service` | `id_service` PK, `libelle` (50) — Sérigraphie, Imprimerie, Vidéosurveillance, Maintenance | `UNIQUE (libelle)` |
| `facture` | `id_facture` (20) PK, `date_facture`, `statut_paiement` (20), `id_client` FK, `id_employe` FK | `id_employe` **nullable** — 4 % des factures n'ont pas d'employé assigné |
| `ligne_facture` | `id_ligne` PK, `description` (255), `quantite`, `prix_unitaire`, `total_ligne`, `id_facture` FK, `id_service` FK | `prix_unitaire` **nullable** — 90 lignes sans prix unitaire renseigné |
| `fournisseur` | `id_fournisseur` PK, `nom` (150) | `UNIQUE (nom)` |
| `categorie_achat` | `id_categorie` PK, `libelle` (50) | `UNIQUE (libelle)` |
| `achat` | `id_achat` PK, `date_achat`, `libelle_article` (255), `quantite`, `prix_achat_total`, `mode_paiement` (30), `id_fournisseur` FK, `id_categorie` FK | seul `mode_paiement` est nullable |

Les longueurs entre parenthèses sont les bornes `VARCHAR`. Elles ne sont pas décoratives : les contrats Pydantic de l'API portent les **mêmes** limites (`api/schemas.py`), de sorte qu'une saisie hors gabarit est rejetée en `422` avec le nom du champ fautif, au lieu de partir en base et de revenir en erreur serveur.

Les montants sont des `INTEGER` : le FCFA n'a pas de subdivision en usage, et le type plafonne à 2 147 483 647, très au-dessus du plus gros montant observé (960 000 FCFA sur une ligne). Les cumuls ne débordent pas davantage, PostgreSQL promouvant `SUM(INTEGER)` en `BIGINT`.

### `schema_ia` — Séries temporelles pour Prophet

Données agrégées au format natif Prophet (`ds` = date, `y` = valeur), alimentant l'entraînement du modèle.

| Table | Colonnes | Description |
|---|---|---|
| `serie_ventes_journalieres` | `id_serie`, `ds`, `y`, `nb_commandes`, `rafraichi_le` | CA global par jour — `UNIQUE (ds)` |
| `serie_ventes_par_service` | `id_serie`, `ds`, `y`, `service`, `nb_commandes`, `rafraichi_le` | CA par jour et par pôle — `UNIQUE (ds, service)` |
| `previsions_prophet` | `id`, `service`, `ds`, `yhat`, `yhat_lower`, `yhat_upper`, `genere_le` | Prévisions 180 jours (lues par l'API) — index sur `(service, ds)` |

Les deux contraintes d'unicité sur `ds` verrouillent la propriété que produit l'agrégation SQL : une observation par jour, une par couple jour-pôle. Un `GROUP BY` altéré par mégarde dupliquerait des dates, Prophet s'entraînerait sur une série gonflée, et rien ne le signalerait.

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

### Jeu de travail et reproductibilité

L'historique commercial réel de l'entreprise n'a pas pu quitter le poste de la Gestionnaire : sa sortie n'était pas autorisée. Le projet travaille donc sur un **jeu de données synthétique**, produit par un générateur paramétré à partir des particularités relevées lors du cadrage métier — formats de dates hétérogènes, fautes de frappe sur les libellés de service, doublons de factures, montants sentinelles et négatifs, variantes orthographiques de noms de villes.

Les trois classeurs sont versionnés dans `data/`, ainsi que le générateur qui les produit. Les graines aléatoires étant fixes, une régénération reproduit les mêmes fichiers :

```bash
# Régénère data/*.xlsx à l'identique (à lancer depuis la racine du projet)
python generated_data/generate_data.py
```

| Fichier | Lignes | Anomalies injectées |
|---|---:|---|
| `ventes_historiques.xlsx` | 3 001 | 142 doublons `Facture_ID` (4,7 %), 121 montants sentinelles à 0, 4 formats de date, 16 variantes de libellés de service |
| `depenses_et_achats.xlsx` | 401 | 8 montants négatifs, 8 lignes vides |
| `suivi_clients_prospects.xlsx` | 47 | 6 variantes orthographiques de « Pointe-Noire », doublons en casse mixte |

> Les volumes, saisonnalités et gammes de prix sont calibrés sur l'activité du pôle Imprimerie & Sérigraphie telle qu'observée pendant le stage. Les taux d'anomalies ci-dessus sont ceux du jeu livré, mesurables directement sur les fichiers — ce sont aussi, par construction, les paramètres d'injection du générateur : ce ne sont pas les résultats d'un diagnostic statistique sur un export de production.

> **Une limitation du générateur, assumée.** Le tirage de la forme du montant non calculé (`0`, `999` ou valeur absente) est évalué une seule fois pour l'ensemble des lignes concernées, et non ligne par ligne. Avec la graine fixée à 42, il tombe sur `0` : le jeu livré ne porte donc que cette forme. Les deux autres restent traitées par `_SENTINELLES_TOTAL` (`src/transform.py`) au titre de la programmation défensive et couvertes par `tests/test_transform.py` sur des DataFrames construits pour l'occasion. Le comportement n'est pas corrigé : régénérer le jeu déplacerait chaque métrique publiée dans le rapport et romprait l'ancrage au tag `metriques-rapport-v1`.

### Exécution

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

`model/evaluate.py` exécute une cross-validation à fenêtre croissante (`initial=365j`, `period=30j`, `horizon=90j`) sur le modèle global et produit quatre tableaux :

1. **MAE / MAPE / Coverage par horizon** (30, 60 et 90 jours) ;
2. **Erreur selon la granularité de décision** — l'erreur est recalculée après agrégation des prévisions au jour, à la semaine et au mois. Le MAPE journalier, élevé du fait de la forte dispersion de la série, chute fortement une fois les prévisions agrégées : c'est à l'échelle hebdomadaire et mensuelle, celle à laquelle les réapprovisionnements sont décidés, que la prévision est réellement exploitable ;
3. **Comparaison à des prévisions de référence (RelMAE)** — Prophet est confronté à un naïf saisonnier (J-7) et à la moyenne de l'historique disponible, sur les mêmes points de coupure et **à information strictement égale** : les deux références sont bornées aux observations antérieures au point de coupure, comme le modèle. Un MAPE lu isolément ne dit rien de la valeur ajoutée d'un modèle ; un RelMAE inférieur à 1 établit qu'il capture une structure que la prévision naïve ne reproduit pas. La mesure est un RelMAE (*relative mean absolute error*) et non le MASE d'Hyndman & Koehler (2006), qui met l'erreur à l'échelle de l'erreur naïve calculée **dans l'échantillon d'entraînement** : même interprétation du seuil, dénominateur différent ;
4. **Comparaison de `changepoint_prior_scale`** (0.01 / 0.05 / 0.50) — la valeur 0.05 retenue minimise le MAPE.

### Reproduire les métriques publiées dans le rapport

Les modèles sont réentraînés le 1er de chaque mois par GitHub Actions : les métriques évoluent avec eux, ce qui est le comportement attendu d'un système en production. Les valeurs citées dans le rapport de stage sont donc **ancrées à une version de modèle**, identifiée par un tag Git.

```bash
# Restaure les modèles sur lesquels les métriques du rapport ont été mesurées
git checkout metriques-rapport-v1 -- models/

python model/evaluate.py    # section 4.3 du rapport
python model/monitor.py     # section 5.2 du rapport

# Revenir aux modèles courants
git checkout HEAD -- models/
```

> Le tag épingle les **modèles**, pas les scripts : une correction apportée à `evaluate.py` ou `monitor.py` change légitimement les valeurs produites sur ces mêmes modèles. C'est arrivé une fois, et le rapport en tient compte — voir la note de méthode de la section 4.3 sur le bornage des prévisions de référence au point de coupure.

Les deux scripts fixent la graine du générateur aléatoire (`SEED = 42`) : Prophet échantillonnant les bornes d'intervalle via le générateur global de numpy, deux exécutions sur les mêmes modèles produisent sans cela des valeurs de coverage différentes. Avec la graine, les chiffres sont strictement reproductibles.

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
| GET | `/api/v1/previsions/{service}` | `X-API-Key` | Prévisions Prophet pré-calculées (`global`, `Imprimerie`, `Sérigraphie`, `Maintenance`, `Vidéosurveillance`) |
| POST | `/api/v1/commandes/` | `X-API-Key` | Enregistre une commande — transaction atomique : upsert client + upsert employé + insertion facture + ligne_facture |
| GET | `/api/v1/kpis/` | `X-API-Key` | CA total, nombre de commandes, CA moyen journalier, pôle leader |

> **Lecture et écriture sont authentifiées de la même façon.** Les prévisions de chiffre d'affaires et les KPI agrégés sont des données commerciales : les exposer en lecture libre reviendrait à publier l'activité de la PME à qui connaît l'URL de l'instance, ce que l'OWASP API Security Top 10 classe en **API2:2023 — Broken Authentication**. Seul `/health` reste ouvert, puisque sa fonction est d'être interrogeable sans identification.

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

> **Cold start :** sur le plan gratuit, l'instance s'endort après 15 minutes d'inactivité et met jusqu'à **~50 secondes** à redémarrer. Les clients httpx configurent un timeout de **60 s** pour absorber ce délai ; côté dashboard, l'appel de prévision est de plus **différé** (déclenché uniquement au moment d'afficher la courbe) afin que les indicateurs et graphiques historiques restent immédiatement disponibles pendant le réveil. Le passage à un plan payant supprimerait cette latence.

### Sécurité de l'API

- **Authentification** : tous les endpoints métier — écriture comme lecture — exigent une clé secrète dans l'en-tête `X-API-Key`, vérifiée **en temps constant** (`secrets.compare_digest`) contre la variable d'environnement `API_SECRET_KEY` — clé stockée dans les variables Render côté serveur et les secrets Streamlit côté client. La dépendance FastAPI (`Depends(verifier_cle_api)`) s'exécute avant toute logique métier : une requête sans clé est rejetée en `401`, pas en `422`.
- **CORS** : origines restreintes à l'URL Streamlit Cloud de production, méthodes limitées à GET/POST.
- **Messages d'erreur non divulgants** : aucun détail technique n'est renvoyé au client. Les exceptions de la couche d'accès aux données sont journalisées côté serveur via `logger.exception` et la réponse HTTP ne contient qu'un message générique — un message SQLAlchemy brut exposerait sinon le schéma, les tables, la requête émise et parfois l'hôte de la base (OWASP API8:2023 — Security Misconfiguration).
- **Écritures atomiques** : l'enregistrement d'une commande s'exécute dans une transaction unique (`engine.begin()`), et les upserts client/employé s'appuient sur `INSERT … ON CONFLICT … RETURNING` adossé aux index uniques `ux_client_nom_lower` et `ux_employe_nom_lower`. Deux saisies concurrentes pour un même client inconnu ne peuvent donc pas créer de doublon.

---

## 10. Application Streamlit

```bash
streamlit run streamlit_app.py
```

L'application expose trois vues, routées selon le rôle de l'utilisateur authentifié (`streamlit_app.py` consulte `st.session_state["role"]` à chaque rechargement) :

| Vue | Utilisateur | Contenu |
|---|---|---|
| **Connexion** | — | Authentification par `bcrypt`, attribution du rôle (directeur / gestionnaire) |
| **Tableau de bord** | Directeur | KPIs Plotly (CA total, commandes, CA moyen, pôle leader), évolution mensuelle empilée, répartition par pôle, et **section de prévision Prophet** alimentée par `GET /api/v1/previsions/{service}` (intervalle de prédiction à 80 %). Horizon réglable de 30 à 180 jours (défaut 90) ; historique et prévision sont affichés à la **granularité mensuelle** pour rester à la même échelle |
| **Saisie** | Gestionnaire | Formulaire de commandes — envoi à l'API via `POST /api/v1/commandes/` (authentifié `X-API-Key`) |

Les appels API sont mis en cache une heure (`@st.cache_data(ttl=3600)`) pour limiter les requêtes vers Render. **Seules les réponses réussies sont mises en cache** : un échec transitoire (cold start) lève une exception, que le cache ne mémorise pas, et il est donc réessayé au rechargement suivant plutôt que figé pendant une heure. L'interface intègre des mesures d'accessibilité WCAG / RGAA (alternatives textuelles aux graphiques, motifs de hachure en complément de la couleur, focus visible, attribut `lang="fr"`).

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
6. Agrégation schema_analytics → schema_ia (intègre les commandes saisies via l'API)
7. Réentraînement Prophet + push des prévisions en BDD
8. Commit automatique des modèles .pkl mis à jour
9. Surveillance de la dérive (model/monitor.py) — qualifie la publication, ne la bloque pas
```

> **Pourquoi l'étape 9 après le commit et non avant ?** Sur une structure de cette taille, mieux vaut
> des prévisions dégradées et signalées que pas de prévisions du tout : le Directeur conserve une
> projection, et l'exploitant sait qu'elle mérite un regard. Le contrôle qualifie la publication.
> Un dépassement de seuil sur le modèle **global** passe le run au rouge et déclenche la notification
> GitHub ; sur un modèle **par pôle**, il n'émet qu'un avertissement — ces séries sont plus courtes et
> plus bruitées, un dépassement isolé n'y vaut pas arrêt du système.

> **Pourquoi l'étape 6 et pas le pipeline ETL complet ?** `charger_analytics()` vide les tables
> (`TRUNCATE ... CASCADE`) avant de les recharger depuis les fichiers Excel. Exécuter `main.py`
> en CI effacerait donc toutes les commandes enregistrées via l'API depuis le déploiement. Seule
> l'agrégation est rejouée : elle lit `schema_analytics` — historique **et** nouvelles commandes —
> et reconstruit les séries temporelles sans rien détruire.

Les secrets de connexion à Supabase (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) sont stockés dans GitHub Secrets — jamais en clair dans le code.

### Second workflow — `keep_alive_supabase.yml`

Le plan gratuit Supabase met un projet en veille après **7 jours sans activité**. Le réentraînement
n'ayant lieu qu'une fois par mois, la base serait systématiquement endormie au moment où le workflow
se déclenche — le job du 01/08/2026 a échoué ainsi, sur un `FATAL (ENOTFOUND) tenant/user not found`
renvoyé par le pooler.

`keep_alive_supabase.yml` exécute un `SELECT 1` **tous les 4 jours** (jours 1, 5, 9… 29 du mois).
L'écart est de 4 jours à l'intérieur du mois, et de 2 à 5 jours au passage d'un mois à l'autre selon
sa longueur — le pire cas étant février, du 25 au 1er mars. Tous ces cas restent sous la fenêtre de
mise en veille de 7 jours. Le dashboard Streamlit et l'API Render, qui lisent la même base, en
bénéficient également.

> **Attention :** GitHub désactive les workflows planifiés après 60 jours sans activité dans le dépôt.
> Passé ce délai, le keep-alive s'arrête et le projet Supabase repart en veille.

### Troisième workflow — `tests.yml`

Le réentraînement mensuel valide le code avant d'écrire en base, mais une régression poussée le 3 du
mois ne serait détectée que le 1er du suivant. `tests.yml` ramène ce délai à quelques minutes : à
chaque push sur `main` et à chaque pull request, il exécute l'analyse statique (`ruff check .`), puis
la suite complète — avec un **service PostgreSQL éphémère** qui permet aux 16 tests d'intégration du
pipeline de s'exécuter — et publie les deux rapports de couverture, sur `src/` et sur `api/`.

L'analyse statique est placée **avant** les tests : une erreur de style ou un import mort se détecte
en quelques secondes, là où la suite complète demande plusieurs minutes, compilation de CmdStan
comprise.

---

## 12. Sécurité

| Mesure | Implémentation |
|---|---|
| Chiffrement en transit | HTTPS/TLS natif sur Supabase, Render et Streamlit Cloud |
| Gestion des secrets | `variable.env` local (hors dépôt) + GitHub Secrets (CI) + Streamlit Secrets + variables Render (prod) |
| Hachage des mots de passe | `bcrypt` — les mots de passe ne sont jamais stockés en clair |
| Authentification application | Page de login obligatoire avant tout accès, contrôle d'accès par rôle (directeur / gestionnaire) |
| Authentification API | Clé `X-API-Key` vérifiée en temps constant (`secrets.compare_digest`) sur **tous les endpoints métier**, lecture comprise — seul `/health` reste ouvert |
| Anti-énumération des comptes | Le login vérifie systématiquement un hash bcrypt, celui d'un leurre de même facteur de coût lorsque l'identifiant n'existe pas : les deux chemins consomment un temps équivalent |
| CORS | Origines restreintes à l'URL Streamlit Cloud de production |
| Isolation des schémas | Trois schémas PostgreSQL étanches — aucune requête ne traverse les frontières de schéma |

---

## 13. Tests automatisés

```bash
# Analyse statique (PEP 8, imports, pièges courants) — configuration : ruff.toml
ruff check .

# Suite sans infrastructure — 87 tests, les 16 tests d'intégration sont ignorés
pytest tests/ -v

# Suite complète — 103 tests, en faisant pointer les variables DB_* vers
# n'importe quel PostgreSQL jetable dont le nom de base contient « test »
NEWTECH_INTEGRATION=1 DB_HOST=localhost DB_PORT=5432 DB_USER=test \
DB_PASSWORD=test DB_NAME=newtech_test DB_SSLMODE=disable pytest tests/ -v
```

> **Aucun moteur n'est à installer pour exécuter la suite complète.** Les 16 tests
> d'intégration ont pour seule dépendance un PostgreSQL jetable, et la voie de
> référence est le **service déclaré dans `.github/workflows/tests.yml`** : GitHub
> Actions le démarre avec le job et le détruit à la fin. La suite complète tourne
> donc à chaque push, et les deux rapports de couverture y sont publiés.
>
> Cela ne contredit pas l'arbitrage documenté en ADR-02 (*Renoncer à Docker*), qui
> porte sur la **conteneurisation de l'application** : image à construire, registry
> à maintenir, orchestration et exposition de ports. Ici, rien de tout cela — une
> base de test déclarée en cinq lignes de YAML, fournie et détruite par la
> plateforme d'intégration continue. La commande ci-dessus n'est qu'une commodité
> pour qui dispose déjà d'un PostgreSQL local.

| Fichier | Tests | Ce qui est vérifié |
|---|---|---|
| `tests/test_transform.py` | 36 | `parser_date` (4 formats), `normaliser_service`, `normaliser_ville`, `transformer_ventes` (doublons, recalcul des trois formes de montant non calculé — sentinelle `0`, sentinelle `999`, valeur absente — sur des DataFrames construits pour l'occasion, le jeu de travail versionné ne portant que la forme `0`), `transformer_depenses` (montants négatifs, déduplication des référentiels), `transformer_clients` (déduplication insensible à la casse, conservation de la casse mixte, normalisation des villes) |
| `tests/test_api.py` | 29 | **Intégration API** — routage, authentification `X-API-Key` sur l'écriture **et sur les deux endpoints de lecture** (401 sur clé absente ou invalide), ouverture maintenue de `/health`, validation Pydantic (422 sur libellé hors référentiel et contraintes métier), bornes de l'horizon, **bornes de longueur alignées sur les colonnes VARCHAR** (422 au-delà, accepté à la limite exacte), exposition du schéma OpenAPI. Exécutés via `TestClient`, sans serveur ni base |
| `tests/test_model.py` | 14 | `slugify`, entraînement Prophet end-to-end, colonnes de sortie, horizon 180 jours, écrêtage à zéro des prévisions négatives |
| `tests/test_dashboard.py` | 8 | Agrégation mensuelle des prévisions — la prévision centrale s'additionne, la demi-largeur de l'intervalle croît en **√n** et non linéairement (test de non-régression explicite contre la somme des bornes), écrêtage à zéro de la borne basse, écartement des mois partiels en bord d'horizon |
| `tests/test_integration_pipeline.py` | 16 | **Intégration ETL sur PostgreSQL** — intégrité référentielle après résolution des clés étrangères, préservation des anomalies dans `schema_brut`, idempotence du rechargement et de l'agrégation, conservation du chiffre d'affaires entre `schema_analytics` et `schema_ia`, `COUNT(DISTINCT)` sur les factures |

**Couverture mesurée** (`pytest --cov`) : **99 %** sur `src/` (262 instructions, 261 couvertes) — `transform`, `extract`, `load` et `db` à **100 %**, `aggregate` à 97 % — et **69 %** sur `api/` (126 instructions, 87 couvertes), dont 100 % sur `auth`, `schemas` et `main`.

La seule ligne non couverte de `src/` est l'appel `alimenter_series()` du garde `if __name__ == "__main__"` de `src/aggregate.py` : c'est le point d'entrée en ligne de commande, invoqué par le workflow de réentraînement (`python src/aggregate.py`) et non par pytest. Les taux plus faibles des modules de routes correspondent aux corps de requêtes SQL, qui ne s'exécutent que face à une base réelle : les cas couverts ici sont ceux rejetés en amont de toute requête (401, 422).

Les deux rapports sont republiés à chaque exécution du workflow `tests.yml`, ce qui évite qu'ils dérivent du code.

Les couches Extract, Load et Aggregate écrivent toutes en base : leur comportement réel — résolution des clés étrangères, respect des contraintes d'intégrité, idempotence du `TRUNCATE + INSERT`, exactitude des requêtes d'agrégation — ne peut se vérifier que face à un vrai moteur. Elles sont donc testées contre un PostgreSQL éphémère plutôt qu'émulées : un conteneur coûte moins cher qu'une couche d'abstraction, et teste le moteur réellement utilisé en production.

> **Garde-fous.** Ces tests exécutent des `TRUNCATE`. Ils sont ignorés tant que `NEWTECH_INTEGRATION=1` n'est pas positionné, et refusent de s'exécuter si `DB_HOST` désigne un hôte hébergé ou si `DB_NAME` ne contient pas « test ».

`conftest.py` à la racine ajoute le projet au `sys.path` pour que les imports fonctionnent sans installation en mode développement.

---

## 14. Perspectives d'évolution

| Axe | Description | Complexité |
|---|---|---|
| **OAuth 2.0** | Remplacer la clé API statique par des tokens à durée de vie limitée (FastAPI `OAuth2PasswordBearer` / Supabase Auth) pour ouvrir l'API à des consommateurs tiers | Moyenne |
| **Endpoint `/historique`** | Raccorder `dashboard.py` à l'API pour éliminer le dernier accès SQL direct depuis l'interface | Faible |
| **Alertes automatiques** | Notifier le Directeur par email (SMTP) quand les prévisions détectent un risque de rupture de stock | Faible |
| **Saisie multi-lignes** | Permettre plusieurs prestations sur une même facture — `ligne_facture` le supporte déjà, l'évolution porte sur le contrat `CommandeIn` et l'ergonomie du formulaire (aucune modification du schéma) | Faible |
| **Surveillance du volume saisi** | `model/monitor.py` mesure la qualité des prévisions, pas celle des données entrantes : un effondrement du nombre de commandes enregistrées ne déclencherait aucune alerte. La colonne `nb_commandes` de `schema_ia` porte déjà l'information | Faible |
| **RelMAE lissé sur trois fenêtres** | La surveillance repose sur une fenêtre de validation unique : un mois atypique suffit à faire varier l'indicateur sans dérive réelle. Une moyenne glissante sur les trois dernières fenêtres donnerait un signal plus stable | Faible |
| **Destinataire interne des alertes** | Les notifications d'échec GitHub Actions n'atteignent aujourd'hui que l'auteur du dépôt ; elles doivent être redirigées vers l'entreprise à la reprise du projet | Faible |
| **Réactivation des workflows planifiés** | GitHub Actions désactive les workflows `schedule` après 60 jours sans activité sur le dépôt. Sans commit ni réactivation manuelle, le réentraînement mensuel s'arrête de lui-même : à documenter dans la notice de reprise | Faible |
| **Tests d'interface (Playwright)** | La suite couvre la logique métier, pas le rendu : une régression Plotly viderait un graphique sans qu'aucun test ne le signale | Moyenne |
| **Git LFS / DVC** | Délocaliser les artefacts binaires `.pkl` hors de l'historique Git tout en conservant la traçabilité des versions | Faible |

---

*Projet réalisé dans le cadre d'un stage de Licence IA & Data Science — 2025/2026.*
