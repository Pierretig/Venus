from django import forms
from .models import Review

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['client_name', 'rating', 'title', 'comment']
        widgets = {
            'client_name': forms.TextInput(attrs={
                'class': 'form-control rounded-3',
                'placeholder': 'Votre prénom ou pseudonyme',
                'required': 'required'
            }),
            'rating': forms.HiddenInput(attrs={
                'id': 'id_rating_input',
                'min': '1',
                'max': '5',
                'value': '5',  # par défaut 5 étoiles
                'required': 'required'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control rounded-3',
                'placeholder': 'Titre de votre avis (optionnel)'
            }),
            'comment': forms.Textarea(attrs={
                'class': 'form-control rounded-3',
                'placeholder': 'Partagez votre expérience avec ce trésor...',
                'rows': 4,
                'required': 'required'
            }),
        }

    def clean_rating(self):
        rating = self.cleaned_data.get('rating')
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise forms.ValidationError("La note doit être un entier valide.")
        if rating < 1 or rating > 5:
            raise forms.ValidationError("La note doit être comprise entre 1 et 5 étoiles.")
        return rating

    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '').strip()
        if not comment:
            raise forms.ValidationError("Le commentaire ne peut pas être vide.")
        return comment
