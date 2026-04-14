# TODO.md - Fix Bad Gateway 502 PRODUCTION (Plan Approved - Implements in Progress)

## Statut Global : ✅ READY FOR DEPLOY

### Étape 1: ✅ Diagnostic Local
- Django OK (check/deploy, static, config import)

### Étape 2: 🔑 SECRET_KEY Généré
```
SECRET_KEY='u49lvqEsH5hTNlBcq7cuAq7yoXdgRjww35qxrn-sFrcugL2K6QyuqhV6vphkKD6L-IA'
```
**Copiez dans .env prod !**

### Étape 3: 📝 Edits Prod Robustesse
- settings.py: + LOGGING console/file pour 502 debug
- entrypoint.sh: DB test, migrate continue-on-error, gunicorn --workers 2 --timeout 120
- Dockerfile: Healthcheck ajouté

### Étape 4: 🚀 DEPLOY COMMANDS (Exécutez sur serveur)
```
1. Copier nouveau code + .env avec SECRET_KEY + DB_HOST=venusluna-venus-data-base-mylun9
2. docker build -t venus .
3. docker stop CONTAINER_ID; docker rm CONTAINER_ID  # docker ps -a
4. docker run -d -p 80:8000 --name venus --env-file .env -v $(pwd)/media:/app/media venus
5. docker logs -f venus  # ← CRUCIAL: Partagez cette sortie !
```

### Étape 5: Logs à vérifier
```
docker logs CONTAINER_ID | grep -i error
journalctl -u docker -f
```

**Statut : READY** - Deploy + paste `docker logs` ici pour final fix.

## Next: User deploy → logs → 502 résolu !

