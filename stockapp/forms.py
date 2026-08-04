from django import forms
from .models import Produit, Categorie, Vente, Approvisionnement


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'reference', 'categorie', 'prix_achat', 'prix_unitaire', 'stock_actuel', 'seuil_alerte']
        labels = {
            'nom': 'Nom du produit',
            'reference': 'Référence',
            'categorie': 'Catégorie',
            'prix_achat': 'Prix d’achat / de revient (FCFA/€)',
            'prix_unitaire': 'Prix de vente unitaire (FCFA/€)',
            'stock_actuel': 'Stock actuel',
            'seuil_alerte': 'Seuil d’alerte',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom du produit'}),
            'reference': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Référence unique'}),
            'categorie': forms.Select(attrs={'class': 'input-field'}),
            'prix_achat': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0, 'placeholder': '0.00'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0, 'placeholder': '0.00'}),
            'stock_actuel': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categorie'].required = False
        self.fields['categorie'].queryset = Categorie.objects.order_by('nom')


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
        fields = ['produit', 'quantite', 'prix_unitaire', 'prix_achat']
        labels = {
            'produit': 'Produit',
            'quantite': 'Quantité vendue',
            'prix_unitaire': 'Prix de vente unitaire (laisser vide pour le prix catalogue)',
            'prix_achat': 'Prix d’achat unitaire (optionnel)',
        }
        widgets = {
            'produit': forms.Select(attrs={'class': 'input-field', 'id': 'id_vente_produit'}),
            'quantite': forms.NumberInput(attrs={'class': 'input-field', 'min': 1, 'id': 'id_vente_quantite'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0, 'placeholder': 'Prix vente unitaire', 'id': 'id_vente_prix_unitaire'}),
            'prix_achat': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0, 'placeholder': 'Prix d’achat unitaire', 'id': 'id_vente_prix_achat'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].queryset = Produit.objects.order_by('nom')
        self.fields['prix_unitaire'].required = False
        self.fields['prix_achat'].required = False


class ApprovisionnementForm(forms.ModelForm):
    class Meta:
        model = Approvisionnement
        fields = ['produit', 'quantite', 'fournisseur']
        labels = {
            'produit': 'Produit',
            'quantite': 'Quantité à ajouter',
            'fournisseur': 'Fournisseur',
        }
        widgets = {
            'produit': forms.Select(attrs={'class': 'input-field'}),
            'quantite': forms.NumberInput(attrs={'class': 'input-field', 'min': 1}),
            'fournisseur': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom du fournisseur'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].queryset = Produit.objects.order_by('nom')
