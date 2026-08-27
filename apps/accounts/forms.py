from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import Profile


# ---------------------------------------------------------------------------
# Formulaire d'inscription — email obligatoire pour les nouveaux comptes
# ---------------------------------------------------------------------------

class RegisterForm(UserCreationForm):
    """
    Hérite de UserCreationForm et ajoute un champ email obligatoire.

    Règles :
    - email obligatoire pour les nouveaux comptes
    - validation de format (EmailField natif)
    - unicité : refusée uniquement si un autre compte possède DÉJÀ cet email
      (les anciens comptes sans email conservent email="" et ne bloquent pas)
    - les anciens comptes sans email ne sont PAS impactés
    """
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

    class Meta(UserCreationForm.Meta):
        model = User
        # username vient de UserCreationForm.Meta, on ajoute email entre username et passwords
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError("Veuillez saisir votre adresse e-mail.")
        # Unicité : on vérifie seulement parmi les utilisateurs ayant déjà un email non vide.
        # Les anciens comptes avec email="" ne rentrent pas dans cette vérification.
        if User.objects.filter(email__iexact=email).exclude(email="").exists():
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée par un autre compte.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        # Normalisation de l'email (minuscules)
        user.email = self.cleaned_data['email'].strip().lower()
        if commit:
            user.save()
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

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'readonly': 'readonly', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super(UserProfileForm, self).__init__(*args, **kwargs)
        # Si l'utilisateur a deja un profil, on pre-remplit les champs phone et address
        if self.instance and hasattr(self.instance, 'profile'):
            self.fields['phone'].initial = self.instance.profile.phone
            self.fields['address'].initial = self.instance.profile.address

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            if hasattr(user, 'profile'):
                profile = user.profile
                profile.phone = self.cleaned_data.get('phone')
                profile.address = self.cleaned_data.get('address')
                # L'image n'est mise a jour que si un nouveau fichier est fourni
                if self.cleaned_data.get('avatar'):
                    profile.avatar = self.cleaned_data.get('avatar')
                profile.save()
        return user