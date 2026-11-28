#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z "${DB_HOST:-db}" 5432; do
sleep 1
done
echo "PostgreSQL is ready."

exec "$@"
