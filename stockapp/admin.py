from django.contrib import admin
from django.db.models import F
from .models import (
    Categorie,
    Produit,
    Vente,
    Approvisionnement,
    AlerteRupture
)


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):

    list_display = (
        'nom',
        'categorie',
        'stock_actuel',
        'seuil_alerte',
        'etat_rupture',
        'prevision',
        'prevision_ml'
    )

    # `rupture` est une propriété, on utilise un filtre personnalisé
    class RuptureFilter(admin.SimpleListFilter):
        title = 'Rupture'
        parameter_name = 'rupture'

        def lookups(self, request, model_admin):
            return (
                ('rupture', 'En rupture'),
                ('ok', 'Disponible'),
            )

        def queryset(self, request, queryset):
            val = self.value()
            if val == 'rupture':
                return queryset.filter(stock_actuel__lte=F('seuil_alerte'))
            if val == 'ok':
                return queryset.filter(stock_actuel__gt=F('seuil_alerte'))
            return queryset

    list_filter = ('categorie', RuptureFilter)
    search_fields = ('nom', 'reference')

    def prevision_ml(self, obj):
        valeur = obj.prediction_ml
        if isinstance(valeur, str):
            return valeur
        return f"{valeur} unités"

    prevision_ml.short_description = (
    "Prévision IA"
    )
    
    def etat_rupture(self, obj):
        if obj.rupture:
            return "⚠ Rupture"

        return "✓ Disponible"

    def prevision(self, obj):
        valeur = obj.prediction_rupture

        if isinstance(valeur, str):
            return valeur

        return f"{valeur} jours"

    etat_rupture.short_description = "État"

    prevision.short_description = "Prévision"


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ('produit', 'quantite', 'date_vente')
    list_filter = ('date_vente', 'produit')
    search_fields = ('produit__nom',)


@admin.register(Approvisionnement)
class ApprovisionnementAdmin(admin.ModelAdmin):
    list_display = ('produit', 'quantite', 'fournisseur', 'date_approvisionnement')
    list_filter = ('date_approvisionnement', 'fournisseur')
    search_fields = ('produit__nom', 'fournisseur')


@admin.register(AlerteRupture)
class AlerteRuptureAdmin(admin.ModelAdmin):
    list_display = (
        'produit',
        'niveau',
        'est_resolue',
        'date_creation',
        'date_resolution'
    )
    
    list_filter = ('niveau', 'est_resolue', 'date_creation')


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ('nom',)
    search_fields = ('nom',)
