# TODO - Système de Watermark Intelligent Cloudinary

## Plan d'implémentation

### Phase 1 : Fichiers de base (utils, templatetags, tests)
- [ ] 1. Créer `apps/core/utils/__init__.py`
- [ ] 2. Créer `apps/core/utils/watermark.py` — `get_clean_url()` et `get_watermarked_url()`
- [ ] 3. Créer `apps/core/templatetags/cloudinary_extras.py` — tag `{% protected_image %}`
- [ ] 4. Créer `apps/core/tests/test_watermark.py` — tests unitaires

### Phase 2 : Vue proxy et URLs
- [ ] 5. Modifier `apps/core/views.py` — ajouter `serve_image()`
- [ ] 6. Modifier `apps/core/urls.py` — route `/media/image/<str:model>/<int:pk>/`
- [ ] 7. Modifier `config/urls.py` — inclure la nouvelle route
- [ ] 8. Modifier `config/settings.py` — `WATERMARK_TEXT`, `SITE_DOMAIN`

### Phase 3 : Protections front-end
- [ ] 9. Modifier `static/css/main_v2.css` — classe `.protected-image`
- [ ] 10. Modifier `static/js/main.js` — bloc clic droit + drag
- [ ] 11. Modifier `templates/base.html` — charger le JS/CSS si besoin

### Phase 4 : Templates (remplacer toutes les URLs directes)
- [ ] 12. `templates/products/product_list.html`
- [ ] 13. `templates/products/product_detail.html`
- [ ] 14. `templates/products/wishlist.html`
- [ ] 15. `templates/pages/home.html`
- [ ] 16. `templates/blog/blog_list.html`
- [ ] 17. `templates/blog/blog_detail.html`
- [ ] 18. `templates/orders/cart.html`
- [ ] 19. `templates/orders/checkout.html`
- [ ] 20. `templates/orders/confirm.html`
- [ ] 21. `templates/accounts/profile.html`
- [ ] 22. `templates/includes/navbar.html`

### Phase 5 : Vérification finale
- [ ] 23. Vérifier qu'aucun `{{ .image.url }}` direct ne reste dans les templates
- [ ] 24. Vérifier que le site fonctionne (aucune URL cassée)

