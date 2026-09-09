# ...existing code...
from django.shortcuts import render, redirect
from django.contrib import messages
from apps.core.ratelimit import ratelimit
from .forms import ContactForm

@ratelimit(rate='5/m', key='ip', block=True, redirect_url='contact:contact', error_message="Trop de messages envoyés. Veuillez patienter une minute avant de renvoyer un message.")
def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            msg = form.save(commit=False)
            if request.user.is_authenticated:
                msg.user = request.user
            msg.save()
            messages.success(request, "Message envoyé. Nous vous répondrons bientôt.")
            return redirect('contact:contact')
        messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                'name': request.user.get_full_name() or request.user.username,
                'email': request.user.email
            }
        form = ContactForm(initial=initial)
    return render(request, 'pages/contact.html', {'form': form})
# ...existing code...