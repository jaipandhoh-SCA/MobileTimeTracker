#!/usr/bin/env bash
# backup_db.sh — Dump the Neon PostgreSQL database before destructive migrations.
#
# Usage:
#   ./scripts/backup_db.sh                  # uses DATABASE_URL from .env
#   DATABASE_URL="postgres://..." ./scripts/backup_db.sh
#
# Output: backups/backup_YYYYMMDD_HHMMSS.sql  (git-ignored)

set -euo pipefail

# Load .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set. Pass it or add to .env." >&2
    exit 1
fi

BACKUP_DIR="backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql"

echo "Backing up database to ${BACKUP_FILE}..."
pg_dump "$DATABASE_URL" --no-owner --no-privileges > "$BACKUP_FILE"

FILE_SIZE=$(wc -c < "$BACKUP_FILE" | tr -d ' ')
echo "Backup complete: ${BACKUP_FILE} (${FILE_SIZE} bytes)"
