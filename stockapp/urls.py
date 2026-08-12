from django.urls import path
from . import views

app_name = 'stockapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Produits
    path('produits/', views.produits, name='produits-list'),
    path('produits/ajouter/', views.produit_ajouter, name='produit-ajouter'),
    path('produits/<int:pk>/modifier/', views.produit_modifier, name='produit-modifier'),
    path('produits/<int:pk>/supprimer/', views.produit_supprimer, name='produit-supprimer'),

    # Catégories
    path('categories/', views.categories, name='categories-list'),
    path('categories/<int:pk>/modifier/', views.categorie_modifier, name='categorie-modifier'),
    path('categories/<int:pk>/supprimer/', views.categorie_supprimer, name='categorie-supprimer'),

    # Ventes
    path('ventes/', views.ventes, name='ventes-list'),
    path('ventes/<int:pk>/supprimer/', views.vente_supprimer, name='vente-supprimer'),
    path('ventes/<int:pk>/recu/', views.telecharger_recu_pdf, name='vente-recu-pdf'),

    # Approvisionnements & Bon de commande IA
    path('approvisionnements/', views.approvisionnements, name='approvisionnements-list'),
    path('approvisionnements/<int:pk>/supprimer/', views.approvisionnement_supprimer, name='approvisionnement-supprimer'),
    path('approvisionnements/bon-de-commande/', views.bon_de_commande, name='bon-de-commande'),
    path('approvisionnements/bon-de-commande/pdf/', views.bon_de_commande_pdf, name='bon-de-commande-pdf'),
    path('approvisionnements/bon-de-commande/valider/', views.bon_de_commande_valider, name='bon-de-commande-valider'),

    # Notifications & Résumé
    path('notifications/envoyer-resume/', views.envoyer_resume_journalier_view, name='envoyer-resume-journalier'),

    # PWA Routes
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('manifest.json', views.pwa_manifest, name='manifest'),

    # Export
    path('export/pdf/', views.export_report_pdf, name='export-report-pdf'),
]
