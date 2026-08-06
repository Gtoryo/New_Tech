-- =============================================================================
-- 03_contraintes_unicite.sql — Index d'unicité de schema_analytics
-- =============================================================================
-- Ces index conditionnent le fonctionnement de l'API : l'endpoint
-- POST /api/v1/commandes/ s'appuie sur INSERT ... ON CONFLICT (LOWER(...))
-- pour ses upserts client et employé. Sans eux, PostgreSQL rejette la requête
-- avec « no unique or exclusion constraint matching the ON CONFLICT
-- specification » et aucune commande ne peut être enregistrée.
--
-- Ils garantissent également qu'aucun doublon insensible à la casse ne peut
-- entrer en base, quelle que soit la voie d'écriture — pipeline ETL ou API.
--
-- Exécution : éditeur SQL Supabase, ou psql -f sql/03_contraintes_unicite.sql
-- =============================================================================


-- ── Prérequis : la base ne doit contenir aucun doublon existant ──────────────
-- Les deux requêtes suivantes doivent renvoyer 0 ligne avant création des
-- index. Si ce n'est pas le cas, exécuter d'abord la fusion ci-dessous.
--
--   SELECT LOWER(nom_client), COUNT(*) FROM schema_analytics.client
--   GROUP BY LOWER(nom_client) HAVING COUNT(*) > 1;
--
--   SELECT LOWER(nom_employe), COUNT(*) FROM schema_analytics.employe
--   GROUP BY LOWER(nom_employe) HAVING COUNT(*) > 1;


-- ── Fusion des doublons préexistants (idempotent, sans effet si la base
--    est déjà saine) ────────────────────────────────────────────────────────
-- Utile sur une base chargée avant l'introduction de la déduplication
-- insensible à la casse dans src/transform.py. La règle de conservation est
-- identique à celle du pipeline : on garde la variante en casse mixte, plus
-- lisible, plutôt que la version tout en majuscules.
BEGIN;

WITH classement AS (
    SELECT id_client,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(nom_client)
               ORDER BY (nom_client = UPPER(nom_client)), id_client
           ) AS rang,
           FIRST_VALUE(id_client) OVER (
               PARTITION BY LOWER(nom_client)
               ORDER BY (nom_client = UPPER(nom_client)), id_client
           ) AS id_conserve
    FROM schema_analytics.client
)
UPDATE schema_analytics.facture f
SET    id_client = c.id_conserve
FROM   classement c
WHERE  f.id_client = c.id_client
  AND  c.rang > 1;

WITH classement AS (
    SELECT id_client,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(nom_client)
               ORDER BY (nom_client = UPPER(nom_client)), id_client
           ) AS rang
    FROM schema_analytics.client
)
DELETE FROM schema_analytics.client cl
USING  classement c
WHERE  cl.id_client = c.id_client
  AND  c.rang > 1;

COMMIT;


-- ── Index d'unicité ─────────────────────────────────────────────────────────
-- Sur LOWER(...) et non sur la colonne brute : « Pharmacie X » et
-- « PHARMACIE X » désignent le même client et ne doivent pas coexister.
CREATE UNIQUE INDEX IF NOT EXISTS ux_client_nom_lower
    ON schema_analytics.client (LOWER(nom_client));

CREATE UNIQUE INDEX IF NOT EXISTS ux_employe_nom_lower
    ON schema_analytics.employe (LOWER(nom_employe));
