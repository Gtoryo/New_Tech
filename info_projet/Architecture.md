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