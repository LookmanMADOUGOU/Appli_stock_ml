from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AlerteRuptureViewSet,
    ApprovisionnementViewSet,
    ProduitViewSet,
    VenteViewSet,
    MouvementStockViewSet,
    consumption_by_product,
    previsions,
    sales_evolution,
    sales_evolution_product,
    stats_category,
    stats_summary,
    stats_trend,
    stock_remaining,
)

router = DefaultRouter()
router.register(r'produits', ProduitViewSet, basename='produit')
router.register(r'ventes', VenteViewSet, basename='vente')
router.register(r'approvisionnements', ApprovisionnementViewSet, basename='approvisionnement')
router.register(r'alertes', AlerteRuptureViewSet, basename='alerte')
router.register(r'mouvements', MouvementStockViewSet, basename='mouvement-stock')

urlpatterns = [
    path('', include(router.urls)),
    path('previsions/', previsions, name='previsions'),
    path('stats/summary/', stats_summary, name='stats-summary'),
    path('stats/category/<int:category_id>/', stats_category, name='stats-category'),
    path('stats/trend/', stats_trend, name='stats-trend'),
    path('charts/sales/', sales_evolution, name='charts-sales'),
    path('charts/sales/product/<int:product_id>/', sales_evolution_product, name='charts-sales-product'),
    path('charts/consumption/', consumption_by_product, name='charts-consumption'),
    path('charts/stock/', stock_remaining, name='charts-stock'),
    path('exports/products/', ProduitViewSet.as_view({'get': 'export'}), name='exports-products'),
]
