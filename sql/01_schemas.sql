-- =============================================================================
-- 01_schemas.sql — Les trois schémas logiques de l'entrepôt
-- =============================================================================
-- La base est découpée selon le stade de maturité de la donnée. Chaque schéma
-- porte une responsabilité unique et les modules Python ne franchissent jamais
-- ces frontières : src/load.py écrit dans schema_brut puis schema_analytics,
-- src/aggregate.py lit schema_analytics et écrit schema_ia, l'API ne lit que
-- schema_analytics (écriture des commandes) et schema_ia (prévisions, KPIs).
--
-- Bénéfice opérationnel : en cas d'erreur dans la couche de transformation, la
-- donnée brute reste disponible dans schema_brut pour être rejouée.
--
-- Exécution : psql -f sql/01_schemas.sql, ou éditeur SQL Supabase.
-- Les trois fichiers sql/ sont idempotents et doivent être joués dans l'ordre.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS schema_brut;       -- ingestion à l'état natif
CREATE SCHEMA IF NOT EXISTS schema_analytics;  -- données propres, 3FN, BI
CREATE SCHEMA IF NOT EXISTS schema_ia;         -- séries temporelles et prévisions
