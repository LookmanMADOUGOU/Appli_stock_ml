from rest_framework import serializers
from stockapp.models import AlerteRupture, Approvisionnement, Produit, Vente


class ProduitSerializer(serializers.ModelSerializer):
    rupture = serializers.SerializerMethodField()
    prediction_rupture = serializers.SerializerMethodField()
    prediction_ml = serializers.SerializerMethodField()

    class Meta:
        model = Produit
        fields = ['id', 'nom', 'reference', 'stock_actuel', 'seuil_alerte', 'prix_unitaire', 'prix_achat', 'marge_unitaire', 'rupture', 'prediction_ml', 'prediction_rupture']

    def get_rupture(self, obj):
        return obj.rupture

    def get_prediction_ml(self, obj):
        return obj.prediction_ml

    def get_prediction_rupture(self, obj):
        return obj.prediction_rupture


class VenteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)
    prix_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    benefice_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Vente
        fields = ['id', 'produit', 'produit_nom', 'quantite', 'prix_unitaire', 'prix_achat', 'prix_total', 'benefice_total', 'date_vente']


class ApprovisionnementSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)

    class Meta:
        model = Approvisionnement
        fields = ['id', 'produit', 'produit_nom', 'quantite', 'fournisseur', 'date_approvisionnement']


class AlerteRuptureSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)

    class Meta:
        model = AlerteRupture
        fields = ['id', 'produit', 'produit_nom', 'niveau', 'message', 'est_resolue', 'date_creation', 'date_resolution']
