# apps/blog/views.py
from django.shortcuts import render, get_object_or_404
from .models import Post

def index(request): # <--- Le nom doit être identique à celui dans urls.py
    posts = Post.objects.filter(published=True).order_by('-created_at')
    return render(request, 'blog/blog_list.html', {'posts': posts})

def detail(request, post_id):
    post = get_object_or_404(Post, id=post_id, published=True)

    # Sécurité prod : author est nullable (SET_NULL). Le template ne doit jamais
    # appeler une méthode sur None.
    author_name = ""
    if getattr(post, 'author', None):
        # get_full_name existe sur User ; fallback au nom si besoin
        try:
            author_name = post.author.get_full_name() or ""
        except Exception:
            author_name = str(post.author)

    context = {
        'post': post,
        'author_name': author_name,
    }
    return render(request, 'blog/blog_detail.html', context)
