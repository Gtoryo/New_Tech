-- =============================================================================
-- 02_tables.sql — Tables des trois schémas
-- =============================================================================
-- Prérequis : sql/01_schemas.sql.
-- Idempotent : rejouable sans effet sur une base déjà initialisée.
--
-- CE FICHIER DÉCRIT LA BASE DE PRODUCTION À L'IDENTIQUE.
-- Types, longueurs, obligatoriété, valeurs par défaut, contraintes d'unicité et
-- index ont été relevés sur l'instance Supabase en service, puis recopiés ici.
-- L'objectif est qu'un repreneur qui applique ces fichiers sur une base vierge
-- obtienne exactement le schéma qui tourne, et non une variante permissive dans
-- laquelle une donnée refusée en production passerait sans bruit.
--
-- Une contrainte d'écriture : pas de caractère « pour cent » dans ces
-- commentaires. Les fichiers sql/ sont joués par exec_driver_sql(), et psycopg2
-- lit ce caractère comme un marqueur de paramètre — le fichier entier échoue
-- alors sur une TypeError qui ne mentionne ni le commentaire ni le fichier.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_brut — archive de l'ingestion
-- ─────────────────────────────────────────────────────────────────────────────
-- Toutes les colonnes métier sont en TEXT : la couche Extract lit les classeurs
-- avec dtype=str afin de préserver intactes les anomalies de saisie (dates
-- malformées, montants incohérents) pour analyse en aval. Les typer ici
-- reviendrait à corriger silencieusement ce que la couche Transform doit
-- détecter explicitement.
--
-- id_raw est une clé technique sans portée métier. Elle donne sa cible au
-- RESTART IDENTITY du TRUNCATE de src/load.py : sans séquence, la clause est
-- acceptée mais sans effet, et le compteur d'une base rechargée dériverait de
-- celui de la production.

CREATE TABLE IF NOT EXISTS schema_brut.ventes_raw (
    id_raw            SERIAL PRIMARY KEY,
    date              TEXT,
    facture_id        TEXT,
    client            TEXT,
    telephone         TEXT,
    service_type      TEXT,
    description       TEXT,
    quantite          TEXT,
    prix_unitaire     TEXT,
    total             TEXT,
    employe_en_charge TEXT,
    statut_paiement   TEXT,
    charge_le         TIMESTAMP DEFAULT NOW()   -- horodatage d'ingestion (traçabilité)
);

CREATE TABLE IF NOT EXISTS schema_brut.depenses_raw (
    id_raw           SERIAL PRIMARY KEY,
    date             TEXT,
    fournisseur      TEXT,
    article          TEXT,
    categorie        TEXT,
    quantite         TEXT,
    prix_achat_total TEXT,
    mode_paiement    TEXT,
    charge_le        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schema_brut.clients_raw (
    id_raw     SERIAL PRIMARY KEY,
    nom_client TEXT,
    entreprise TEXT,
    telephone  TEXT,
    email      TEXT,
    ville      TEXT,
    notes      TEXT,
    charge_le  TIMESTAMP DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_analytics — modèle relationnel en 3FN
-- ─────────────────────────────────────────────────────────────────────────────
-- Ordre de création imposé par les clés étrangères : référentiels d'abord,
-- tables de faits ensuite.
--
-- Les chaînes sont bornées (VARCHAR(n) et non TEXT). La borne n'est pas
-- décorative : elle refuse en base une saisie hors gabarit, et les contrats
-- Pydantic de l'API portent les mêmes limites afin que le rejet se produise en
-- 422 côté API, avec un message lisible, plutôt qu'en erreur serveur.

CREATE TABLE IF NOT EXISTS schema_analytics.client (
    id_client  SERIAL PRIMARY KEY,
    nom_client VARCHAR(150) NOT NULL,
    entreprise VARCHAR(150),
    telephone  VARCHAR(20),
    email      VARCHAR(100),
    ville      VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS schema_analytics.employe (
    id_employe  SERIAL PRIMARY KEY,
    nom_employe VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_analytics.service (
    id_service SERIAL PRIMARY KEY,
    libelle    VARCHAR(50) NOT NULL UNIQUE
);

-- id_facture est une référence métier (FAC-2026-A3F9C2D1) générée côté API,
-- pas une séquence : le type est donc VARCHAR et non SERIAL. Le format tient en
-- 17 caractères, la borne de 20 laisse la marge d'un préfixe plus long.
--
-- id_client est NOT NULL, id_employe ne l'est pas, et l'écart est voulu.
-- Une commande appartient toujours à un client : la couche Transform écarte les
-- lignes sans client, et l'API crée le client avant la facture. L'employé, lui,
-- n'est pas toujours renseigné à la saisie — 113 factures du jeu de travail sur
-- 2 859, environ une sur vingt-cinq, n'en portent aucun. La facture reste
-- légitime, son chiffre d'affaires compte, seul le lien vers employe manque.
CREATE TABLE IF NOT EXISTS schema_analytics.facture (
    id_facture      VARCHAR(20) PRIMARY KEY,
    date_facture    DATE        NOT NULL,
    statut_paiement VARCHAR(20) NOT NULL,
    id_client       INTEGER     NOT NULL REFERENCES schema_analytics.client (id_client),
    id_employe      INTEGER              REFERENCES schema_analytics.employe (id_employe)
);

-- Les montants sont en FCFA, monnaie sans subdivision courante : des entiers
-- suffisent et évitent les erreurs d'arrondi flottant sur les agrégations.
-- INTEGER plafonne à 2 147 483 647, très au-dessus du plus gros montant observé
-- (960 000 FCFA sur une ligne). Les cumuls ne débordent pas non plus :
-- PostgreSQL promeut SUM(INTEGER) en BIGINT.
--
-- prix_unitaire est la seule colonne nullable de la table. Ce n'est pas un
-- oubli : 90 lignes du jeu de travail ne portent aucun prix unitaire renseigné,
-- alors que leur total, lui, est connu. Contraindre cette colonne obligerait à
-- inventer une valeur ou à supprimer la ligne — deux façons d'abîmer
-- l'historique pour satisfaire le modèle.
CREATE TABLE IF NOT EXISTS schema_analytics.ligne_facture (
    id_ligne      SERIAL PRIMARY KEY,
    description   VARCHAR(255) NOT NULL,
    quantite      INTEGER      NOT NULL,
    prix_unitaire INTEGER,
    total_ligne   INTEGER      NOT NULL,
    id_facture    VARCHAR(20)  NOT NULL REFERENCES schema_analytics.facture (id_facture),
    id_service    INTEGER      NOT NULL REFERENCES schema_analytics.service (id_service)
);

CREATE TABLE IF NOT EXISTS schema_analytics.fournisseur (
    id_fournisseur SERIAL PRIMARY KEY,
    nom            VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS schema_analytics.categorie_achat (
    id_categorie SERIAL PRIMARY KEY,
    libelle      VARCHAR(50) NOT NULL UNIQUE
);

-- La clé primaire suit la convention id_<entité> appliquée à toutes les autres
-- tables. Pour une base tierce créée avant cette uniformisation,
-- CREATE TABLE IF NOT EXISTS ne renomme pas une colonne existante ; appliquer
-- alors une fois :
--     ALTER TABLE schema_analytics.achat RENAME COLUMN id TO id_achat;
-- Aucun module Python ne référence cette colonne — le pipeline laisse
-- PostgreSQL générer la valeur — la migration est donc sans effet de bord.
CREATE TABLE IF NOT EXISTS schema_analytics.achat (
    id_achat         SERIAL PRIMARY KEY,
    date_achat       DATE         NOT NULL,
    libelle_article  VARCHAR(255) NOT NULL,
    quantite         INTEGER      NOT NULL,
    prix_achat_total INTEGER      NOT NULL,
    mode_paiement    VARCHAR(30),
    id_fournisseur   INTEGER      NOT NULL REFERENCES schema_analytics.fournisseur (id_fournisseur),
    id_categorie     INTEGER      NOT NULL REFERENCES schema_analytics.categorie_achat (id_categorie)
);

-- Référentiel contrôlé des pôles d'activité. Cette table n'est jamais alimentée
-- par le pipeline : src/load.py la lit pour résoudre id_service, et l'API la
-- consulte pour valider le libellé reçu. Les quatre valeurs correspondent au
-- type Literal du contrat CommandeIn (api/schemas.py) — toute divergence
-- provoquerait un rejet en 400 à l'enregistrement d'une commande.
INSERT INTO schema_analytics.service (libelle)
VALUES ('Imprimerie'), ('Sérigraphie'), ('Maintenance'), ('Vidéosurveillance')
ON CONFLICT (libelle) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_ia — séries temporelles et prévisions
-- ─────────────────────────────────────────────────────────────────────────────
-- Les colonnes ds et y portent les noms imposés par Prophet : aucun renommage
-- n'est nécessaire à l'entraînement.
--
-- Les contraintes d'unicité sur ds, et sur le couple (ds, service), verrouillent
-- la propriété que produit l'agrégation SQL : une observation par jour, et une
-- par couple jour-pôle. Un GROUP BY altéré par mégarde dupliquerait des dates,
-- Prophet s'entraînerait sur une série gonflée, et rien ne le signalerait.

CREATE TABLE IF NOT EXISTS schema_ia.serie_ventes_journalieres (
    id_serie     SERIAL PRIMARY KEY,
    ds           DATE          NOT NULL UNIQUE,
    y            NUMERIC(12,2) NOT NULL,
    nb_commandes INTEGER       NOT NULL,
    rafraichi_le TIMESTAMP     DEFAULT NOW()
);

-- L'ordre des colonnes suit celui de la production, que src/aggregate.py
-- reproduit à l'insertion.
CREATE TABLE IF NOT EXISTS schema_ia.serie_ventes_par_service (
    id_serie     SERIAL PRIMARY KEY,
    ds           DATE          NOT NULL,
    y            NUMERIC(12,2) NOT NULL,
    service      VARCHAR(50)   NOT NULL,
    nb_commandes INTEGER       NOT NULL,
    rafraichi_le TIMESTAMP     DEFAULT NOW(),
    UNIQUE (ds, service)
);

-- genere_le porte une valeur par défaut : model/train.py n'insère que les cinq
-- premières colonnes. Les bornes de prévision sont NOT NULL parce que
-- _preparer_previsions() les écrête à zéro avant écriture : une absence de
-- valeur signalerait un défaut du modèle, pas une donnée manquante.
CREATE TABLE IF NOT EXISTS schema_ia.previsions_prophet (
    id         SERIAL PRIMARY KEY,
    service    VARCHAR(50) NOT NULL,
    ds         DATE        NOT NULL,
    yhat       INTEGER     NOT NULL,
    yhat_lower INTEGER     NOT NULL,
    yhat_upper INTEGER     NOT NULL,
    genere_le  TIMESTAMP   DEFAULT NOW()
);

-- L'API filtre sur (service, ds) à chaque appel de GET /previsions/{service}.
CREATE INDEX IF NOT EXISTS idx_prev_service_ds
    ON schema_ia.previsions_prophet (service, ds);
