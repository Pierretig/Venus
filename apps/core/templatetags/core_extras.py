from django import template

register = template.Library()


@register.filter
def chunk(value, chunk_size):
    """Découpe une séquence en sous-listes de taille au plus chunk_size."""
    try:
        size = int(chunk_size)
    except (TypeError, ValueError):
        size = 1
    if size < 1:
        size = 1
    items = list(value)
    return [items[i : i + size] for i in range(0, len(items), size)]
