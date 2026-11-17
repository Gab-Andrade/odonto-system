#!/bin/sh
# Executado pela imagem oficial do Postgres apenas na criação do volume.
set -e
psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v app_password="$APP_DB_PASSWORD" -v owner="$POSTGRES_USER" \
    -f /opt/odonto/roles.sql
