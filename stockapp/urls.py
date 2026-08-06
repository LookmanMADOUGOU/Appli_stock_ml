from django.urls import path
from . import views

app_name = 'stockapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    
    # Produits
    path('produits/', views.produits, name='produits-list'),
    # CRUD via admin only: produit add/modify/delete removed from public routes
    
    # Catégories
    path('categories/', views.categories, name='categories-list'),
    # Category modify/delete via admin only
    
    # Ventes
    path('ventes/', views.ventes, name='ventes-list'),
    # Vente deletion via admin only
    
    # Approvisionnements
    path('approvisionnements/', views.approvisionnements, name='approvisionnements-list'),
    # Approvisionnement deletion via admin only
    
    # Export
    path('export/pdf/', views.export_report_pdf, name='export-report-pdf'),
]
