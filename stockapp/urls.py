from django.urls import path
from . import views

app_name = 'stockapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Produits
    path('produits/', views.produits, name='produits-list'),
    # Produits
    path('produits/', views.produits, name='produits-list'),
    
    # Catégories
    path('categories/', views.categories, name='categories-list'),
    
    # Ventes
    path('ventes/', views.ventes, name='ventes-list'),
    path('ventes/<int:pk>/recu/', views.telecharger_recu_pdf, name='vente-recu-pdf'),
    
    # Approvisionnements & Bon de commande
    path('approvisionnements/', views.approvisionnements, name='approvisionnements-list'),
    path('approvisionnements/bon-de-commande/', views.bon_de_commande, name='bon-de-commande'),
    path('approvisionnements/bon-de-commande/pdf/', views.bon_de_commande_pdf, name='bon-de-commande-pdf'),
    path('approvisionnements/bon-de-commande/valider/', views.bon_de_commande_valider, name='bon-de-commande-valider'),

    # Notifications
    path('notifications/envoyer-resume/', views.envoyer_resume_journalier_view, name='envoyer-resume-journalier'),
    
    # PWA Routes
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('manifest.json', views.pwa_manifest, name='manifest'),
    
    # Export
    path('export/pdf/', views.export_report_pdf, name='export-report-pdf'),
]
