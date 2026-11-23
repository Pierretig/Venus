from django import forms
from apps.core.validators import validate_togo_phone

class CheckoutForm(forms.Form):
    full_name = forms.CharField(
        label="Nom complet", 
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Jean Dossou'})
    )
    
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'votre@email.com'})
    )
    
    phone = forms.CharField(
        label="Téléphone (T-Money ou Moov)", 
        max_length=50, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 90 01 02 03'})
    )
    
    address = forms.CharField(
        label="Adresse précise", 
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Quartier, repères...'})
    )
    
    city = forms.CharField(
        label="Ville", 
        max_length=150, 
        initial="Lomé",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    country = forms.CharField(
        label="Pays", 
        max_length=100, 
        initial="Togo",
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
    )
    
    notes = forms.CharField(
        label="Notes pour la livraison (optionnel)", 
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Ex: Préciser une heure de passage'}),
        required=False
    )

    def clean_full_name(self):
        """Met en majuscule la première lettre de chaque nom"""
        return self.cleaned_data.get('full_name').title()

    def clean_phone(self):
        """Nettoie et valide le numéro Togolais pour l'API via le validateur centralisé."""
        return validate_togo_phone(self.cleaned_data.get('phone'))