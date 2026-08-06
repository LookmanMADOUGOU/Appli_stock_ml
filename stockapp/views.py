import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, F, Count
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import timedelta
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente
from .forms import ProduitForm, CategorieForm, VenteForm, ApprovisionnementForm
from .services.alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire


@login_required
def dashboard(request):
    produits_count = Produit.objects.count()
    stock_total = Produit.objects.aggregate(total=Sum('stock_actuel'))['total'] or 0
    produits_en_rupture = Produit.objects.filter(stock_actuel__lte=F('seuil_alerte'))
    produits_en_rupture_count = produits_en_rupture.count()
    rupture_rate = round((produits_en_rupture_count / produits_count) * 100, 1) if produits_count else 0

    alertes_actives = AlerteRupture.objects.filter(est_resolue=False).select_related('produit')[:10]
    alertes_actives_count = alertes_actives.count()

    ventes_recentes = Vente.objects.select_related('produit').order_by('-date_vente')[:10]
    ventes_30j = Vente.objects.filter(date_vente__gte=timezone.now() - timedelta(days=30)).aggregate(total=Sum('quantite'))['total'] or 0
    top_consumed = (
        Vente.objects
        .values('produit__nom')
        .annotate(total=Sum('quantite'))
        .order_by('-total')[:5]
    )

    produits_critique = Produit.objects.filter(stock_actuel__lte=F('seuil_alerte')).order_by('stock_actuel')[:10]
    produits_list = Produit.objects.select_related('categorie').order_by('nom')[:8]
    categories_count = Categorie.objects.count()
    top_categories = (
        Categorie.objects
        .annotate(total_produits=Count('produits'))
        .order_by('-total_produits')[:5]
    )
    approvisionnements_count = Approvisionnement.objects.count()
    approvisionnements_recents = Approvisionnement.objects.select_related('produit').order_by('-date_approvisionnement')[:6]
    avg_products_per_category = round(produits_count / categories_count, 1) if categories_count else 0

    # Prévisions simples
    previsions = []
    for p in Produit.objects.all()[:50]:
        previsions.append({
            'id': p.id,
            'nom': p.nom,
            'prediction_ml': p.prediction_ml,
            'prediction_rupture': p.prediction_rupture,
        })

    context = {
        'produits_count': produits_count,
        'stock_total': stock_total,
        'produits_en_rupture_count': produits_en_rupture_count,
        'rupture_rate': rupture_rate,
        'alertes_actives_count': alertes_actives_count,
        'alertes_actives': alertes_actives,
        'ventes_recentes': ventes_recentes,
        'top_consumed': top_consumed,
        'previsions': previsions,
        'produits_critique': produits_critique,
        'produits_list': produits_list,
        'categories_count': categories_count,
        'top_categories': top_categories,
        'avg_products_per_category': avg_products_per_category,
        'approvisionnements_count': approvisionnements_count,
        'approvisionnements_recents': approvisionnements_recents,
        'ventes_30j': ventes_30j,
        'alert_rate': round((alertes_actives_count / produits_count) * 100, 1) if produits_count else 0,
    }

    return render(request, 'stockapp/dashboard.html', context)


# ==================== PRODUITS ====================
# ==================== PRODUITS ====================

@login_required
def produits(request):
    # Les opérations d'ajout / modification / suppression via le dashboard
    # sont désactivées sur la branche `main`. Utilisez l'administration Django.
    if request.method == 'POST':
        messages.warning(request, "Les opérations d'ajout/modification/suppression sont disponibles uniquement via l'administration Django.")
        return redirect('stockapp:produits-list')
    form = None

    produits_qs = Produit.objects.select_related('categorie').order_by('nom')
    total_produits = produits_qs.count()
    produits_en_rupture = produits_qs.filter(stock_actuel__lte=F('seuil_alerte')).count()
    return render(request, 'stockapp/produits.html', {
        'produits': produits_qs,
        'total_produits': total_produits,
        'produits_en_rupture': produits_en_rupture,
        'form': form,
    })


# ==================== CATÉGORIES ====================

@login_required
def categories(request):
    # Operations via dashboard disabled; use Django admin.
    if request.method == 'POST':
        messages.warning(request, "Les opérations d'ajout/modification/suppression sont disponibles uniquement via l'administration Django.")
        return redirect('stockapp:categories-list')
    form = None

    categories_qs = Categorie.objects.annotate(nb_produits=Count('produits')).order_by('-nb_produits', 'nom')
    total_categories = categories_qs.count()
    total_produits = Produit.objects.count()
    return render(request, 'stockapp/categories.html', {
        'categories': categories_qs,
        'total_categories': total_categories,
        'total_produits': total_produits,
        'form': form,
    })


# ==================== VENTES ====================

@login_required
def ventes(request):
    if request.method == 'POST':
        messages.warning(request, "Les enregistrements de ventes via le dashboard sont désactivés. Utilisez l'administration Django.")
        return redirect('stockapp:ventes-list')
    form = None

    ventes_qs = Vente.objects.select_related('produit').order_by('-date_vente')[:50]
    total_ventes = Vente.objects.aggregate(total=Sum('quantite'))['total'] or 0
    return render(request, 'stockapp/ventes.html', {
        'ventes': ventes_qs,
        'total_ventes': total_ventes,
        'form': form,
    })


# ==================== VENTES ====================

@login_required
def ventes(request):
    if request.method == 'POST':
        messages.warning(request, "Les enregistrements de ventes via le dashboard sont désactivés. Utilisez l'administration Django.")
        return redirect('stockapp:ventes-list')
    form = None

    ventes_qs = Vente.objects.select_related('produit').order_by('-date_vente')[:50]
    total_ventes = Vente.objects.aggregate(total=Sum('quantite'))['total'] or 0
    return render(request, 'stockapp/ventes.html', {
        'ventes': ventes_qs,
        'total_ventes': total_ventes,
        'form': form,
    })


# ==================== APPROVISIONNEMENTS ====================

@login_required
def approvisionnements(request):
    if request.method == 'POST':
        messages.warning(request, "Les approvisionnements via le dashboard sont désactivés. Utilisez l'administration Django.")
        return redirect('stockapp:approvisionnements-list')
    form = None

    approvisionnements_qs = Approvisionnement.objects.select_related('produit').order_by('-date_approvisionnement')[:50]
    total_approvisionnements = Approvisionnement.objects.aggregate(total=Sum('quantite'))['total'] or 0
    return render(request, 'stockapp/approvisionnements.html', {
        'approvisionnements': approvisionnements_qs,
        'total_approvisionnements': total_approvisionnements,
        'form': form,
    })


# ==================== INFOS ET EXPORT ====================

def home(request):
    return render(request, 'stockapp/home.html')


def info(request):
    return render(request, 'stockapp/info.html')


@login_required
def export_report_pdf(request):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    produits_en_rupture = Produit.objects.filter(stock_actuel__lte=F('seuil_alerte'))

    story.append(Paragraph('Rapport de stock', styles['Title']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Produits enregistrés : {Produit.objects.count()}", styles['BodyText']))
    story.append(Paragraph(f"Stock total : {Produit.objects.aggregate(total=Sum('stock_actuel'))['total'] or 0}", styles['BodyText']))
    story.append(Paragraph(f"Produits en rupture : {produits_en_rupture.count()}", styles['BodyText']))
    story.append(Spacer(1, 12))

    rows = [['Produit', 'Stock', 'Seuil', 'État']]
    for produit in Produit.objects.order_by('nom')[:20]:
        rows.append([produit.nom, str(produit.stock_actuel), str(produit.seuil_alerte), 'Rupture' if produit.rupture else 'OK'])

    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.beige]),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph('Produits en rupture et seuils critiques', styles['Heading2']))

    rupture_rows = [['Produit', 'Stock courant', 'Seuil d’alerte']]
    for produit in produits_en_rupture.order_by('stock_actuel')[:20]:
        rupture_rows.append([
            produit.nom,
            str(produit.stock_actuel),
            str(produit.seuil_alerte),
        ])

    rupture_table = Table(rupture_rows, repeatRows=1)
    rupture_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F766E')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.aliceblue]),
    ]))
    story.append(rupture_table)

    top_products = (
        Vente.objects
        .values('produit__nom')
        .annotate(total=Sum('quantite'))
        .order_by('-total')[:10]
    )

    story.append(Spacer(1, 20))
    story.append(Paragraph('Top 10 des produits les plus vendus', styles['Heading2']))

    top_rows = [['Produit', 'Quantité vendue']]
    for item in top_products:
        top_rows.append([item['produit__nom'], str(item['total'])])

    top_table = Table(top_rows, repeatRows=1)
    top_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#9447FF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lavender]),
    ]))
    story.append(top_table)
    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="rapport_stock.pdf"'
    return response
