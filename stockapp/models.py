from django.db import models


class Categorie(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Produit(models.Model):
    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='produits'
    )

    nom = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, unique=True)
    stock_actuel = models.IntegerField(default=0)
    seuil_alerte = models.IntegerField(default=10)

    @property
    def rupture(self):
        # Considérer en rupture lorsque le stock est inférieur ou égal au seuil
        return self.stock_actuel <= self.seuil_alerte
    
    @property
    def prediction_rupture(self):

        ventes = Vente.objects.filter(
            produit=self
        )

        if not ventes.exists():
            return "Pas assez de données"

        total = sum(
            v.quantite
            for v in ventes
        )

        moyenne = total / ventes.count()

        if moyenne == 0:
            return "Stock stable"

        jours = self.stock_actuel / moyenne

        return round(jours, 1)
    @property
    def prediction_ml(self):
        """
        Prédire la quantité de vente pour le jour suivant.
        """
        from .services.prediction_service import predict_sales
        return predict_sales(self)

    @property
    def prediction_stockout(self):
        """
        Prédire le nombre de jours avant rupture de stock.
        """
        from .services.prediction_service import predict_stockout
        return predict_stockout(self)
    
    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Vente(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField()
    date_vente = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_vente']

    def __str__(self):
        return f"{self.produit.nom} - {self.quantite}"


class Approvisionnement(models.Model):
    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE
    )

    quantite = models.PositiveIntegerField()

    date_approvisionnement = models.DateTimeField(
        auto_now_add=True
    )

    fournisseur = models.CharField(
        max_length=200
    )

    class Meta:
        ordering = ['-date_approvisionnement']

    def __str__(self):
        return f"{self.produit.nom} +{self.quantite}"


class AlerteRupture(models.Model):
    """
    Modèle pour enregistrer les alertes de rupture de stock.
    """
    
    NIVEAU_CHOICES = [
        ('info', 'Information'),
        ('alerte', 'Alerte'),
        ('critique', 'Critique'),
    ]

    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name='alertes'
    )

    niveau = models.CharField(
        max_length=10,
        choices=NIVEAU_CHOICES,
        default='alerte'
    )

    message = models.TextField()

    date_creation = models.DateTimeField(auto_now_add=True)

    date_resolution = models.DateTimeField(
        null=True,
        blank=True
    )

    est_resolue = models.BooleanField(
        default=False
    )

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Alerte rupture'
        verbose_name_plural = 'Alertes ruptures'

    def __str__(self):
        etat = "✓ Résolue" if self.est_resolue else "⚠ Active"
        return f"{self.produit.nom} - {etat} ({self.get_niveau_display()})"