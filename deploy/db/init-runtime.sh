#!/bin/sh
# PostgreSQL runs this only for a fresh data directory. Existing volumes: see runbook.
set -eu
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"
psql -X --quiet --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv runtime_password POSTGRES_APP_PASSWORD
SELECT format('CREATE ROLE docqa_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS', :'runtime_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'docqa_app')
\gexec
SQL
