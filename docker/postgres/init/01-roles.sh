#!/usr/bin/env bash
# Creates Cucumber's two database roles and its database (U0.2 design §4).
#
#   cucumber_owner  owns the database and tables, runs migrations, may create
#                   the test database.
#   cucumber_app    may only log in; its table rights come from U0.2a's GRANTs.
#
# Runs as the PostgreSQL superuser: by Docker on the first start of an empty
# volume, and by CI as a step. Passwords come from the environment and are
# passed to psql as variables, never written into this file.
set -euo pipefail

: "${DB_OWNER_PASSWORD:?DB_OWNER_PASSWORD must be set}"
: "${DB_APP_PASSWORD:?DB_APP_PASSWORD must be set}"
DB_NAME="${DB_NAME:-cucumber}"

psql -v ON_ERROR_STOP=1 --dbname postgres \
  -v owner_password="$DB_OWNER_PASSWORD" \
  -v app_password="$DB_APP_PASSWORD" \
  -v db_name="$DB_NAME" <<'SQL'
CREATE ROLE cucumber_owner LOGIN CREATEDB NOSUPERUSER NOCREATEROLE
  PASSWORD :'owner_password';
CREATE ROLE cucumber_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'app_password';
CREATE DATABASE :"db_name" OWNER cucumber_owner;
-- Only Cucumber's own roles may connect to its database.
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO cucumber_owner, cucumber_app;
SQL
