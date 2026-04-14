#!/bin/sh
set -e

echo "=== Venus Luna Startup ==="

# DB test
python <<EOF
try:
    from config.settings import DATABASES
    from django.db import connection
    cursor = connection.cursor()
    print("✓ DB Connection OK")
except Exception as e:
    print(f"✗ DB Error: {e}")
    exit(1)
EOF

python manage.py migrate --noinput || echo "⚠ Migrate skipped, continuing..."

python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \\
    --bind 0.0.0.0:8000 \\
    --workers=2 \\
    --worker-tmp-dir /dev/shm \\
    --timeout 120 \\
    --max-requests 1000 \\
    --max-requests-jitter 100 \\
    --preload-app \\
    --log-level info \\
    --access-logfile '-' \\
    --error-logfile '-' \\
    --enable-stdio-inheritance

