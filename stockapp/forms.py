from django import forms
from .models import Produit, Categorie, Vente, Approvisionnement


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'reference', 'categorie', 'stock_actuel', 'seuil_alerte', 'prix_unitaire', 'prix_achat']
        labels = {
            'nom': 'Nom du produit',
            'reference': 'Référence',
            'categorie': 'Catégorie',
            'stock_actuel': 'Stock actuel',
            'seuil_alerte': 'Seuil d’alerte',
            'prix_unitaire': 'Prix de Vente Unitaire (FCFA/€)',
            'prix_achat': 'Prix d\'Achat / Revient (FCFA/€)',
        }
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nom du produit'}),
            'reference': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Référence unique'}),
            'categorie': forms.Select(attrs={'class': 'input-field'}),
            'stock_actuel': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'prix_achat': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
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
        fields = ['produit', 'quantite', 'prix_unitaire']
        labels = {
            'produit': 'Produit',
            'quantite': 'Quantité vendue',
            'prix_unitaire': 'Prix unitaire (FCFA/€)',
        }
        widgets = {
            'produit': forms.Select(attrs={'class': 'input-field', 'id': 'id_vente_produit'}),
            'quantite': forms.NumberInput(attrs={'class': 'input-field', 'min': 1, 'id': 'id_vente_quantite'}),
            'prix_unitaire': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'id': 'id_vente_prix_unitaire'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['produit'].queryset = Produit.objects.order_by('nom')
        self.fields['prix_unitaire'].required = False


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
