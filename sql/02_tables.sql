-- =============================================================================
-- 02_tables.sql — Tables des trois schémas
-- =============================================================================
-- Prérequis : sql/01_schemas.sql.
-- Idempotent : rejouable sans effet sur une base déjà initialisée.
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_brut — archive de l'ingestion
-- ─────────────────────────────────────────────────────────────────────────────
-- Toutes les colonnes métier sont en TEXT : la couche Extract lit les classeurs
-- avec dtype=str afin de préserver intactes les anomalies de saisie (dates
-- malformées, montants incohérents) pour analyse en aval. Les typer ici
-- reviendrait à corriger silencieusement ce que la couche Transform doit
-- détecter explicitement.

CREATE TABLE IF NOT EXISTS schema_brut.ventes_raw (
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
    charge_le         TIMESTAMP    -- horodatage d'ingestion (traçabilité)
);

CREATE TABLE IF NOT EXISTS schema_brut.depenses_raw (
    date             TEXT,
    fournisseur      TEXT,
    article          TEXT,
    categorie        TEXT,
    quantite         TEXT,
    prix_achat_total TEXT,
    mode_paiement    TEXT,
    charge_le        TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_brut.clients_raw (
    nom_client TEXT,
    entreprise TEXT,
    telephone  TEXT,
    email      TEXT,
    ville      TEXT,
    notes      TEXT,
    charge_le  TIMESTAMP
);


-- ─────────────────────────────────────────────────────────────────────────────
-- schema_analytics — modèle relationnel en 3FN
-- ─────────────────────────────────────────────────────────────────────────────
-- Ordre de création imposé par les clés étrangères : référentiels d'abord,
-- tables de faits ensuite.

CREATE TABLE IF NOT EXISTS schema_analytics.client (
    id_client  SERIAL PRIMARY KEY,
    nom_client TEXT NOT NULL,
    entreprise TEXT,
    telephone  TEXT,
    email      TEXT,
    ville      TEXT
);

CREATE TABLE IF NOT EXISTS schema_analytics.employe (
    id_employe  SERIAL PRIMARY KEY,
    nom_employe TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_analytics.service (
    id_service SERIAL PRIMARY KEY,
    libelle    TEXT NOT NULL UNIQUE
);

-- id_facture est une référence métier (FAC-2026-A3F9C2D1) générée côté API,
-- pas une séquence : le type est donc TEXT et non SERIAL.
CREATE TABLE IF NOT EXISTS schema_analytics.facture (
    id_facture      TEXT PRIMARY KEY,
    date_facture    DATE NOT NULL,
    statut_paiement TEXT,
    id_client       INTEGER REFERENCES schema_analytics.client (id_client),
    id_employe      INTEGER REFERENCES schema_analytics.employe (id_employe)
);

-- Les montants sont en FCFA, monnaie sans subdivision courante : des entiers
-- suffisent et évitent les erreurs d'arrondi flottant sur les agrégations.
CREATE TABLE IF NOT EXISTS schema_analytics.ligne_facture (
    id_ligne      SERIAL PRIMARY KEY,
    description   TEXT,
    quantite      INTEGER,
    prix_unitaire BIGINT,
    total_ligne   BIGINT,
    id_facture    TEXT    REFERENCES schema_analytics.facture (id_facture) ON DELETE CASCADE,
    id_service    INTEGER REFERENCES schema_analytics.service (id_service)
);

CREATE TABLE IF NOT EXISTS schema_analytics.fournisseur (
    id_fournisseur SERIAL PRIMARY KEY,
    nom            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_analytics.categorie_achat (
    id_categorie SERIAL PRIMARY KEY,
    libelle      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_analytics.achat (
    id               SERIAL PRIMARY KEY,
    date_achat       DATE,
    libelle_article  TEXT,
    quantite         INTEGER,
    prix_achat_total BIGINT,
    mode_paiement    TEXT,
    id_fournisseur   INTEGER REFERENCES schema_analytics.fournisseur (id_fournisseur),
    id_categorie     INTEGER REFERENCES schema_analytics.categorie_achat (id_categorie)
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

CREATE TABLE IF NOT EXISTS schema_ia.serie_ventes_journalieres (
    id_serie     SERIAL PRIMARY KEY,
    ds           DATE NOT NULL,
    y            NUMERIC,
    nb_commandes INTEGER,
    rafraichi_le TIMESTAMP
);

CREATE TABLE IF NOT EXISTS schema_ia.serie_ventes_par_service (
    id_serie     SERIAL PRIMARY KEY,
    ds           DATE NOT NULL,
    service      TEXT NOT NULL,
    y            NUMERIC,
    nb_commandes INTEGER,
    rafraichi_le TIMESTAMP
);

-- genere_le porte une valeur par défaut : model/train.py n'insère que les cinq
-- premières colonnes.
CREATE TABLE IF NOT EXISTS schema_ia.previsions_prophet (
    id         SERIAL PRIMARY KEY,
    service    TEXT NOT NULL,
    ds         DATE NOT NULL,
    yhat       BIGINT,
    yhat_lower BIGINT,
    yhat_upper BIGINT,
    genere_le  TIMESTAMP DEFAULT NOW()
);

-- L'API filtre sur (service, ds) à chaque appel de GET /previsions/{service}.
CREATE INDEX IF NOT EXISTS ix_previsions_service_ds
    ON schema_ia.previsions_prophet (service, ds);
