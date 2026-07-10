-- Configure the least-privileged login used by Grafana.
-- psql reads the password from the process environment without exposing it in argv.
\set ON_ERROR_STOP on
\getenv grafana_password GRAFANA_DB_PASSWORD

BEGIN;

SELECT 'CREATE ROLE oura_grafana'
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'oura_grafana')
\gexec

ALTER ROLE oura_grafana WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT
    NOREPLICATION
    NOBYPASSRLS
    PASSWORD :'grafana_password';

ALTER ROLE oura_grafana SET default_transaction_read_only = on;
ALTER ROLE oura_grafana SET search_path = pg_catalog, public;

SELECT format('GRANT CONNECT ON DATABASE %I TO oura_grafana', current_database())
\gexec

GRANT USAGE ON SCHEMA public TO oura_grafana;
REVOKE CREATE ON SCHEMA public FROM oura_grafana;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM oura_grafana;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM oura_grafana;

-- New tables stay private until this migration explicitly reviews and grants them.
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE SELECT ON TABLES FROM oura_grafana',
    current_user
)
\gexec

-- oauth_token_state must remain inaccessible even through an accidental PUBLIC grant.
REVOKE ALL PRIVILEGES ON TABLE public.oauth_token_state FROM PUBLIC;

SELECT format('GRANT SELECT ON TABLE %I.%I TO oura_grafana', namespace.nspname, relation.relname)
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
WHERE namespace.nspname = 'public'
  AND relation.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND relation.relname <> 'oauth_token_state'
ORDER BY relation.relname
\gexec

COMMIT;
