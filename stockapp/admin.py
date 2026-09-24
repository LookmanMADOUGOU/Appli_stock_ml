from django.contrib import admin
from django.db.models import F
from .models import (
    Categorie,
    Produit,
    Vente,
    Approvisionnement,
    AlerteRupture,
    MouvementStock,
    Client,
    Fournisseur,
    Depense,
    JournalAudit,
    ClotureCaisse,
    Notification,
)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email', 'solde_credit', 'date_creation')
    search_fields = ('nom', 'telephone', 'email')


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email', 'dette_fournisseur', 'date_creation')
    search_fields = ('nom', 'telephone', 'email')



@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = (
        'nom',
        'reference',
        'categorie',
        'stock_actuel',
        'seuil_alerte',
        'stock_maximum',
        'statut_stock',
        'prix_unitaire',
        'prix_achat',
        'prevision_ml'
    )

    class RuptureFilter(admin.SimpleListFilter):
        title = 'Rupture'
        parameter_name = 'rupture'

        def lookups(self, request, model_admin):
            return (
                ('rupture', 'En rupture / Faible'),
                ('ok', 'Stock Normal'),
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

    prevision_ml.short_description = "Prévision IA"


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = (
        'produit',
        'type_mouvement',
        'quantite',
        'stock_avant',
        'stock_apres',
        'utilisateur',
        'date_mouvement'
    )
    list_filter = ('type_mouvement', 'date_mouvement', 'produit')
    search_fields = ('produit__nom', 'reference', 'commentaire')
    readonly_fields = ('date_mouvement',)


@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = ('produit', 'quantite', 'prix_unitaire', 'prix_total', 'benefice_total', 'date_vente')
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


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = ('titre', 'categorie', 'montant', 'date_depense', 'beneficiaire', 'utilisateur')
    list_filter = ('categorie', 'date_depense')
    search_fields = ('titre', 'beneficiaire', 'justificatif')


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    list_display = ('date_creation', 'action', 'module', 'objet_concerne', 'utilisateur', 'adresse_ip')
    list_filter = ('action', 'module', 'date_creation')
    search_fields = ('objet_concerne', 'description', 'utilisateur__username')
    readonly_fields = ('date_creation',)


@admin.register(ClotureCaisse)
class ClotureCaisseAdmin(admin.ModelAdmin):
    list_display = ('reference', 'caissier', 'date_cloture', 'total_ventes_net', 'ecart_total', 'statut_conformite')
    list_filter = ('statut_conformite', 'date_cloture')
    search_fields = ('reference', 'caissier__username', 'commentaire')
    readonly_fields = ('date_creation',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('titre', 'type_notification', 'niveau', 'destinataire', 'est_lue', 'est_archivee', 'date_creation')
    list_filter = ('type_notification', 'niveau', 'est_lue', 'est_archivee', 'date_creation')
    search_fields = ('titre', 'message', 'cle_unicite', 'destinataire__username')
    readonly_fields = ('date_creation', 'date_lecture')


