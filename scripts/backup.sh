#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# OctoWatch — TimescaleDB Backup Script
#
# Creates a pg_dump backup with TimescaleDB-compatible flags, compresses it,
# and optionally uploads to S3/MinIO.
#
# Usage:
#   ./scripts/backup.sh                          # Backup to ./backups/
#   ./scripts/backup.sh s3://bucket/path         # Backup and upload to S3
#
# Environment variables:
#   DATABASE_URL    — PostgreSQL connection string (required)
#   PGPASSWORD      — Alternative: password for pg_dump (optional if in URL)
#   AWS_PROFILE     — AWS profile for S3 upload (optional)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/../backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/octowatch-backup-${TIMESTAMP}.dump"
S3_DEST="${1:-}"

# ── Validate prerequisites ──────────────────────────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL environment variable is required." >&2
  echo "  Example: postgresql://app_rw:password@localhost:5432/auditlogs" >&2
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump not found. Install PostgreSQL client tools." >&2
  exit 1
fi

# ── Create backup directory ─────────────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  OctoWatch TimescaleDB Backup                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Timestamp : ${TIMESTAMP}"
echo "  Output    : ${BACKUP_FILE}"
echo ""

# ── Run pg_dump with TimescaleDB-compatible flags ───────────────────────────
# --no-owner / --no-acl: portable across environments
# --format=custom: enables parallel restore and selective table restore
# --compress=9: maximum gzip compression
echo "→ Running pg_dump..."
pg_dump "${DATABASE_URL}" \
  --no-owner \
  --no-acl \
  --format=custom \
  --compress=9 \
  --verbose \
  --file="${BACKUP_FILE}" \
  2>&1 | tail -5

BACKUP_SIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
echo ""
echo "✓ Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Upload to S3/MinIO if destination provided ──────────────────────────────
if [ -n "${S3_DEST}" ]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: aws CLI not found. Install it to upload to S3." >&2
    exit 1
  fi

  S3_PATH="${S3_DEST}/octowatch-backup-${TIMESTAMP}.dump"
  echo ""
  echo "→ Uploading to ${S3_PATH}..."
  aws s3 cp "${BACKUP_FILE}" "${S3_PATH}"
  echo "✓ Upload complete."
fi

echo ""
echo "Backup finished at $(date +%Y-%m-%d\ %H:%M:%S\ %Z)"
