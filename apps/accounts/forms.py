from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from django.db import transaction
from apps.core.validators import validate_togo_phone
from .models import Profile


# ---------------------------------------------------------------------------
# Formulaire d'inscription enrichi
# ---------------------------------------------------------------------------

class RegisterForm(UserCreationForm):
    """
    Hérite de UserCreationForm et collecte :
      - Prénom, Nom (User.first_name / last_name) — obligatoires
      - Nom d'utilisateur (User.username) — obligatoire
      - Adresse e-mail (User.email) — obligatoire, unique parmi les comptes ayant un email
      - Téléphone (Profile.phone) — obligatoire, validé format togolais
      - Adresse (Profile.address) — facultatif
      - Ville (Profile.city) — facultatif
      - Mot de passe + confirmation — obligatoires (hérités de UserCreationForm)

    Rétrocompatibilité :
      - Les anciens comptes avec email="" ne sont pas bloqués par la vérification d'unicité.
      - Le signal post_save crée automatiquement le Profile ; save() le récupère ensuite.
    """

    # --- Champs User supplémentaires ---
    first_name = forms.CharField(
        label="Prénom",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Votre prénom',
            'class': 'form-control',
            'autocomplete': 'given-name',
        }),
        error_messages={'required': "Veuillez saisir votre prénom."},
    )
    last_name = forms.CharField(
        label="Nom",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Votre nom de famille',
            'class': 'form-control',
            'autocomplete': 'family-name',
        }),
        error_messages={'required': "Veuillez saisir votre nom."},
    )
    email = forms.EmailField(
        label="Adresse e-mail",
        required=True,
        widget=forms.EmailInput(attrs={
            'placeholder': 'votre@email.com',
            'class': 'form-control',
            'autocomplete': 'email',
        }),
        error_messages={
            'required': "Veuillez saisir votre adresse e-mail.",
            'invalid': "Veuillez saisir une adresse e-mail valide.",
        },
    )

    # --- Champs Profile ---
    phone = forms.CharField(
        label="Téléphone (WhatsApp)",
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': '90 01 02 03 ou 228 90 01 02 03',
            'class': 'form-control',
            'autocomplete': 'tel',
        }),
        error_messages={'required': "Veuillez saisir votre numéro de téléphone."},
    )
    address = forms.CharField(
        label="Adresse / Quartier (facultatif)",
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Quartier, précisions livraison…',
            'class': 'form-control',
            'autocomplete': 'street-address',
        }),
    )
    city = forms.CharField(
        label="Ville (facultatif)",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Lomé',
            'class': 'form-control',
            'autocomplete': 'address-level2',
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # Ordre des champs déclarés sur le modèle
        fields = ('first_name', 'last_name', 'username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ordre ergonomique des champs : coordonnées avant les mots de passe
        desired_order = [
            'first_name',
            'last_name',
            'username',
            'email',
            'phone',
            'address',
            'city',
            'password1',
            'password2',
        ]
        self.fields = {k: self.fields[k] for k in desired_order if k in self.fields}

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError("Veuillez saisir votre adresse e-mail.")
        # Unicité : on vérifie seulement parmi les utilisateurs ayant déjà un email non vide.
        # Les anciens comptes avec email="" ne rentrent pas dans cette vérification.
        if User.objects.filter(email__iexact=email).exclude(email='').exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée par un autre compte.")
        return email

    def clean_phone(self):
        return validate_togo_phone(self.cleaned_data.get('phone', ''))

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        # Champs User
        user.first_name = self.cleaned_data.get('first_name', '').strip()
        user.last_name = self.cleaned_data.get('last_name', '').strip()
        user.email = self.cleaned_data['email'].strip().lower()
        if commit:
            user.save()  # Le signal post_save crée automatiquement Profile
            # Mise à jour du profil (signal l'a déjà créé via get_or_create)
            profile = user.profile
            profile.phone = self.cleaned_data.get('phone', '')
            profile.address = self.cleaned_data.get('address', '')
            profile.city = self.cleaned_data.get('city', '')
            profile.save()
        return user


# ---------------------------------------------------------------------------
# Formulaire de connexion — username OU adresse e-mail
# ---------------------------------------------------------------------------

class EmailOrUsernameAuthForm(AuthenticationForm):
    """
    Étend AuthenticationForm pour accepter un nom d'utilisateur OU une adresse e-mail.

    Logique :
    - Si la valeur saisie contient '@' -> recherche par email -> récupère le username associé
    - Sinon -> utilise la valeur telle quelle comme username
    - L'authentification finale reste confiée à Django (vérification du mot de passe hashé)
    - Rétrocompatible : les anciens utilisateurs sans email peuvent toujours se connecter via username
    """
    username = forms.CharField(
        label="Nom d'utilisateur ou adresse e-mail",
        widget=forms.TextInput(attrs={
            'autofocus': True,
            'placeholder': "Nom d'utilisateur ou e-mail",
            'class': 'form-control',
            'autocomplete': 'username',
        }),
    )

    def clean(self):
        username_or_email = self.cleaned_data.get('username', '').strip()
        password = self.cleaned_data.get('password')

        if username_or_email and password:
            # Detection : si '@' present -> tentative de connexion par email
            if '@' in username_or_email:
                try:
                    # Recherche insensible a la casse, parmi les comptes ayant un email
                    user_obj = User.objects.get(email__iexact=username_or_email)
                    # Substitue le username reel pour l'authentification Django standard
                    username_or_email = user_obj.username
                except User.DoesNotExist:
                    # Email introuvable : on laisse Django generer l'erreur standard
                    pass
                except User.MultipleObjectsReturned:
                    # Cas rare (email en doublon en base) : on laisse Django gerer
                    pass

            # Authentification standard Django (verifie username + password hache)
            self.cleaned_data['username'] = username_or_email
            self.user_cache = authenticate(
                self.request,
                username=username_or_email,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


# ---------------------------------------------------------------------------
# Formulaire de modification de profil (existant — conserve intact)
# ---------------------------------------------------------------------------

class UserProfileForm(forms.ModelForm):
    # Champs additionnels venant du modele Profile
    phone = forms.CharField(
        label="Telephone (WhatsApp)",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '+228...', 'class': 'form-control'})
    )
    address = forms.CharField(
        label="Quartier / Precisions livraison",
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
    )
    city = forms.CharField(
        label="Ville",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Lomé', 'class': 'form-control'})
    )
    avatar = forms.ImageField(
        label="Photo de profil (Avatar)",
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/png,image/jpeg,image/webp'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'readonly': 'readonly', 'class': 'form-control'}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            return validate_togo_phone(phone)
        return ''

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'size'):
            max_size = 2 * 1024 * 1024
            if avatar.size > max_size:
                raise forms.ValidationError("L'image ne doit pas dépasser 2 Mo.")
            allowed_types = ['image/jpeg', 'image/png', 'image/webp']
            content_type = getattr(avatar, 'content_type', '')
            if content_type and content_type not in allowed_types:
                raise forms.ValidationError("Format d'image non supporté. Formats acceptés : JPEG, PNG, WEBP.")
        return avatar

    def clean_email(self):
        # Sécurité anti-falsification : l'adresse email ne peut pas être modifiée via ce formulaire
        if self.instance and self.instance.pk:
            return self.instance.email
        return self.cleaned_data.get('email')

    def __init__(self, *args, **kwargs):
        super(UserProfileForm, self).__init__(*args, **kwargs)
        # Sécurité : le champ email est verrouillé côté serveur (disabled=True ignore tout POST falsifié)
        if 'email' in self.fields:
            self.fields['email'].disabled = True
        # Si l'utilisateur a deja un profil, on pre-remplit les champs phone et address
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['phone'].initial = self.instance.profile.phone
            self.fields['address'].initial = self.instance.profile.address
            self.fields['city'].initial = self.instance.profile.city

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            if hasattr(user, 'profile'):
                profile = user.profile
                profile.phone = self.cleaned_data.get('phone')
                profile.address = self.cleaned_data.get('address')
                profile.city = self.cleaned_data.get('city', '')
                # L'image n'est mise a jour que si un nouveau fichier est fourni
                if self.cleaned_data.get('avatar'):
                    profile.avatar = self.cleaned_data.get('avatar')
                profile.save()
        return user