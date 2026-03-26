#!/usr/bin/env bash
set -euo pipefail

# Lexiro rebrand migration — run on VPS in /opt/ipcodex (or /opt/lexiro)
# Renames: DB ipcodex→lexiro, user ipcodex→lexiro, S3 bucket, .env, project dir

PROJECT_DIR="/opt/ipcodex"
NEW_DIR="/opt/lexiro"

cd "$PROJECT_DIR"

echo "=== Step 1: Pull latest code ==="
git pull origin main

echo ""
echo "=== Step 2: Stop application services (keep postgres, redis, minio) ==="
docker compose stop api worker beat web

echo ""
echo "=== Step 3: Rename PostgreSQL database and user ==="
docker compose exec -T postgres psql -U ipcodex -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ipcodex' AND pid <> pg_backend_pid();"
docker compose exec -T postgres psql -U ipcodex -d postgres -c \
  "ALTER DATABASE ipcodex RENAME TO lexiro;"
docker compose exec -T postgres psql -U ipcodex -d postgres -c \
  "ALTER USER ipcodex RENAME TO lexiro;"
docker compose exec -T postgres psql -U lexiro -d postgres -c \
  "ALTER USER lexiro WITH PASSWORD 'lexiro_dev';"
echo "PostgreSQL: database and user renamed successfully"

echo ""
echo "=== Step 4: Migrate MinIO S3 bucket ==="
# Install mc (MinIO Client) inside minio container if not present
docker compose exec -T minio sh -c '
  if ! command -v mc >/dev/null 2>&1; then
    echo "mc not found, using built-in minio client..."
  fi
  mc alias set local http://localhost:9000 ${MINIO_ROOT_USER:-ipcodex} ${MINIO_ROOT_PASSWORD:-ipcodex_dev} 2>/dev/null || true
  if mc ls local/ipcodex-storage >/dev/null 2>&1; then
    mc mb local/lexiro-storage --ignore-existing
    mc mirror --overwrite local/ipcodex-storage local/lexiro-storage
    mc rb --force local/ipcodex-storage
    echo "S3: bucket migrated ipcodex-storage -> lexiro-storage"
  else
    mc mb local/lexiro-storage --ignore-existing
    echo "S3: ipcodex-storage not found, created lexiro-storage"
  fi
'

echo ""
echo "=== Step 5: Update .env on VPS ==="
if [ -f .env ]; then
  cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
  sed -i 's|ipcodex:ipcodex_dev@|lexiro:lexiro_dev@|g' .env
  sed -i 's|/ipcodex$|/lexiro|g' .env
  sed -i 's|POSTGRES_PASSWORD=ipcodex_dev|POSTGRES_PASSWORD=lexiro_dev|g' .env
  sed -i 's|S3_ACCESS_KEY=ipcodex|S3_ACCESS_KEY=lexiro|g' .env
  sed -i 's|S3_SECRET_KEY=ipcodex_dev|S3_SECRET_KEY=lexiro_dev|g' .env
  sed -i 's|S3_BUCKET=ipcodex-storage|S3_BUCKET=lexiro-storage|g' .env
  sed -i 's|/opt/ipcodex|/opt/lexiro|g' .env
  echo ".env updated (backup saved)"
else
  echo "No .env file found, skipping"
fi

echo ""
echo "=== Step 6: Update MinIO credentials ==="
# MinIO root credentials need to be updated to match new S3_ACCESS_KEY
docker compose exec -T minio sh -c '
  mc alias set local http://localhost:9000 ${MINIO_ROOT_USER:-ipcodex} ${MINIO_ROOT_PASSWORD:-ipcodex_dev} 2>/dev/null || true
  mc admin user add local lexiro lexiro_dev 2>/dev/null || true
  mc admin policy attach local readwrite --user=lexiro 2>/dev/null || true
' || echo "MinIO credential update skipped (may need manual config)"

echo ""
echo "=== Step 7: Rebuild and start services ==="
docker compose build api web
docker compose up -d

echo ""
echo "=== Step 8: Verify ==="
sleep 5
docker compose exec -T postgres psql -U lexiro -d lexiro -c "SELECT count(*) as products FROM products;"
echo ""
docker compose logs --tail=10 api

echo ""
echo "=== Step 9 (optional): Rename project directory ==="
echo "To rename the project directory, run manually after verifying everything works:"
echo "  cd / && mv $PROJECT_DIR $NEW_DIR"
echo "  # Then update any systemd units, cron jobs, etc. that reference the old path"

echo ""
echo "=== Migration complete! ==="
