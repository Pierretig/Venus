import re
from django import forms

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
        """Nettoie et valide le numéro Togolais pour l'API"""
        phone = self.cleaned_data.get('phone')
        # On enlève tout ce qui n'est pas un chiffre
        digits = re.sub(r'\D', '', phone)

        # Si l'utilisateur a saisi 228XXXXXXXX
        if digits.startswith('228'):
            short_phone = digits[3:]
            full_phone = digits
        else:
            short_phone = digits
            full_phone = f"228{digits}"

        # Validation de la longueur (8 chiffres après le 228)
        if len(short_phone) != 8:
            raise forms.ValidationError("Le numéro doit comporter 8 chiffres (ex: 90010203).")

        # Préfixes valides Togo (Moov & TMoney)
        # 90-93, 96-99 (TogoCellulaire) / 70, 79 (Moov)
        valid_prefixes = ('90', '91', '92', '93', '96', '97', '98', '99', '79', '70', '71', '72', '78')
        if not short_phone.startswith(valid_prefixes):
            raise forms.ValidationError("Ce numéro ne semble pas appartenir à un opérateur Togolais valide.")

        return full_phone