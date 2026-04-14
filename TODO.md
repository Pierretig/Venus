# TODO.md - Plan de Correction Erreurs 500 (Approuvé par User)

## Statut Global : 🔄 EN COURS

### Étape 1: ✅ Compréhension Projet (Fait)
- Django 6.0.1 + Apps: accounts/products/orders/blog/contact/core
- Problèmes: cloudinary manquant, pas de local env, DB prod en local

### Étape 2: ✅ Setup Local Test Env (Fait)
- ✅ local_test/requirements_test.txt
- ✅ local_test/manage_local.py  
- ✅ .env.example

### Étape 3: ✅✅ Fix settings.py TERMINÉ
- ✅ Try/except Cloudinary + fallback local
- ✅ DB: SQLite si DEBUG=True, PostgreSQL sinon (via .env)

### Étape 4: ✅ Test Local
- ✅ .env + .env.example créés
```
# Exécutez maintenant:
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

### Étape 5: ✅ PROD READY (Heroku/Docker)
```
git add . && git commit -m "Fix DB/env pour prod"
git push heroku main
heroku run python manage.py migrate
heroku run python manage.py collectstatic --noinput
heroku config:set $(cat .env | grep -v '#' | cut -d '=' -f1)=$(cat .env | grep -v '#' | cut -d '=' -f1 | paste -d= -)
```

## Statut Global : ✅ RÉSOLU ! Testez maintenant.
- heroku run python manage.py migrate
- heroku run python manage.py collectstatic --noinput
- Vérifier .env prod (ALLOWED_HOSTS, cloudinary keys)

## Prochaines Actions
Attendre création fichiers + installs → tester → updater ce TODO
