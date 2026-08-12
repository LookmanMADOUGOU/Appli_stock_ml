from django.db import models
from django.db.models import Sum


class Categorie(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.nom


class Produit(models.Model):
    nom = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, unique=True)
    stock_actuel = models.IntegerField(default=0)
    seuil_alerte = models.IntegerField(default=5)
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    @property
    def rupture(self):
        """Déterminer si le produit est en rupture de stock."""
        return self.stock_actuel <= self.seuil_alerte

    @property
    def marge_unitaire(self):
        """Marge unitaire sur le produit."""
        return self.prix_unitaire - self.prix_achat

    @property
    def prediction_ml(self):
        """Prédire les ventes du jour suivant."""
        from .services.prediction_service import predict_sales
        return predict_sales(self)

    @property
    def prediction_stockout(self):
        """Prédire le nombre de jours avant rupture de stock."""
        from .services.prediction_service import predict_stockout
        return predict_stockout(self)

    @property
    def prediction_rupture(self):
        """Prédire le nombre de jours avant rupture de stock (alias)."""
        from .services.prediction_service import predict_stockout
        return predict_stockout(self)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Vente(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_vente = models.DateTimeField(auto_now_add=True)

    @property
    def prix_total(self):
        return self.quantite * self.prix_unitaire

    @property
    def marge_unitaire(self):
        return self.prix_unitaire - self.prix_achat

    @property
    def benefice_total(self):
        return (self.prix_unitaire - self.prix_achat) * self.quantite

    def save(self, *args, **kwargs):
        if not self.prix_unitaire and self.produit:
            self.prix_unitaire = self.produit.prix_unitaire
        if not self.prix_achat and self.produit:
            self.prix_achat = self.produit.prix_achat
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date_vente']

    def __str__(self):
        return f"{self.produit.nom} - {self.quantite} x {self.prix_unitaire}"


class Approvisionnement(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField()
    date_approvisionnement = models.DateTimeField(auto_now_add=True)
    fournisseur = models.CharField(max_length=200)

    class Meta:
        ordering = ['-date_approvisionnement']

    def __str__(self):
        return f"{self.produit.nom} +{self.quantite}"


class AlerteRupture(models.Model):
    NIVEAU_CHOICES = [
        ('info', 'Information'),
        ('alerte', 'Alerte'),
        ('critique', 'Critique'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='alertes')
    niveau = models.CharField(max_length=10, choices=NIVEAU_CHOICES, default='alerte')
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    est_resolue = models.BooleanField(default=False)
    date_resolution = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"Alerte {self.niveau}: {self.produit.nom}"