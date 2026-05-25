# TODO — Blog détail 500 en production

- [ ] Ajouter un debug temporaire pour capturer la stacktrace du 500 sur la vue blog.detail (logs).
- [ ] Vérifier/ajuster le template `templates/blog/blog_detail.html` : sécuriser tous les accès à `post.author` (nullable) et à `protected_image` / tags.
- [ ] Mettre à jour `apps/blog/views.py` pour récupérer `author` et éviter toute exception côté template.
- [ ] Exécuter `python manage.py check` puis lancer un test local sur un post avec `author=None` et `image=None`.
- [ ] Relancer la prod et vérifier que la route `/blog/<id>/` ne renvoie plus 500.

