#!/bin/sh
# Runs once, when the db container initialises an empty data volume.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v migrator_password="$MDM_MIGRATOR_PASSWORD" \
  -v app_password="$MDM_APP_PASSWORD" \
  -v readonly_password="$MDM_READONLY_PASSWORD" \
  -f /bootstrap/bootstrap.sql
