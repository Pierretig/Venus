# Plan d'implémentation — Gestion intelligente des stocks

## Étape 1 — Migration sûre (synchronisation DB)
- [x] Créer `apps/products/migrations/0008_stock_features.py` :
  - Ajout champs `restocking_date`, `low_stock_threshold`, `low_stock_alert_sent` sur Product
  - Création tables `StockMovement`, `StockReservation`, `AdminNotification`
  - Migration 100% réversible, sans perte de données
- [x] Appliquer la migration (à exécuter sur le serveur — la DB de prod n'est pas joignable en local)
- [x] Corriger bug pré-existant `CheckConstraint` (check → condition) sur Product

## Étape 2 — Helpers & logique métier (DRY)
- [x] Créer `apps/products/stock_utils.py` :
  - `reserve_stock(product, session_key, qty)` : réservation atomique 15 min
  - `release_reservation_session(session_key)` : libération des réservations d'une session
  - `release_expired_reservations()` : purge des réservations expirées
  - `get_available_stock(product, exclude_session)` : stock réellement vendable
- [x] Ajout propriétés lecture seule sur `Product` : `is_out_of_stock`, `is_low_stock`, `available_stock`

## Étape 3 — Vue tableau de bord des stocks
- [ ] `apps/products/views.py` : vue `stock_dashboard` (ruptures, stock faible, best-sellers, jamais vendus, derniers mouvements, alertes, KPI)
- [ ] `apps/products/urls.py` : route `stock-dashboard/`
- [ ] `templates/admin_custom/dashboard.html` : section stocks
- [ ] Enregistrement `StockMovement`, `StockReservation`, `AdminNotification` dans l'admin

## Étape 4 — Panier & réservation
- [ ] `apps/orders/views.py` : `cart_add` (vérif stock dispo + réservation), `cart_update`/`cart_remove` (maj réservation), `checkout` (blocage indispo), `payment_success` (libération)
- [ ] `apps/orders/models.py` : statut `refunded`
- [ ] `apps/orders/signals.py` : déduction/réintégration atomique anti-négatif + traçage StockMovement (SALE/CANCEL/REFUND)

## Étape 5 — Template produits
- [ ] `templates/products/product_detail.html` : badge "En rupture", désactivation bouton, date de réappro
- [ ] `templates/products/product_list.html` : badge stock faible/rupture

## Étape 6 — Commande cron + tests
- [ ] `apps/orders/management/commands/release_expired_reservations.py`
- [ ] `apps/products/tests/test_stock.py`

## Étape 7 — Vérifications finales
- [ ] `python manage.py makemigrations --check` (pas de migration pendante)
- [ ] `python manage.py migrate` (synchronisation)
- [ ] `python manage.py test apps.products`
