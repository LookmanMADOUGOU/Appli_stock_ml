import io
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db.models import Sum, F, Count
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import timedelta
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente
from .forms import ProduitForm, CategorieForm, VenteForm, ApprovisionnementForm
from .services.alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire, generer_et_envoyer_resume_journalier
from .services.purchase_order_service import generate_purchase_order_data, generate_purchase_order_pdf, convert_order_data_to_approvisionnements


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

@login_required
def produits(request):
    if request.method != 'GET':
        return redirect('/admin/')

    produits_qs = Produit.objects.select_related('categorie').order_by('nom')
    total_produits = produits_qs.count()
    produits_en_rupture = produits_qs.filter(stock_actuel__lte=F('seuil_alerte')).count()
    return render(request, 'stockapp/produits.html', {
        'produits': produits_qs,
        'total_produits': total_produits,
        'produits_en_rupture': produits_en_rupture,
    })


@login_required
def produit_ajouter(request):
    if request.method == 'POST':
        form = ProduitForm(request.POST)
        if form.is_valid():
            produit = form.save()
            if produit.rupture:
                creer_alerte_si_necessaire(produit)
            else:
                resoudre_alerte_si_necessaire(produit)
            messages.success(request, f"Produit '{produit.nom}' créé avec succès.")
            return redirect('stockapp:produits-list')
    else:
        form = ProduitForm()
    return render(request, 'stockapp/produit_form.html', {'form': form, 'title': 'Ajouter un produit'})


@login_required
def produit_modifier(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    if request.method == 'POST':
        form = ProduitForm(request.POST, instance=produit)
        if form.is_valid():
            produit = form.save()
            if produit.rupture:
                creer_alerte_si_necessaire(produit)
            else:
                resoudre_alerte_si_necessaire(produit)
            messages.success(request, f"Produit '{produit.nom}' modifié avec succès.")
            return redirect('stockapp:produits-list')
    else:
        form = ProduitForm(instance=produit)
    return render(request, 'stockapp/produit_form.html', {'form': form, 'produit': produit, 'title': 'Modifier le produit'})


@login_required
def produit_supprimer(request, pk):
    if request.method == 'POST':
        produit = get_object_or_404(Produit, pk=pk)
        nom = produit.nom
        produit.delete()
        messages.success(request, f"Produit '{nom}' supprimé.")
    return redirect('stockapp:produits-list')


# ==================== CATÉGORIES ====================

@login_required
def categories(request):
    if request.method != 'GET':
        return redirect('/admin/')

    categories_qs = Categorie.objects.annotate(nb_produits=Count('produits')).order_by('-nb_produits', 'nom')
    total_categories = categories_qs.count()
    total_produits = Produit.objects.count()
    return render(request, 'stockapp/categories.html', {
        'categories': categories_qs,
        'total_categories': total_categories,
        'total_produits': total_produits,
    })


@login_required
def categorie_modifier(request, pk):
    categorie = get_object_or_404(Categorie, pk=pk)
    if request.method == 'POST':
        form = CategorieForm(request.POST, instance=categorie)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Catégorie '{cat.nom}' modifiée avec succès.")
            return redirect('stockapp:categories-list')
    else:
        form = CategorieForm(instance=categorie)
    return render(request, 'stockapp/categorie_form.html', {'form': form, 'categorie': categorie, 'title': 'Modifier la catégorie'})


@login_required
def categorie_supprimer(request, pk):
    if request.method == 'POST':
        categorie = get_object_or_404(Categorie, pk=pk)
        nom = categorie.nom
        categorie.delete()
        messages.success(request, f"Catégorie '{nom}' supprimée.")
    return redirect('stockapp:categories-list')


# ==================== VENTES ====================

@login_required
def ventes(request):
    # --- Gestion de la période ---
    periode = request.GET.get('periode', 'jour')
    date_str = request.GET.get('date')
    today = timezone.now().date()

    if date_str:
        try:
            selected_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    # Calcul de la plage de dates selon la période
    if periode == 'semaine':
        debut_periode = selected_date - timedelta(days=selected_date.weekday())
        fin_periode = debut_periode + timedelta(days=6)
        label_periode = f"Semaine du {debut_periode.strftime('%d/%m')} au {fin_periode.strftime('%d/%m/%Y')}"
    elif periode == 'mois':
        debut_periode = selected_date.replace(day=1)
        if selected_date.month == 12:
            fin_periode = selected_date.replace(year=selected_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            fin_periode = selected_date.replace(month=selected_date.month + 1, day=1) - timedelta(days=1)
        label_periode = f"Mois de {selected_date.strftime('%B %Y')}"
    elif periode == 'annee':
        debut_periode = selected_date.replace(month=1, day=1)
        fin_periode = selected_date.replace(month=12, day=31)
        label_periode = f"Année {selected_date.year}"
    else:  # jour (default)
        debut_periode = selected_date
        fin_periode = selected_date
        label_periode = f"Journée du {selected_date.strftime('%d/%m/%Y')}"

    if request.method != 'GET':
        return redirect('/admin/')

    # Ventes de la période sélectionnée
    ventes_periode = Vente.objects.filter(
        date_vente__date__gte=debut_periode,
        date_vente__date__lte=fin_periode
    ).select_related('produit').order_by('date_vente')

    # Registre du jour (toujours la date sélectionnée)
    ventes_jour = Vente.objects.filter(date_vente__date=selected_date).select_related('produit').order_by('date_vente')

    # Agrégation du journal quotidien par produit
    journal_dict = {}
    chiffre_affaires_jour = 0
    benefice_net_jour = 0
    total_articles_jour = 0

    for v in ventes_jour:
        p_id = v.produit.id
        if p_id not in journal_dict:
            journal_dict[p_id] = {
                'produit_id': p_id,
                'produit_nom': v.produit.nom,
                'quantites_list': [v.quantite],
                'total_quantite': v.quantite,
                'prix_unitaire': v.prix_unitaire,
                'montant_total': v.prix_total,
                'benefice': v.benefice_total,
            }
        else:
            journal_dict[p_id]['quantites_list'].append(v.quantite)
            journal_dict[p_id]['total_quantite'] += v.quantite
            journal_dict[p_id]['montant_total'] += v.prix_total
            journal_dict[p_id]['benefice'] += v.benefice_total

        chiffre_affaires_jour += v.prix_total
        benefice_net_jour += v.benefice_total
        total_articles_jour += v.quantite

    journal_ventes = []
    for item in journal_dict.values():
        item['decomposition'] = ' + '.join(str(q) for q in item['quantites_list'])
        journal_ventes.append(item)

    journal_ventes.sort(key=lambda x: x['montant_total'], reverse=True)

    # Statistiques de la période (Semaine/Mois/Année)
    chiffre_affaires_periode = sum(v.prix_total for v in ventes_periode)
    benefice_net_periode = sum(v.benefice_total for v in ventes_periode)
    total_articles_periode = sum(v.quantite for v in ventes_periode)

    ventes_recentes = Vente.objects.select_related('produit').order_by('-date_vente')[:50]

    return render(request, 'stockapp/ventes.html', {
        'ventes': ventes_recentes,
        'journal_ventes': journal_ventes,
        'selected_date': selected_date.strftime('%Y-%m-%d'),
        'periode': periode,
        'label_periode': label_periode,
        'chiffre_affaires_jour': chiffre_affaires_jour,
        'benefice_net_jour': benefice_net_jour,
        'total_articles_jour': total_articles_jour,
        'nb_transactions_jour': ventes_jour.count(),
        'chiffre_affaires_periode': chiffre_affaires_periode,
        'benefice_net_periode': benefice_net_periode,
        'total_articles_periode': total_articles_periode,
        'nb_transactions_periode': ventes_periode.count(),
        'periode_choices': [
            ('jour', 'Jour'),
            ('semaine', 'Semaine'),
            ('mois', 'Mois'),
            ('annee', 'Année'),
        ],
    })


@login_required
def vente_supprimer(request, pk):
    if request.method == 'POST':
        vente = get_object_or_404(Vente, pk=pk)
        nom = vente.produit.nom
        vente.delete()  # Signal pre_delete triggers restore_sale automatically
        messages.success(request, f"Vente de '{nom}' supprimée. Le stock a été réapprovisionné.")
    return redirect('stockapp:ventes-list')


@login_required
def telecharger_recu_pdf(request, pk):
    vente = get_object_or_404(Vente, pk=pk)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(220, 400), leftMargin=10, rightMargin=10, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph("LOOK-TECH", styles['Title']))
    story.append(Paragraph("Gestion Stock IA", styles['Normal']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Reçu N° #{vente.pk:06d}", styles['Heading2']))
    story.append(Paragraph(f"Date : {vente.date_vente.strftime('%d/%m/%Y à %H:%M')}", styles['Normal']))
    story.append(Spacer(1, 10))

    # Ligne séparatrice
    story.append(Table([['-' * 35]], colWidths=[200]))
    story.append(Spacer(1, 6))

    # Détail de la vente
    data = [
        ['Produit', vente.produit.nom],
        ['Référence', vente.produit.reference],
        ['Quantité', str(vente.quantite)],
        ['Prix unitaire', f"{vente.prix_unitaire} FCFA/€"],
        ['TOTAL', f"{vente.prix_total} FCFA/€"],
    ]
    if vente.prix_achat > 0:
        data.append(['Bénéfice Net', f"{vente.benefice_total} FCFA/€"])

    tbl = Table(data, colWidths=[90, 110])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 4), (-1, 4), 11),
        ('TEXTCOLOR', (0, 4), (-1, 4), colors.HexColor('#0891b2')),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Merci pour votre achat !", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="recu_{vente.pk:06d}.pdf"'
    return response


# ==================== APPROVISIONNEMENTS ====================

@login_required
def approvisionnements(request):
    if request.method != 'GET':
        return redirect('/admin/')

    approvisionnements_qs = Approvisionnement.objects.select_related('produit').order_by('-date_approvisionnement')[:50]
    total_approvisionnements = Approvisionnement.objects.aggregate(total=Sum('quantite'))['total'] or 0
    return render(request, 'stockapp/approvisionnements.html', {
        'approvisionnements': approvisionnements_qs,
        'total_approvisionnements': total_approvisionnements,
    })


@login_required
def approvisionnement_supprimer(request, pk):
    if request.method == 'POST':
        appro = get_object_or_404(Approvisionnement, pk=pk)
        nom = appro.produit.nom
        appro.delete() # Signal pre_delete triggers revert_approvisionnement automatically
        messages.success(request, f"Approvisionnement de '{nom}' annulé. Le stock a été déduit.")
    return redirect('stockapp:approvisionnements-list')


# ==================== BON DE COMMANDE IA & NOTIFICATIONS ====================

@login_required
def bon_de_commande(request):
    order_data = generate_purchase_order_data()
    return render(request, 'stockapp/bon_de_commande.html', {
        'order_data': order_data,
    })


@login_required
def bon_de_commande_pdf(request):
    order_data = generate_purchase_order_data()
    pdf_bytes = generate_purchase_order_pdf(order_data)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Bon_de_Commande_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def bon_de_commande_valider(request):
    if request.method == 'POST':
        order_data = generate_purchase_order_data()
        count = convert_order_data_to_approvisionnements(order_data)
        messages.success(request, f"✅ {count} approvisionnement(s) créé(s) avec succès depuis le bon de commande IA !")
    return redirect('stockapp:approvisionnements-list')


@login_required
def envoyer_resume_journalier_view(request):
    if request.method == 'POST':
        res = generer_et_envoyer_resume_journalier()
        messages.success(
            request,
            f"📲 Résumé envoyé à l'administration ! (CA: {res['chiffre_affaires']} | Bénéfice: {res['benefice_net']} FCFA/€)"
        )
    return redirect(request.META.get('HTTP_REFERER', 'stockapp:dashboard'))


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


# ==================== PWA VIEWS ====================

def service_worker(request):
    import os
    from django.conf import settings
    sw_path = os.path.join(settings.BASE_DIR, 'stockapp', 'static', 'service-worker.js')
    if os.path.exists(sw_path):
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = ""
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


def pwa_manifest(request):
    import os
    from django.conf import settings
    manifest_path = os.path.join(settings.BASE_DIR, 'stockapp', 'static', 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = "{}"
    return HttpResponse(content, content_type='application/manifest+json')

