#!/bin/sh
set -e

echo "=== Venus Luna Startup ==="

# DB test with retries to avoid startup race
python <<EOF
import os
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.db import connection

max_attempts = 10
for attempt in range(1, max_attempts + 1):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
        print("✓ DB Connection OK")
        break
    except Exception as e:
        if attempt == max_attempts:
            print(f"✗ DB Error after {max_attempts} attempts: {e}")
            raise SystemExit(1)
        print(f"⚠ DB not ready (attempt {attempt}/{max_attempts}): {e}")
        time.sleep(3)
EOF

python manage.py migrate --noinput || echo "⚠ Migrate skipped, continuing..."

python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers=2 \
    --worker-tmp-dir /dev/shm \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --preload \
    --log-level info \
    --access-logfile '-' \
    --error-logfile '-' \
    --capture-output

