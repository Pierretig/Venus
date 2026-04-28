# TODO - Uniformisation verts + Correction Admin

## Couleur cible : #1c683b (vert principal), #155430 (vert foncé/dégradés)

### Fichiers modifiés

- [x] `apps/products/admin.py` — Ajout `list_display_links = ("name",)` pour rendre le nom du produit cliquable en bleu dans l'admin
- [x] `static/css/main_v2.css` — Remplacement `#0b7a3b` par `#155430`
- [x] `staticfiles/css/main_v2.css` — Synchronisé avec static/css/main_v2.css
- [x] `templates/pages/home.html` — Harmonisation des verts
- [x] `templates/accounts/login.html` — `--venus-vert: #1c683b`
- [x] `templates/accounts/register.html` — `--venus-vert: #1c683b`
- [x] `templates/accounts/dashboard.html` — `--venus-vert: #1c683b`
- [x] `templates/accounts/edit_profile.html` — `--venus-vert: #1c683b`
- [x] `templates/accounts/profile.html` — `--venus-vert: #1c683b`
- [x] `templates/blog/blog_list.html` — `--venus-vert: #1c683b`
- [x] `templates/blog/blog_detail.html` — `--venus-vert: #1c683b`
- [x] `templates/admin_custom/dashboard.html` — `--venus-vert: #1c683b`
- [x] `templates/orders/cart.html` — `--venus-vert: #1c683b`
- [x] `templates/orders/confirm.html` — `--venus-vert: #1c683b` (restauré après corruption)
- [x] `templates/orders/order_success.html` — `--venus-vert: #1c683b`
- [x] `templates/orders/history.html` — `--venus-vert: #1c683b`
- [x] `templates/pages/faq.html` — `--venus-aura: #1c683b`
- [x] `templates/pages/contact.html` — `--venus-aura: #1c683b`
- [x] `templates/pages/404.html` — `--venus-aura: #155430`
- [x] `templates/pages/cgv.html` — `--venus-vert-profond: #155430`
- [x] `templates/pages/about.html` — `--venus-aura: #155430`
- [x] `templates/orders/order_confirmation.html` — `#1c683b`, `#155430`
- [x] `templates/orders/pdf_receipt.html` — `#1c683b`, `#155430`
- [x] `templates/products/product_detail.html` — `--venus-aura: #155430`

### Résumé des corrections

1. **Uniformisation des verts** : Toutes les teintes vertes dispersées (`#145c44`, `#0a3d2d`, `#217a10`, `#09b920`, `#259b35`, `#1dcc34`, `#61813b`, `#349b4b`, `#20c449`, `#15b149`, `#189128`, `#289b28`, `#229e47`, `#229b40`, `#128C7E`, `#25aa37`, `#0b7a3b`, `#2d8131`, `#408540`) ont été remplacées par :
   - **#1c683b** comme vert principal
   - **#155430** comme vert foncé (pour les dégradés, hover, ombres)

2. **Correction Admin Django** : Ajout de `list_display_links = ("name",)` dans `ProductAdmin` pour que le nom du produit apparaisse en bleu et soit cliquable dans la liste des produits de l'interface admin, redirigeant vers la page de modification.

3. **SEO conforme** : Aucune balise meta, structure HTML ou contenu SEO n'a été modifié. Les corrections sont strictement visuelles (CSS/couleurs) et fonctionnelles (admin).

