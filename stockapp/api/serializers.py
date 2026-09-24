from rest_framework import serializers
from stockapp.models import AlerteRupture, Approvisionnement, Produit, Vente, MouvementStock


class ProduitSerializer(serializers.ModelSerializer):
    rupture = serializers.SerializerMethodField()
    prediction_rupture = serializers.SerializerMethodField()
    prediction_ml = serializers.SerializerMethodField()

    class Meta:
        model = Produit
        fields = [
            'id', 'nom', 'reference', 'sku', 'code_barres', 'description', 'unite',
            'stock_actuel', 'seuil_alerte', 'stock_maximum', 'statut_stock',
            'prix_unitaire', 'prix_achat', 'marge_unitaire', 'taux_marge',
            'valeur_stock_achat', 'valeur_stock_vente', 'statut',
            'rupture', 'prediction_ml', 'prediction_rupture',
            'date_creation', 'date_modification'
        ]

    def get_rupture(self, obj):
        return obj.rupture

    def get_prediction_ml(self, obj):
        return obj.prediction_ml

    def get_prediction_rupture(self, obj):
        return obj.prediction_rupture



class MouvementStockSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)
    utilisateur_username = serializers.CharField(source='utilisateur.username', read_only=True, default='')

    class Meta:
        model = MouvementStock
        fields = [
            'id', 'produit', 'produit_nom', 'quantite', 'type_mouvement',
            'stock_avant', 'stock_apres', 'date_mouvement', 'utilisateur',
            'utilisateur_username', 'reference', 'commentaire'
        ]


class VenteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)
    prix_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    benefice_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Vente
        fields = ['id', 'produit', 'produit_nom', 'quantite', 'prix_unitaire', 'prix_achat', 'prix_total', 'benefice_total', 'date_vente']


class ApprovisionnementSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)
    fournisseur_nom = serializers.CharField(source='nom_fournisseur', read_only=True)

    class Meta:
        model = Approvisionnement
        fields = [
            'id', 'produit', 'produit_nom', 'quantite',
            'fournisseur', 'fournisseur_fk', 'fournisseur_nom',
            'cout_unitaire', 'statut', 'notes', 'date_approvisionnement'
        ]


class AlerteRuptureSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)

    class Meta:
        model = AlerteRupture
        fields = ['id', 'produit', 'produit_nom', 'niveau', 'message', 'est_resolue', 'date_creation', 'date_resolution']
