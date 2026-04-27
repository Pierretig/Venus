# TODO - Venus Luna - Corrections & Améliorations

## Partie 1 : Boutique & Sous-catégories ✅

### 1. Modèle (`apps/products/models.py`)
- [x] Renommer `related_name='children'` → `'subcategories'`
- [x] Mettre à jour `get_descendants()`

### 2. Vues (`apps/products/views.py`)
- [x] Remplacer `prefetch_related('children__children')` par `('subcategories__subcategories')`

### 3. Templates
- [x] `templates/products/product_list.html` : Remplacer `children` → `subcategories` + corriger CSS cartes
- [x] `templates/products/category_detail.html` : Remplacer `children` → `subcategories`
- [x] `templates/includes/navbar.html` : Supprimer dropdown "Catégories"

### 4. Migration
- [x] `python manage.py makemigrations products` → Migration `0006_alter_category_parent.py` générée
- [ ] `python manage.py migrate` → À exécuter sur le serveur PRODUCTION

## Partie 2 : Navbar & Corrections CSS ✅

### 1. Diagnostic
- [x] Identifier le CSS obsolète (topbar, mega-menu) qui cachait la navbar
- [x] Identifier `.navbar { display: none }` sur mobile
- [x] Identifier `.navbar { position: relative }` qui écrasait `.fixed-top`

### 2. Corrections CSS (`static/css/main_v2.css` & `staticfiles/css/main_v2.css`)
- [x] Supprimer l'ancien bloc CSS obsolète (topbar, header, mega-menu, navbar-inner)
- [x] Supprimer `.navbar { display: none }` en mobile
- [x] Supprimer `.navbar { position: relative; z-index: 500 }` qui écrasait `.fixed-top`
- [x] Logo arrondi (`border-radius: 50%`) avec bordure blanche et ombre
- [x] Navbar visible et fonctionnelle sur desktop et mobile

### 3. Templates
- [x] `templates/products/product_list.html` : Titres produits en vert `#1c683b`
- [x] `templates/base.html` : Vérifié (pas de texte parasite)

### 4. Admin
- [x] Bouton "Ajouter une sous-catégorie" déjà présent dans `templates/admin/products/category/change_form.html`

## Déploiement production - Actions requises ⚠️
- [ ] Exécuter `python manage.py migrate` sur le serveur
- [ ] Exécuter `python manage.py collectstatic --noinput` sur le serveur (si les CSS ne se mettent pas à jour automatiquement)
- [ ] Redémarrer le serveur (gunicorn/uwsgi)


