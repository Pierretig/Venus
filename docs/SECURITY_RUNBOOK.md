# Runbook de Sécurité & Rotation des Secrets — Venus Luna

Ce document décrit les procédures opérationnelles pour la gestion des secrets, le durcissement de l'infrastructure et la maintenance de la sécurité de **Venus Luna**.

---

## 1. Procédure de rotation des secrets

### A. Clé secrète Django (`SECRET_KEY`)
La clé secrète Django signe les cookies de session, les jetons CSRF et les jetons de réinitialisation de mot de passe.

1. **Génération d'une nouvelle clé cryptographique** :
   Exécutez dans l'environnement Python :
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```
2. **Mise à jour sur le serveur de production** (Dokploy / Docker / Traefik) :
   Définissez la variable dans votre gestionnaire d'environnement :
   ```env
   SECRET_KEY=votre_nouvelle_cle_generee
   ```
3. **Redémarrage du conteneur** :
   ```bash
   docker restart venus-luna
   ```
   *Note : La rotation de `SECRET_KEY` invalidera les sessions de connexion actives, ce qui est le comportement de sécurité normal.*

---

### B. Secret Webhook CashPay (`CASHPAY_SECRET_WEBHOOK`)
1. Connectez-vous à la console marchand **Semoa Payments / CashPay**.
2. Dans la configuration Webhooks / Développeur, générez ou récupérez le secret partagé de webhook.
3. Renseignez la variable en production :
   ```env
   CASHPAY_SECRET_WEBHOOK=votre_secret_cashpay
   ```
4. Tout webhook reçu sans signature valide sera automatiquement rejeté avec le statut `401 Unauthorized`.

---

### C. Identifiants SMTP Brevo (Sendinblue)
1. Rendez-vous sur votre compte [Brevo](https://app.brevo.com/) > **Paramètres SMTP & API**.
2. Générez une nouvelle clé SMTP.
3. Mettez à jour le fichier `.env` ou les variables du conteneur :
   ```env
   BREVO_SMTP_KEY=votre_nouvelle_cle_smtp
   ```
4. Supprimez immédiatement l'ancienne clé compromise sur la console Brevo.

---

### D. Clés Cloudinary
1. Connectez-vous sur [Cloudinary Console](https://console.cloudinary.com/) > **Settings** > **Access Keys**.
2. Générez une nouvelle paire `API Key` / `API Secret`.
3. Mettez à jour les variables d'environnement de production :
   ```env
   CLOUDINARY_API_KEY=votre_nouvelle_cle
   CLOUDINARY_API_SECRET=votre_nouveau_secret
   ```
4. Révoquez l'ancienne clé après validation du bon chargement des images.

---

## 2. Procédure d'assainissement de l'historique Git

Si des fichiers `.env` contenant des secrets ont été archivés dans d'anciens commits Git :

1. **Installer l'outil officiel recommandé par Git** :
   ```bash
   pip install git-filter-repo
   ```
2. **Exécuter la purge du fichier `.env` sur tout l'historique** :
   ```bash
   git filter-repo --path .env --invert-paths --force
   ```
3. **Pousser l'historique assaini vers le dépôt distant** (nécessite les droits administrateur) :
   ```bash
   git push origin --force --all
   git push origin --force --tags
   ```
4. Informez tous les collaborateurs de cloner à nouveau le dépôt pour synchroniser l'arbre assaini.

---

## 3. Checklist de vérification avant déploiement en production

- [ ] `DEBUG=False` dans les variables de production.
- [ ] `SECRET_KEY` définie et différente de toute valeur de test.
- [ ] `ALLOWED_HOSTS=venus-luna.com,www.venus-luna.com` (sans wildcard `*`).
- [ ] `CASHPAY_SECRET_WEBHOOK` configuré.
- [ ] Le certificat SSL Let's Encrypt est actif sur le reverse proxy (HTTPS forcé).
- [ ] Les tests automatisés sont 100% verts :
  ```bash
  python manage.py test core.tests orders.tests accounts.tests --settings=config.settings_test
  ```
