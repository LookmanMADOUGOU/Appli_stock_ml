from decimal import Decimal
from django import forms
from .models import Produit, Categorie, Vente, Approvisionnement, Client, Fournisseur, Depense, ClotureCaisse



class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'telephone', 'email', 'adresse', 'solde_credit']
        labels = {
            'nom': 'Nom du client',
            'telephone': 'Téléphone',
            'email': 'Adresse email',
            'adresse': 'Adresse physique',
            'solde_credit': 'Solde Crédit / En-cours (FCFA/€)',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom complet ou entreprise'}),
            'telephone': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: +229 90 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'client@email.com'}),
            'adresse': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Adresse de livraison ou facturation'}),
            'solde_credit': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
        }


class FournisseurForm(forms.ModelForm):
    class Meta:
        model = Fournisseur
        fields = ['nom', 'telephone', 'email', 'adresse', 'dette_fournisseur']
        labels = {
            'nom': 'Nom du fournisseur',
            'telephone': 'Téléphone',
            'email': 'Adresse email',
            'adresse': 'Adresse / Siège',
            'dette_fournisseur': 'Dette / En-cours (FCFA/€)',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom de la société fournisseur'}),
            'telephone': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: +229 21 00 00 00'}),
            'email': forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'contact@fournisseur.com'}),
            'adresse': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Adresse complète'}),
            'dette_fournisseur': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
        }


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = [
            'nom', 'reference', 'sku', 'code_barres', 'categorie',
            'stock_actuel', 'seuil_alerte', 'stock_maximum',
            'prix_unitaire', 'prix_achat', 'unite', 'statut', 'description'
        ]
        labels = {
            'nom': 'Nom du produit',
            'reference': 'Référence unique',
            'sku': 'Code SKU (optionnel)',
            'code_barres': 'Code-barres EAN/UPC',
            'categorie': 'Catégorie',
            'stock_actuel': 'Stock actuel',
            'seuil_alerte': 'Seuil d’alerte (Rupture/Faible)',
            'stock_maximum': 'Capacité stock max',
            'prix_unitaire': 'Prix de Vente Unitaire (FCFA/€)',
            'prix_achat': 'Prix d\'Achat / Coût (FCFA/€)',
            'unite': 'Unité de mesure (ex: kg, pièce, carton)',
            'statut': 'Statut produit',
            'description': 'Description du produit',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom du produit'}),
            'reference': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Référence unique'}),
            'sku': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: SKU-PROD-001'}),
            'code_barres': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: 6190000000000'}),
            'categorie': forms.Select(attrs={'class': 'input-field'}),
            'stock_actuel': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'stock_maximum': forms.NumberInput(attrs={'class': 'input-field', 'min': 1}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'prix_achat': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'unite': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'pièce, kg, l'}),
            'statut': forms.Select(attrs={'class': 'input-field'}),
            'description': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': 'Description ou caractéristiques du produit...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categorie'].required = False
        self.fields['categorie'].queryset = Categorie.objects.order_by('nom')
        self.fields['sku'].required = False
        self.fields['code_barres'].required = False
        self.fields['description'].required = False


class AjustementStockForm(forms.Form):
    produit = forms.ModelChoiceField(
        queryset=Produit.objects.order_by('nom'),
        widget=forms.Select(attrs={'class': 'input-field'}),
        label='Produit à ajuster'
    )
    nouveau_stock = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
        label='Nouveau stock réel (Inventaire)'
    )
    motif = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Inventaire mensuel, Casse, Périmé'}),
        label='Motif de l\'ajustement'
    )


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ['nom']
        labels = {
            'nom': 'Nom de la catégorie',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom de la catégorie'}),
        }


class VenteForm(forms.ModelForm):
    class Meta:
        model = Vente
        fields = ['produit', 'client', 'quantite', 'prix_unitaire', 'remise', 'mode_paiement', 'notes']
        labels = {
            'produit': 'Produit',
            'client': 'Client (Optionnel)',
            'quantite': 'Quantité vendue',
            'prix_unitaire': 'Prix unitaire (FCFA/€)',
            'remise': 'Remise globale (FCFA/€)',
            'mode_paiement': 'Mode de Paiement',
            'notes': 'Notes / Remarques',
        }
        widgets = {
            'produit': forms.Select(attrs={'class': 'input-field', 'id': 'id_vente_produit'}),
            'client': forms.Select(attrs={'class': 'input-field'}),
            'quantite': forms.NumberInput(attrs={'class': 'input-field', 'min': 1, 'id': 'id_vente_quantite'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'id': 'id_vente_prix_unitaire'}),
            'remise': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
            'mode_paiement': forms.Select(attrs={'class': 'input-field'}),
            'notes': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Remarques éventuelles'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].queryset = Produit.objects.order_by('nom')
        self.fields['client'].queryset = Client.objects.order_by('nom')
        self.fields['client'].required = False
        self.fields['prix_unitaire'].required = False
        self.fields['remise'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned_data = super().clean()
        produit = cleaned_data.get('produit')
        quantite = cleaned_data.get('quantite')

        if produit and quantite is not None:
            stock_disponible = produit.stock_actuel
            # En cas de modification d'une vente existante sur le même produit
            if self.instance and self.instance.pk and self.instance.produit_id == produit.pk:
                stock_disponible += self.instance.quantite

            if quantite > stock_disponible:
                self.add_error(
                    'quantite',
                    f"Stock insuffisant pour '{produit.nom}'. Disponible : {stock_disponible} unité(s), Demandé : {quantite}."
                )

        return cleaned_data


class ApprovisionnementForm(forms.ModelForm):
    class Meta:
        model = Approvisionnement
        fields = ['produit', 'fournisseur_fk', 'fournisseur', 'quantite', 'cout_unitaire', 'notes']
        labels = {
            'produit': 'Produit',
            'fournisseur_fk': 'Sélectionner un Fournisseur',
            'fournisseur': 'Ou saisir un Fournisseur (Libellé)',
            'quantite': 'Quantité reçue',
            'cout_unitaire': 'Coût d\'achat unitaire (FCFA/€)',
            'notes': 'Notes / N° Facture fournisseur',
        }
        widgets = {
            'produit': forms.Select(attrs={'class': 'input-field', 'id': 'id_appro_produit'}),
            'fournisseur_fk': forms.Select(attrs={'class': 'input-field', 'id': 'id_appro_fournisseur_fk'}),
            'fournisseur': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Si nouveau fournisseur'}),
            'quantite': forms.NumberInput(attrs={'class': 'input-field', 'min': 1, 'placeholder': 'ex: 50'}),
            'cout_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'placeholder': 'ex: 1500.00'}),
            'notes': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Facture F-2026-09, arrivage port'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].queryset = Produit.objects.order_by('nom')
        self.fields['fournisseur_fk'].queryset = Fournisseur.objects.order_by('nom')
        self.fields['fournisseur_fk'].required = False
        self.fields['fournisseur'].required = False
        self.fields['cout_unitaire'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned_data = super().clean()
        fk = cleaned_data.get('fournisseur_fk')
        nom = cleaned_data.get('fournisseur')

        if not fk and not (nom and nom.strip()):
            cleaned_data['fournisseur'] = 'Fournisseur Standard'
        elif fk and not (nom and nom.strip()):
            cleaned_data['fournisseur'] = fk.nom
        return cleaned_data


class ReglerDetteFournisseurForm(forms.Form):
    montant = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        label="Montant du règlement",
        widget=forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'placeholder': 'Montant en FCFA/€'})
    )
    moyen_reglement = forms.ChoiceField(
        choices=[
            ('VIREMENT', 'Virement bancaire'),
            ('ESPECES', 'Espèces'),
            ('CHEQUE', 'Chèque'),
            ('MOBILE_MONEY', 'Mobile Money'),
        ],
        label="Moyen de règlement",
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    notes = forms.CharField(
        required=False,
        label="Référence / Notes",
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Réf virement, quittance n°...'})
    )


class DepenseForm(forms.ModelForm):
    """
    Formulaire de saisie d'une charge d'exploitation (Phase 7 - Finances & Trésorerie).
    """
    class Meta:
        model = Depense
        fields = ['titre', 'categorie', 'montant', 'date_depense', 'beneficiaire', 'justificatif', 'notes']
        labels = {
            'titre': 'Intitulé de la dépense / charge',
            'categorie': 'Catégorie de charge',
            'montant': 'Montant décaissé (FCFA/€)',
            'date_depense': 'Date de la dépense',
            'beneficiaire': 'Bénéficiaire / Prestataire',
            'justificatif': 'N° Pièce / Facture justificative',
            'notes': 'Commentaire / Justification',
        }
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Loyer du local commercial, Facture SBEE/CIE...'}),
            'categorie': forms.Select(attrs={'class': 'input-field'}),
            'montant': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'placeholder': '0.00'}),
            'date_depense': forms.DateInput(attrs={'class': 'input-field', 'type': 'date'}),
            'beneficiaire': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom du prestataire ou fournisseur de service'}),
            'justificatif': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: FACT-2026-0042, Quittance...'}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Détails complémentaires sur la charge...'}),
        }


class ClotureCaisseForm(forms.ModelForm):
    """
    Formulaire de déclaration et de validation du Rapport Z de Clôture de Caisse (Phase 11).
    Le caissier renseigne le fond de caisse initial et les montants physiques réellement constatés.
    """
    class Meta:
        model = ClotureCaisse
        fields = [
            'fond_de_caisse_initial',
            'montant_especes_reel',
            'montant_carte_reel',
            'montant_mobile_money_reel',
            'montant_cheque_reel',
            'commentaire',
        ]
        labels = {
            'fond_de_caisse_initial': 'Fond de Caisse Initial (Monnaie d\'ouverture)',
            'montant_especes_reel': 'Espèces Physiques Comptées dans le Tiroir',
            'montant_carte_reel': 'Total Télécollecte TPE / Carte Bancaire',
            'montant_mobile_money_reel': 'Total Relevé Mobile Money',
            'montant_cheque_reel': 'Total Chèques Physiques',
            'commentaire': 'Remarques / Justification d\'un éventuel écart',
        }
        widgets = {
            'fond_de_caisse_initial': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': '0', 'id': 'id_fond_initial'}),
            'montant_especes_reel': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': '0', 'id': 'id_especes_reel'}),
            'montant_carte_reel': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': '0', 'id': 'id_carte_reel'}),
            'montant_mobile_money_reel': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': '0', 'id': 'id_momo_reel'}),
            'montant_cheque_reel': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': '0', 'id': 'id_cheque_reel'}),
            'commentaire': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Expliquer tout écart ou consigner les consignes de passation de caisse...'}),
        }


# ==================== GESTION DES UTILISATEURS & PROFILS (RBAC) ====================

from django.contrib.auth.models import User
from .permissions import ROLES_CHOICES, ROLE_ADMIN, ROLE_MANAGER, ROLE_MAGASINIER, ROLE_CAISSIER


class UtilisateurCreateForm(forms.Form):
    """
    Formulaire complet de création d'un utilisateur par l'administrateur.
    Permet d'assigner l'un des 4 profils de base (Admin, Manager, Magasinier, Caissier).
    """
    username = forms.CharField(
        max_length=150,
        required=True,
        label="Identifiant de connexion",
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': 'ex: caissier_jean, magasinier_ali',
            'autocomplete': 'off'
        })
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        label="Prénom",
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: Jean'})
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label="Nom de famille",
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'ex: KOFFI'})
    )
    email = forms.EmailField(
        required=False,
        label="Adresse Email",
        widget=forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'employe@smarttech.bj'})
    )
    role = forms.ChoiceField(
        choices=ROLES_CHOICES,
        required=True,
        label="Profil & Rôle Attribué",
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    password = forms.CharField(
        max_length=128,
        required=True,
        label="Mot de passe initial",
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': 'Minimum 6 caractères'})
    )
    password_confirm = forms.CharField(
        max_length=128,
        required=True,
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': 'Répétez le mot de passe'})
    )
    is_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Compte actif immédiatement",
        widget=forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500'})
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Cet identifiant est déjà utilisé. Veuillez en choisir un autre.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('password_confirm', "Les deux mots de passe ne correspondent pas.")
        if p1 and len(p1) < 6:
            self.add_error('password', "Le mot de passe doit comporter au moins 6 caractères.")
        return cleaned_data


class UtilisateurUpdateForm(forms.Form):
    """
    Formulaire d'édition d'un utilisateur existant (Informations personnelles, rôle, statut).
    """
    first_name = forms.CharField(
        max_length=150,
        required=False,
        label="Prénom",
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Prénom'})
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        label="Nom de famille",
        widget=forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom'})
    )
    email = forms.EmailField(
        required=False,
        label="Adresse Email",
        widget=forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'employe@smarttech.bj'})
    )
    role = forms.ChoiceField(
        choices=ROLES_CHOICES,
        required=True,
        label="Profil & Rôle Attribué",
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    is_active = forms.BooleanField(
        required=False,
        label="Compte actif",
        widget=forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded border-gray-300 text-cyan-600 focus:ring-cyan-500'})
    )


class UtilisateurPasswordResetForm(forms.Form):
    """
    Formulaire pour réinitialiser directement le mot de passe d'un utilisateur par l'administrateur.
    """
    new_password = forms.CharField(
        max_length=128,
        required=True,
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': 'Minimum 6 caractères'})
    )
    new_password_confirm = forms.CharField(
        max_length=128,
        required=True,
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': 'Répétez le mot de passe'})
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('new_password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('new_password_confirm', "Les deux mots de passe ne correspondent pas.")
        if p1 and len(p1) < 6:
            self.add_error('new_password', "Le mot de passe doit comporter au moins 6 caractères.")
        return cleaned_data




