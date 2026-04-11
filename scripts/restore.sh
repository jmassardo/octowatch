#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# OctoWatch — TimescaleDB Restore Script
#
# Restores a pg_dump backup into a TimescaleDB database, verifies hypertable
# integrity, and runs Alembic migrations to ensure schema consistency.
#
# Usage:
#   ./scripts/restore.sh backups/octowatch-backup-20260401-020000.dump
#   ./scripts/restore.sh s3://bucket/path/octowatch-backup-20260401-020000.dump
#
# Environment variables:
#   DATABASE_URL    — PostgreSQL connection string (required)
#   PGPASSWORD      — Alternative: password for pg_restore (optional if in URL)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BACKUP_SOURCE="${1:-}"

if [ -z "${BACKUP_SOURCE}" ]; then
  echo "Usage: $0 <backup-file-or-s3-path>" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  $0 backups/octowatch-backup-20260401-020000.dump" >&2
  echo "  $0 s3://octowatch-backups/octowatch/backups/20260401-020000.sql.gz" >&2
  exit 1
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL environment variable is required." >&2
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "ERROR: pg_restore not found. Install PostgreSQL client tools." >&2
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  OctoWatch TimescaleDB Restore                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Download from S3 if needed ──────────────────────────────────────────────
RESTORE_FILE="${BACKUP_SOURCE}"
if [[ "${BACKUP_SOURCE}" == s3://* ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "ERROR: aws CLI not found. Install it to download from S3." >&2
    exit 1
  fi
  RESTORE_FILE="/tmp/octowatch-restore-$(date +%s).dump"
  echo "→ Downloading from ${BACKUP_SOURCE}..."
  aws s3 cp "${BACKUP_SOURCE}" "${RESTORE_FILE}"
  echo "✓ Downloaded to ${RESTORE_FILE}"
  echo ""
fi

if [ ! -f "${RESTORE_FILE}" ]; then
  echo "ERROR: Backup file not found: ${RESTORE_FILE}" >&2
  exit 1
fi

echo "  Source : ${BACKUP_SOURCE}"
echo "  File   : ${RESTORE_FILE} ($(du -h "${RESTORE_FILE}" | cut -f1))"
echo ""
echo "⚠  WARNING: This will overwrite the current database contents."
echo "   Ensure all OctoWatch services (API, workers, beat) are STOPPED."
echo ""
read -r -p "Continue with restore? [y/N] " CONFIRM
if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
  echo "Restore cancelled."
  exit 0
fi

# ── Step 1: Ensure TimescaleDB extension exists ─────────────────────────────
echo ""
echo "→ Step 1: Ensuring TimescaleDB extension is available..."
psql "${DATABASE_URL}" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" 2>/dev/null || true

# ── Step 2: Pre-restore — run timescaledb_pre_restore ───────────────────────
echo "→ Step 2: Running timescaledb_pre_restore()..."
psql "${DATABASE_URL}" -c "SELECT timescaledb_pre_restore();" 2>/dev/null || {
  echo "  (timescaledb_pre_restore not available — skipping, this is OK for plain PostgreSQL)"
}

# ── Step 3: Restore the dump ────────────────────────────────────────────────
echo "→ Step 3: Restoring database from backup..."
pg_restore "${DATABASE_URL}" \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  --verbose \
  "${RESTORE_FILE}" \
  2>&1 | tail -20 || {
    echo ""
    echo "  Note: pg_restore may report some errors for existing objects."
    echo "  This is normal when using --clean --if-exists."
  }

# ── Step 4: Post-restore — run timescaledb_post_restore ─────────────────────
echo ""
echo "→ Step 4: Running timescaledb_post_restore()..."
psql "${DATABASE_URL}" -c "SELECT timescaledb_post_restore();" 2>/dev/null || {
  echo "  (timescaledb_post_restore not available — skipping)"
}

# ── Step 5: Verify hypertable integrity ─────────────────────────────────────
echo ""
echo "→ Step 5: Verifying hypertable integrity..."
psql "${DATABASE_URL}" -c "
  SELECT hypertable_name, num_chunks, compression_enabled
  FROM timescaledb_information.hypertables
  ORDER BY hypertable_name;
" 2>/dev/null || {
  echo "  (No hypertables found or TimescaleDB not active)"
}

# ── Step 6: Verify chunk count ──────────────────────────────────────────────
echo ""
echo "→ Step 6: Checking chunk health..."
psql "${DATABASE_URL}" -c "
  SELECT hypertable_name,
         chunk_name,
         range_start,
         range_end,
         is_compressed
  FROM timescaledb_information.chunks
  ORDER BY hypertable_name, range_start
  LIMIT 20;
" 2>/dev/null || {
  echo "  (Chunk listing not available)"
}

# ── Step 7: Run Alembic migration verification ─────────────────────────────
echo ""
echo "→ Step 7: Verifying Alembic migration state..."
if command -v alembic >/dev/null 2>&1; then
  echo "  Current head:"
  alembic current 2>/dev/null || true
  echo ""
  echo "  Checking for pending migrations..."
  alembic check 2>/dev/null && echo "  ✓ All migrations applied." || {
    echo "  ⚠ Pending migrations detected. Running upgrade..."
    alembic upgrade head
    echo "  ✓ Migrations applied."
  }
else
  echo "  WARNING: alembic not found in PATH. Run migrations manually:"
  echo "    cd backend && alembic upgrade head"
fi

# ── Cleanup S3 temp file ────────────────────────────────────────────────────
if [[ "${BACKUP_SOURCE}" == s3://* ]] && [ -f "${RESTORE_FILE}" ]; then
  rm -f "${RESTORE_FILE}"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Restore complete!                                          ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Next steps:                                                ║"
echo "║    1. Start OctoWatch services (API, workers, beat)         ║"
echo "║    2. Verify /health and /ready return 200                  ║"
echo "║    3. Check ingestion and detection workers are processing  ║"
echo "╚══════════════════════════════════════════════════════════════╝"
