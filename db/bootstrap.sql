-- BVT MDM: one-time cluster bootstrap. Run as a superuser with psql.
-- Idempotent: safe to re-run (e.g. to rotate role passwords).
--
-- Required psql variables:
--   migrator_password, app_password, readonly_password
-- Example:
--   psql -v migrator_password=... -v app_password=... -v readonly_password=... -f db/bootstrap.sql
--
-- Everything inside the databases (schema mdm, tables, grants) is owned by
-- Alembic migrations running as mdm_migrator. This script only creates the
-- roles and the databases.

\set ON_ERROR_STOP on

-- Roles ---------------------------------------------------------------------
SELECT 'CREATE ROLE mdm_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_migrator') \gexec
SELECT 'CREATE ROLE mdm_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_app') \gexec
SELECT 'CREATE ROLE mdm_readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdm_readonly') \gexec

ALTER ROLE mdm_migrator PASSWORD :'migrator_password';
ALTER ROLE mdm_app      PASSWORD :'app_password';
ALTER ROLE mdm_readonly PASSWORD :'readonly_password';

ALTER ROLE mdm_app      SET search_path = mdm;
ALTER ROLE mdm_app      SET statement_timeout = '60s';
ALTER ROLE mdm_app      SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE mdm_readonly SET search_path = mdm;
ALTER ROLE mdm_readonly SET default_transaction_read_only = on;
ALTER ROLE mdm_readonly SET statement_timeout = '300s';

-- Databases -----------------------------------------------------------------
-- mdm: the application database. mdm_test: pytest only. mdm_e2e: Playwright only.
SELECT 'CREATE DATABASE mdm OWNER mdm_migrator ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mdm') \gexec
SELECT 'CREATE DATABASE mdm_test OWNER mdm_migrator ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mdm_test') \gexec
SELECT 'CREATE DATABASE mdm_e2e OWNER mdm_migrator ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mdm_e2e') \gexec

REVOKE ALL ON DATABASE mdm      FROM PUBLIC;
REVOKE ALL ON DATABASE mdm_test FROM PUBLIC;
REVOKE ALL ON DATABASE mdm_e2e  FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE mdm      TO mdm_app;
GRANT CONNECT, TEMPORARY ON DATABASE mdm_test TO mdm_app;
GRANT CONNECT, TEMPORARY ON DATABASE mdm_e2e  TO mdm_app;
GRANT CONNECT ON DATABASE mdm      TO mdm_readonly;
GRANT CONNECT ON DATABASE mdm_test TO mdm_readonly;
GRANT CONNECT ON DATABASE mdm_e2e  TO mdm_readonly;

-- Nobody but the owner may create objects in public.
\connect mdm
REVOKE ALL ON SCHEMA public FROM PUBLIC;
\connect mdm_test
REVOKE ALL ON SCHEMA public FROM PUBLIC;
\connect mdm_e2e
REVOKE ALL ON SCHEMA public FROM PUBLIC;
