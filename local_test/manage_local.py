#!/usr/bin/env python
"""manage_local.py - Version LOCAL pour tests (DEBUG=True, SQLite).\n
Usage: python manage_local.py runserver\n
MIGRE: python manage_local.py migrate\n"""

import os
import sys
from pathlib import Path

# Ajoute apps au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps'))

# Force .env parent
from dotenv import load_dotenv
load_dotenv(dotenv_path='../.env')  # Charge .env racine

# Force path + settings
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['DEBUG'] = 'True'  # Force DEBUG local
os.environ['DB_ENGINE'] = 'django.db.backends.sqlite3'
os.environ['DB_NAME'] = str(BASE_DIR / 'db.sqlite3')
# os.environ['DB_NAME'] = 'local_db'  # Optionnel: override si besoin
# os.environ['DB_HOST'] = 'localhost'

from django.core.management import execute_from_command_line

if __name__ == '__main__':
    execute_from_command_line(sys.argv)
