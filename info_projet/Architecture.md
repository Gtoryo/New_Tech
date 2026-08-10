## Partie 2 : Architecture Technique, Automatisation et Sécurité

### 2.1 Architecture globale du pipeline de données
Le projet adopte une architecture en couches étanches, permettant la transition de la donnée brute vers la donnée prédictive :

$$\text{1. Ingestion (Script Python)} \longrightarrow \text{2. Base Cloud (Supabase)} \longrightarrow \text{3. Pipeline IA \& BI} \longrightarrow \text{4. API REST (FastAPI)} \longrightarrow \text{5. Application (Streamlit)}$$

* **Couche Ingestion (ETL) :** Un script Python nettoie l'historique des fichiers Excel actuels (gestion des doublons, formats de dates, valeurs manquantes) pour injecter une donnée saine dans le nouveau système.  
* **Couche Stockage (Data Warehouse) :** Une base PostgreSQL est segmentée en trois schémas logiques pour garantir la propreté du cycle de vie de la donnée :  
  * `schema_brut` : Stockage des données d'ingestion à l'état natif.  
  * `schema_analytics` : Tables agrégées et nettoyées pour les calculs de KPI métiers.  
  * `schema_ia` : Tables formatées en séries temporelles destinées à l'entraînement du modèle.  

### 2.2 Choix technologiques et Modélisation IA
* **Modèle IA (Séries Temporelles) :** Utilisation de l'algorithme **Prophet** (développé par Meta). Ce modèle est idéal pour les PME car il gère de manière robuste les fortes saisonnalités (pics de ventes liés aux fêtes, rentrées scolaires ou événements locaux) et tolère les trous dans les données historiques.  
* **Couche de service (API REST) :** Une API **FastAPI**, déployée sur **Render**, expose les prévisions pré-calculées (`GET /api/v1/previsions/{service}`) et reçoit les nouvelles commandes (`POST /api/v1/commandes/`, authentifié par clé API). Cette couche découple l'interface utilisateur de la base de données : aucun module client n'exécute de SQL pour ces opérations.  
* **Interface Web et BI :** Utilisation du framework **Streamlit** (Python). Il permet de construire rapidement l'interface de saisie pour la gestionnaire, les graphiques interactifs (via la bibliothèque *Plotly*) pour le directeur, et d'afficher les courbes de prévisions générées par le modèle Prophet.  

### 2.3 Hébergement et industrialisation — arbitrage Docker
La conteneurisation **Docker** avait été envisagée initialement pour garantir la portabilité de l'environnement (image `python:3.10-slim`). Cette approche a été **écartée** après analyse : pour deux utilisateurs et des plateformes d'hébergement managées, la charge de gestion d'un conteneur (registry, orchestration, exposition de port) était injustifiée. La solution retenue s'appuie sur trois services cloud à déploiement natif depuis GitHub : **Streamlit Cloud** (interface), **Render** (API REST) et **Supabase** (base de données). La version Python est fixée à 3.11 (`runtime.txt`) sur l'ensemble des environnements.  

### 2.4 Automatisation et Orchestration
L'entreprise continue de générer de l'activité au quotidien. Pour que le modèle d'IA reste performant, son réentraînement est automatisé :  
* **Orchestration :** Un workflow *GitHub Actions* (`retrain_prophet.yml`) s'exécute le 1er de chaque mois à 02h00 UTC (cron `0 2 1 * *`). Il valide d'abord la suite de tests pytest, puis réentraîne les modèles Prophet sur les données les plus récentes et pousse les prévisions à 180 jours dans `schema_ia.previsions_prophet`, sans aucune action humaine. Les nouvelles commandes saisies via l'application alimentent la base en continu à travers l'API.  

### 2.5 Stratégie de Sécurité
Les données financières d'une entreprise exigeant une confidentialité absolue, les barrières de sécurité suivantes sont implémentées :  
* **Chiffrement :** Utilisation des protocoles HTTPS/TLS pour sécuriser les données en transit entre l'application et les serveurs de la base de données.  
* **Gestion des Secrets :** Les clés privées et identifiants de connexion ne sont jamais stockés dans le code source — injection via les secrets Streamlit Cloud (interface), les variables d'environnement Render (API) et les GitHub Secrets (CI).  
* **Protection des accès (Authentification) :** L'accès à l'application web est protégé par une page de Login. Les mots de passe du Directeur et de la Gestionnaire sont hachés à l'aide de l'algorithme `bcrypt` et stockés dans les secrets de la plateforme, empêchant toute lecture en clair même en cas de fuite.  
* **Sécurisation de l'API :** L'endpoint d'écriture exige une clé secrète dans l'en-tête `X-API-Key`, vérifiée en temps constant côté serveur ; la politique CORS restreint les origines autorisées à l'URL de production Streamlit Cloud.
---

## Partie 3 : Décisions d'architecture (ADR)

Chaque décision structurante est consignée au format ADR — contexte, options
envisagées, décision, conséquences assumées. L'objectif est qu'un développeur
reprenant le projet comprenne *pourquoi* il est bâti ainsi, et sache ce qu'il
casserait en revenant sur un choix.

### ADR-01 — Trois schémas PostgreSQL étanches plutôt qu'un schéma unique

**Contexte.** Les données traversent trois états : brutes issues des classeurs
Excel, nettoyées et normalisées, agrégées en séries temporelles.

**Options.** (a) Un schéma unique avec des préfixes de table. (b) Trois bases
distinctes. (c) Trois schémas logiques dans une même base.

**Décision.** Option (c). Les préfixes ne sont qu'une convention de nommage, que
rien n'empêche de contourner. Trois bases distinctes interdiraient les jointures
entre couches et multiplieraient les connexions sur un plan gratuit qui les
limite.

**Conséquences.** Chaque module Python n'écrit que dans un schéma, ce qui rend la
frontière vérifiable. En cas d'erreur de transformation, `schema_brut` permet de
rejouer sans revenir aux fichiers sources. En contrepartie, la création de la
base exige un script d'initialisation ordonné (`sql/01_schemas.sql`).

### ADR-02 — Renoncer à Docker

**Contexte.** Le cadrage initial prévoyait de conteneuriser l'environnement
(`python:3.10-slim`) pour verrouiller la reproductibilité.

**Options.** (a) Docker avec registry et orchestration. (b) Plateformes managées
à déploiement natif depuis GitHub.

**Décision.** Option (b) : Streamlit Cloud, Render et Supabase. Pour deux
utilisateurs, l'outillage à maintenir dépassait le bénéfice attendu.

**Conséquences.** Plus aucune image à construire ni à héberger, mais la
reproductibilité repose désormais sur `runtime.txt` (Python 3.11 partout) et sur
des fichiers de dépendances distincts par cible. La leçon dépasse la décision :
l'architecture avait été dimensionnée sur ce que je voulais apprendre, pas sur ce
que la PME allait réellement utiliser.

**Portée de la décision.** Elle vise la conteneurisation de l'**application** :
image à construire, registry à maintenir, orchestration, exposition de ports.
Elle ne vise pas la base de test éphémère des tests d'intégration (cf. ADR-05),
déclarée en cinq lignes de YAML et fournie puis détruite par GitHub Actions.
Aucun moteur de conteneurs n'est installé sur un poste de développement, aucune
image n'est construite ni publiée, et le projet ne dépend d'aucun runtime de
conteneur pour être exécuté, déployé ou repris.

### ADR-03 — Précalculer les prévisions en base plutôt que charger le modèle à la demande

**Contexte.** Streamlit Cloud plafonne à environ 1 Go de mémoire sur son offre
gratuite. Prophet et CmdStanPy en mobilisent plusieurs centaines à eux seuls, et
la chaîne de compilation Stan est hors de portée sur un environnement sans droits
d'administration.

**Options.** (a) Charger le `.pkl` dans l'application et appeler `predict()` à
chaque affichage. (b) Calculer les prévisions au réentraînement mensuel et les
persister dans `schema_ia.previsions_prophet`.

**Décision.** Option (b). Au-delà de la contrainte mémoire, les deux opérations
n'ont pas le même rythme : calculer coûte cher et se fait une fois par mois,
consulter est léger et quotidien. Les mélanger soude le workflow CI/CD à
l'application utilisateur alors que rien ne les oblige à évoluer ensemble.

**Conséquences.** L'application ne dépend ni de Prophet ni de SQLAlchemy pour
afficher une prévision — un simple appel HTTP suffit. En contrepartie, les
prévisions affichées datent au plus du dernier réentraînement, ce qui impose de
ne renvoyer que les dates futures (`WHERE ds >= CURRENT_DATE`). Ce patron porte un
nom en MLOps, le *prediction store*, mais il a été trouvé en butant sur un
plafond mémoire, non choisi pour cette raison.

### ADR-04 — Une API REST intercalée entre l'interface et la base

**Contexte.** L'interface Streamlit pourrait interroger Supabase directement.

**Options.** (a) Accès SQL direct depuis Streamlit. (b) Une API REST comme
couche de service unique.

**Décision.** Option (b) pour les prévisions et l'écriture des commandes. Sans
elle, tout nouveau client — application mobile, logiciel de caisse, partenaire —
devrait réimplémenter l'accès aux données et la logique métier de son côté.

**Conséquences.** La logique d'écriture est testable indépendamment de
l'interface, et les contrats sont documentés automatiquement via OpenAPI. Le
déploiement gagne une pièce mobile, avec son cold start à absorber côté client.
Une dette subsiste et reste assumée : `app/dashboard.py` interroge encore la base
en direct pour les séries historiques. Un endpoint `GET /api/v1/historique/`
refermerait cette seconde porte.

### ADR-05 — Tester le pipeline de données contre PostgreSQL plutôt que l'émuler

**Contexte.** Les couches Extract, Load et Aggregate écrivent toutes en base.
Elles sont restées longtemps à 0 % de couverture, faute de méthode.

**Options.** (a) Rabattre les tests sur SQLite. (b) Simuler l'engine SQLAlchemy.
(c) Un PostgreSQL éphémère, déclaré comme service du job GitHub Actions.

**Décision.** Option (c). L'option (a) reposait sur une hypothèse fausse — SQLite
supporte `ON CONFLICT` depuis la 3.24 et `RETURNING` depuis la 3.35, et les
schémas multiples s'y émulent par `ATTACH` — mais elle resterait de toute façon
une émulation. L'option (b) ne validerait ni l'exactitude des requêtes produites
ni le comportement des contraintes d'intégrité, c'est-à-dire précisément ce que
ces tests doivent vérifier.

**Conséquences.** La couverture de `src/` passe de 45 % à 99 %, et les tests ont
immédiatement révélé un comportement non documenté : 4 % des factures n'ont aucun
employé assigné. Ces tests exécutant des `TRUNCATE`, deux garde-fous indépendants
refusent leur exécution hors d'une base explicitement jetable.

### ADR-06 — Surveiller la dérive par le MASE et non par le MAPE

**Contexte.** Le workflow mensuel vérifiait que l'entraînement se terminait sans
erreur. Un modèle entraîné sur des données dégradées publiait ses prévisions sans
qu'aucune alerte ne le signale.

**Options.** (a) Seuil sur le MAPE. (b) Seuil sur le MASE, qui rapporte l'erreur
à celle d'une prévision naïve.

**Décision.** Option (b). Le MAPE n'a pas de valeur de référence absolue sur cette
série : 130 % y est normal, un seuil serait donc arbitraire. Un MASE supérieur à 1
signifie littéralement que le modèle fait moins bien qu'une prévision naïve — un
critère interprétable sans connaître la série.

**Conséquences.** `model/monitor.py` réentraîne chaque modèle sur l'historique
amputé de ses 30 derniers jours et mesure l'erreur sur cette fenêtre. Le contrôle
alerte sans bloquer, et s'exécute après la publication : sur une PME, mieux vaut
des prévisions dégradées et signalées que pas de prévisions du tout. Il a
également mis en évidence que les pôles Maintenance et Vidéosurveillance ne
comptent qu'environ 295 jours d'activité, en deçà du cycle annuel que leur modèle
prétend capter.
