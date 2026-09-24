import csv

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, F
from django.shortcuts import get_object_or_404

from stockapp.permissions import IsAdminUserRole, IsManagerUserRole, IsCashierUserRole, IsStockManagerUserRole


from stockapp.models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente, MouvementStock
from .serializers import (
    AlerteRuptureSerializer,
    ApprovisionnementSerializer,
    ProduitSerializer,
    VenteSerializer,
    MouvementStockSerializer,
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sales_evolution(request):
    """Retourne les ventes agrégées par jour pour les X derniers jours."""
    days = int(request.GET.get('days', 30))
    produit_id = request.GET.get('produit')
    since = timezone.now() - timedelta(days=days)

    qs = Vente.objects.filter(date_vente__gte=since)
    if produit_id:
        qs = qs.filter(produit_id=produit_id)

    data = (
        qs
        .values('date_vente__date')
        .annotate(total=Sum('quantite'))
        .order_by('date_vente__date')
    )

    result = [{
        'date': item['date_vente__date'].isoformat(),
        'quantite': item['total']
    } for item in data]

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sales_evolution_product(request, product_id):
    """Série temporelle des ventes pour un produit donné."""
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)

    qs = (
        Vente.objects.filter(produit_id=product_id, date_vente__gte=since)
        .values('date_vente__date')
        .annotate(total=Sum('quantite'))
        .order_by('date_vente__date')
    )

    result = [{
        'date': item['date_vente__date'].isoformat(),
        'quantite': item['total']
    } for item in qs]

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def consumption_by_product(request):
    """Retourne la consommation (ventes) par produit sur les X derniers jours."""
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)

    qs = (
        Vente.objects.filter(date_vente__gte=since)
        .values('produit__id', 'produit__nom')
        .annotate(total=Sum('quantite'))
        .order_by('-total')
    )

    limit = request.GET.get('limit')
    if limit:
        try:
            limit = int(limit)
            qs = qs[:limit]
        except ValueError:
            pass

    result = [{
        'produit_id': item['produit__id'],
        'produit_nom': item.get('produit__nom') or Produit.objects.filter(pk=item['produit__id']).values_list('nom', flat=True).first(),
        'quantite': item['total']
    } for item in qs]

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stock_remaining(request):
    """Retourne l'état des stocks pour tous les produits."""
    produits = Produit.objects.all().values('id', 'nom', 'stock_actuel', 'seuil_alerte')
    result = []
    for p in produits:
        result.append({
            'produit_id': p['id'],
            'produit_nom': p['nom'],
            'stock_actuel': p['stock_actuel'],
            'seuil_alerte': p['seuil_alerte'],
            'en_rupture': p['stock_actuel'] <= p['seuil_alerte']
        })
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_summary(request):
    total_products = Produit.objects.count()
    total_stock = Produit.objects.aggregate(total=Sum('stock_actuel'))['total'] or 0
    products_in_rupture = Produit.objects.filter(stock_actuel__lte=F('seuil_alerte')).count()
    active_alerts = AlerteRupture.objects.filter(est_resolue=False).count()
    top_consumed = (
        Vente.objects
        .values('produit__id', 'produit__nom')
        .annotate(total=Sum('quantite'))
        .order_by('-total')[:5]
    )

    return Response({
        'total_products': total_products,
        'total_stock': total_stock,
        'products_in_rupture': products_in_rupture,
        'active_alerts': active_alerts,
        'top_consumed': [
            {
                'produit_id': item['produit__id'],
                'produit_nom': item['produit__nom'],
                'quantite': item['total'],
            }
            for item in top_consumed
        ],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_category(request, category_id):
    category = get_object_or_404(Categorie, pk=category_id)
    produits = Produit.objects.filter(categorie=category)
    total_products = produits.count()
    total_stock = produits.aggregate(total=Sum('stock_actuel'))['total'] or 0
    products_in_rupture = produits.filter(stock_actuel__lte=F('seuil_alerte')).count()
    recent_consumption = (
        Vente.objects.filter(produit__categorie=category)
        .values('produit__id', 'produit__nom')
        .annotate(total=Sum('quantite'))
        .order_by('-total')[:5]
    )

    return Response({
        'category_id': category.id,
        'category_nom': category.nom,
        'total_products': total_products,
        'total_stock': total_stock,
        'products_in_rupture': products_in_rupture,
        'top_consumed': [
            {
                'produit_id': item['produit__id'],
                'produit_nom': item['produit__nom'],
                'quantite': item['total'],
            }
            for item in recent_consumption
        ],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def stats_trend(request):
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    sales = (
        Vente.objects.filter(date_vente__gte=since)
        .values('date_vente__date')
        .annotate(total=Sum('quantite'))
        .order_by('date_vente__date')
    )
    stock_levels = (
        Produit.objects
        .values('id', 'nom', 'stock_actuel')
        .order_by('nom')
    )

    return Response({
        'period_days': days,
        'sales': [
            {'date': item['date_vente__date'].isoformat(), 'quantite': item['total']}
            for item in sales
        ],
        'stock_levels': [
            {'produit_id': item['id'], 'produit_nom': item['nom'], 'stock_actuel': item['stock_actuel']}
            for item in stock_levels
        ],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def previsions(request):
    produit_id = request.GET.get('produit')
    qs = Produit.objects.all()
    if produit_id:
        qs = qs.filter(pk=produit_id)

    resultat = []
    for produit in qs:
        resultat.append({
            'produit_id': produit.id,
            'produit_nom': produit.nom,
            'stock_actuel': produit.stock_actuel,
            'seuil_alerte': produit.seuil_alerte,
            'rupture': produit.rupture,
            'prediction_ml': produit.prediction_ml,
            'prediction_rupture': produit.prediction_rupture,
        })

    return Response(resultat)


class DynamicPageNumberPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProduitFilter(django_filters.FilterSet):
    rupture = django_filters.BooleanFilter(method='filter_rupture')

    class Meta:
        model = Produit
        fields = ['categorie', 'rupture']

    def filter_rupture(self, queryset, name, value):
        if value:
            return queryset.filter(stock_actuel__lte=F('seuil_alerte'))
        return queryset.filter(stock_actuel__gt=F('seuil_alerte'))


class ProduitViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Produit.objects.all().select_related('categorie')
    serializer_class = ProduitSerializer
    pagination_class = DynamicPageNumberPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    filterset_class = ProduitFilter
    search_fields = ['nom', 'reference']

    @action(detail=False, methods=['get'])
    def export(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="produits.csv"'

        writer = csv.writer(response)
        writer.writerow(['nom', 'reference', 'categorie', 'stock_actuel', 'seuil_alerte', 'rupture'])

        for produit in self.get_queryset().select_related('categorie'):
            writer.writerow([
                produit.nom,
                produit.reference,
                produit.categorie.nom if produit.categorie else '',
                produit.stock_actuel,
                produit.seuil_alerte,
                'oui' if produit.rupture else 'non',
            ])

        return response

    @action(detail=False, methods=['post'], url_path='import', permission_classes=[IsAuthenticated, IsAdminUser])
    def import_csv(self, request):
        csv_file = request.FILES.get('file') or request.data.get('file')
        if not csv_file:
            return Response({'detail': 'Fichier CSV manquant.'}, status=400)

        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(decoded.splitlines())
        imported = 0
        updated = 0
        errors = []

        for row_index, row in enumerate(reader, start=1):
            reference = (row.get('reference') or row.get('ref') or '').strip()
            nom = (row.get('nom') or row.get('name') or '').strip()
            if not reference or not nom:
                errors.append(f'Ligne {row_index} : reference ou nom manquant.')
                continue

            stock_actuel = row.get('stock_actuel') or row.get('stock') or '0'
            seuil_alerte = row.get('seuil_alerte') or row.get('seuil') or '10'
            categorie_nom = (row.get('categorie') or row.get('category') or '').strip()

            try:
                stock_actuel = int(stock_actuel)
            except ValueError:
                stock_actuel = 0

            try:
                seuil_alerte = int(seuil_alerte)
            except ValueError:
                seuil_alerte = 10

            categorie = None
            if categorie_nom:
                categorie, _ = Categorie.objects.get_or_create(nom=categorie_nom)

            produit, created = Produit.objects.update_or_create(
                reference=reference,
                defaults={
                    'nom': nom,
                    'stock_actuel': stock_actuel,
                    'seuil_alerte': seuil_alerte,
                    'categorie': categorie,
                }
            )

            # Vérifier les alertes après création/mise à jour du produit
            from stockapp.services.alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire
            if produit.rupture:
                creer_alerte_si_necessaire(produit)
            else:
                resoudre_alerte_si_necessaire(produit)

            if created:
                imported += 1
            else:
                updated += 1

        return Response({
            'imported': imported,
            'updated': updated,
            'errors': errors,
        })

    @action(detail=True, methods=['get'])
    def prediction(self, request, pk=None):
        produit = self.get_object()
        return Response({
            'prediction_ml': produit.prediction_ml,
            'prediction_rupture': produit.prediction_rupture,
        })

    @action(detail=True, methods=['get'])
    def forecast(self, request, pk=None):
        produit = self.get_object()
        days = int(request.GET.get('days', 7))
        from stockapp.services.prediction_service import get_demand_forecast

        forecast = get_demand_forecast(produit, days_ahead=days)
        return Response({
            'prediction_ml': produit.prediction_ml,
            'prediction_rupture': produit.prediction_rupture,
            'forecast': forecast,
        })

    @action(detail=True, methods=['get'])
    def trend(self, request, pk=None):
        produit = self.get_object()
        days = int(request.GET.get('days', 30))
        from stockapp.services.prediction_service import get_sales_trend

        result = get_sales_trend(produit, days=days)
        return Response(result)

    @action(detail=False, methods=['get'])
    def comparison(self, request):
        ids = request.GET.getlist('ids', [])
        if not ids:
            return Response([])

        produits = Produit.objects.filter(pk__in=ids)
        from stockapp.services.prediction_service import compare_products_forecast

        result = compare_products_forecast(list(produits))
        return Response(result)


class VenteViewSet(viewsets.ModelViewSet):
    queryset = Vente.objects.all().order_by('-date_vente')
    serializer_class = VenteSerializer

    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Seuls les administrateurs peuvent créer des ventes.'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Seuls les administrateurs peuvent modifier des ventes.'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Seuls les administrateurs peuvent modifier des ventes.'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({'detail': 'Seuls les administrateurs peuvent supprimer des ventes.'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


class ApprovisionnementViewSet(viewsets.ModelViewSet):
    queryset = Approvisionnement.objects.all().order_by('-date_approvisionnement')
    serializer_class = ApprovisionnementSerializer

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='import', permission_classes=[IsAuthenticated, IsAdminUser])
    def import_csv(self, request):
        csv_file = request.FILES.get('file') or request.data.get('file')
        if not csv_file:
            return Response({'detail': 'Fichier CSV manquant.'}, status=400)

        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(decoded.splitlines())
        imported = 0
        errors = []

        for row_index, row in enumerate(reader, start=1):
            produit_ref = (row.get('reference') or row.get('produit_reference') or row.get('product_reference') or '').strip()
            quantite = row.get('quantite') or row.get('quantity') or '0'
            fournisseur = (row.get('fournisseur') or row.get('supplier') or 'Inconnu').strip()

            if not produit_ref:
                errors.append(f'Ligne {row_index} : référence de produit manquante.')
                continue

            try:
                quantite = int(quantite)
            except ValueError:
                errors.append(f'Ligne {row_index} : quantite invalide.')
                continue

            produit = Produit.objects.filter(reference=produit_ref).first()
            if not produit:
                errors.append(f'Ligne {row_index} : produit introuvable pour la référence {produit_ref}.')
                continue

            Approvisionnement.objects.create(
                produit=produit,
                quantite=quantite,
                fournisseur=fournisseur,
            )

            imported += 1

        return Response({
            'imported': imported,
            'errors': errors,
        })


class AlerteRuptureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AlerteRupture.objects.select_related('produit').order_by('-date_creation')
    serializer_class = AlerteRuptureSerializer


class MouvementStockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MouvementStock.objects.select_related('produit', 'utilisateur').order_by('-date_mouvement')
    serializer_class = MouvementStockSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['produit', 'type_mouvement']
    search_fields = ['produit__nom', 'reference', 'commentaire']

