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
    
    # Approvisionnements
    path('approvisionnements/', views.approvisionnements, name='approvisionnements-list'),
    path('approvisionnements/<int:pk>/supprimer/', views.approvisionnement_supprimer, name='approvisionnement-supprimer'),
    
    # Export
    path('export/pdf/', views.export_report_pdf, name='export-report-pdf'),
]
