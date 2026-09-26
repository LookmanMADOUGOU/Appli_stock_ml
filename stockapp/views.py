import csv
import io
import json
import os
from datetime import timedelta
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Count
from django.http import HttpResponse, JsonResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.db import models, transaction

from django.contrib.auth.models import User, Group

from .forms import (
    ProduitForm, CategorieForm, VenteForm, ApprovisionnementForm,
    AjustementStockForm, ClientForm, FournisseurForm, ReglerDetteFournisseurForm, DepenseForm,
    ClotureCaisseForm, UtilisateurCreateForm, UtilisateurUpdateForm, UtilisateurPasswordResetForm
)
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente, MouvementStock, Client, Fournisseur, Depense, JournalAudit, ClotureCaisse, Notification
from .selectors import (
    get_dashboard_metrics, get_decision_support_metrics, get_advanced_analytics_metrics,
    get_financial_metrics, get_audit_logs_metrics,
    get_caisse_session_summary, get_clotures_caisse_metrics, get_comptabilite_export_data,
    get_notifications_metrics
)
from .permissions import (
    role_required, user_has_role, get_user_primary_role, get_user_role_code,
    get_user_home_url, assign_user_role, ROLES_CONFIG, ROLES_CHOICES,
    ROLE_ADMIN, ROLE_MANAGER, ROLE_MAGASINIER, ROLE_CAISSIER
)
from .services.alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire, generer_et_envoyer_resume_journalier
from .services.prediction_service import get_product_time_series_data, calculate_reorder_point_and_safety_stock
from .services.purchase_order_service import generate_purchase_order_data, generate_purchase_order_pdf, convert_order_data_to_approvisionnements
from .services.stock_service import ajuster_stock_manuel
from .services.notification_service import (
    generer_alertes_proactives,
    get_notifications_pour_utilisateur,
    marquer_notification_comme_lue,
    marquer_toutes_comme_lues,
    archiver_notification,
    get_statistiques_notifications,
)
from .services.backup_service import (
    creer_sauvegarde,
    lister_sauvegardes,
    restaurer_sauvegarde,
    supprimer_sauvegarde,
    verifier_integrite_base,
    purger_anciens_logs_audit,
    get_backup_dir,
)



@login_required
def dashboard(request):
    """
    Tableau de bord exécutif moderne et complet (Phase 5).
    Affiche le CA, bénéfice net, créances, dettes, alertes, valeur du stock et graphiques.
    Redirection automatique :
    - Un Caissier est orienté directement vers la Caisse POS
    - Un Magasinier est orienté directement vers la gestion du Stock
    - L'Administrateur et le Manager accèdent au pilotage exécutif
    """
    role_code = get_user_role_code(request.user)
    if role_code == ROLE_CAISSIER:
        return redirect('stockapp:caisse-pos')
    elif role_code == ROLE_MAGASINIER:
        return redirect('stockapp:stock-inventaire')

    metrics = get_dashboard_metrics()

    return render(request, 'stockapp/dashboard.html', {
        'stats': metrics,
        'alertes_actives': metrics['alertes_actives'],
        'top_produits_ventes': metrics['top_produits_ventes'],
        'ventes_recentes': metrics['ventes_recentes'],
        'mouvements_recents': metrics['mouvements_recents'],
        'chart_dates_json': json.dumps(metrics['chart_dates']),
        'chart_sales_values_json': json.dumps(metrics['chart_sales_values']),
    })


@login_required
@role_required('Admin', 'Manager')
def analytics_view(request):
    """
    Module Analytics Avancé & Performance Financière (Phase 6).
    Analyse de la performance des ventes, marges brutes par catégorie, panier moyen,
    matrice de rentabilité produits (BCG SMART-TECH) et répartition des modes de paiement.
    """
    metrics = get_advanced_analytics_metrics()

    return render(request, 'stockapp/analytics.html', {
        'ca_global': metrics['ca_global'],
        'cogs_global': metrics['cogs_global'],
        'benefice_global': metrics['benefice_global'],
        'volume_global': metrics['volume_global'],
        'taux_marge_global': metrics['taux_marge_global'],
        'nb_tickets': metrics['nb_tickets'],
        'panier_moyen': metrics['panier_moyen'],
        'articles_par_panier': metrics['articles_par_panier'],
        'cat_summary': metrics['cat_summary'],
        'prod_summary': metrics['prod_summary'],
        'modes_summary': metrics['modes_summary'],
        'counts_matrice': metrics['counts_matrice'],
        'articles_jamais_vendus': metrics['articles_jamais_vendus'],
        'chart_cat_labels_json': json.dumps(metrics['chart_cat_labels']),
        'chart_cat_ca_json': json.dumps(metrics['chart_cat_ca']),
        'chart_cat_benef_json': json.dumps(metrics['chart_cat_benef']),
        'chart_modes_labels_json': json.dumps(metrics['chart_modes_labels']),
        'chart_modes_ca_json': json.dumps(metrics['chart_modes_ca']),
    })



# ==================== PRODUITS ====================

@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def produits(request):
    query = request.GET.get('q')
    categorie_id = request.GET.get('categorie')

    produits_qs = Produit.objects.select_related('categorie').all()

    if query:
        produits_qs = produits_qs.filter(nom__icontains=query) | produits_qs.filter(reference__icontains=query)

    if categorie_id:
        produits_qs = produits_qs.filter(categorie_id=categorie_id)

    categories = Categorie.objects.all()

    return render(request, 'stockapp/produits.html', {
        'produits': produits_qs,
        'categories': categories,
    })


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def produit_ajouter(request):
    if request.method == 'POST':
        form = ProduitForm(request.POST)
        if form.is_valid():
            produit = form.save()
            creer_alerte_si_necessaire(produit)
            JournalAudit.log_action(
                utilisateur=request.user,
                action='CREATION',
                module='PRODUIT',
                objet_concerne=f"Produit #{produit.id} ({produit.nom})",
                description=f"Création du produit '{produit.nom}' (Réf: {produit.reference or '-'}, Prix: {produit.prix_unitaire} FCFA/€, Stock initial: {produit.stock_actuel})",
                request=request
            )
            messages.success(request, f"Produit '{produit.nom}' ajouté avec succès.")
            return redirect('stockapp:produits-list')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = ProduitForm()

    return render(request, 'stockapp/produit_form.html', {'form': form, 'title': 'Ajouter un Produit'})


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def produit_modifier(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    ancien_prix = produit.prix_unitaire
    if request.method == 'POST':
        form = ProduitForm(request.POST, instance=produit)
        if form.is_valid():
            produit = form.save()
            creer_alerte_si_necessaire(produit)
            resoudre_alerte_si_necessaire(produit)
            if ancien_prix != produit.prix_unitaire:
                JournalAudit.log_action(
                    utilisateur=request.user,
                    action='MODIFICATION_PRIX',
                    module='PRODUIT',
                    objet_concerne=f"Produit #{produit.id} ({produit.nom})",
                    description=f"Changement de prix de vente pour '{produit.nom}' : {ancien_prix} -> {produit.prix_unitaire} FCFA/€",
                    request=request
                )
            else:
                JournalAudit.log_action(
                    utilisateur=request.user,
                    action='MODIFICATION',
                    module='PRODUIT',
                    objet_concerne=f"Produit #{produit.id} ({produit.nom})",
                    description=f"Mise à jour des informations de la fiche produit '{produit.nom}'",
                    request=request
                )
            messages.success(request, f"Produit '{produit.nom}' modifié avec succès.")
            return redirect('stockapp:produits-list')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = ProduitForm(instance=produit)

    return render(request, 'stockapp/produit_form.html', {'form': form, 'title': f"Modifier '{produit.nom}'", 'produit': produit})


@login_required
@role_required('Admin')
def produit_supprimer(request, pk):
    if request.method == 'POST':
        produit = get_object_or_404(Produit, pk=pk)
        nom = produit.nom
        p_id = produit.id
        produit.delete()
        JournalAudit.log_action(
            utilisateur=request.user,
            action='SUPPRESSION',
            module='PRODUIT',
            objet_concerne=f"Produit #{p_id} ({nom})",
            description=f"Suppression définitive du produit '{nom}' (ID #{p_id})",
            request=request
        )
        messages.success(request, f"Produit '{nom}' supprimé avec succès.")
    return redirect('stockapp:produits-list')


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def stock_inventaire(request):

    """
    Interface moderne de gestion de stock & inventaire (Section 13).
    - KPI Cards : Total Produits, Stock Faible, Ruptures, Valeur globale du stock.
    - Tableau des Produits avec stock disponible, coût unitaire, prix vente, marge, statut.
    - Section Alertes Stock Faible et Mouvements de Stock Récents (Audit Trail).
    """
    query = request.GET.get('q', '').strip()
    categorie_id = request.GET.get('categorie', '').strip()
    statut_filter = request.GET.get('statut', '').strip()

    produits_qs = Produit.objects.select_related('categorie').all()

    if query:
        produits_qs = produits_qs.filter(
            models.Q(nom__icontains=query) |
            models.Q(reference__icontains=query) |
            models.Q(sku__icontains=query) |
            models.Q(code_barres__icontains=query)
        )

    if categorie_id:
        produits_qs = produits_qs.filter(categorie_id=categorie_id)

    # Statistiques globales (KPIs)
    all_produits = Produit.objects.all()
    total_produits = all_produits.count()
    ruptures_count = all_produits.filter(stock_actuel=0).count()
    stock_faible_count = all_produits.filter(stock_actuel__gt=0, stock_actuel__lte=F('seuil_alerte')).count()

    valeur_stock_achat = sum(p.valeur_stock_achat for p in all_produits)
    valeur_stock_vente = sum(p.valeur_stock_vente for p in all_produits)
    marge_estimee_stock = valeur_stock_vente - valeur_stock_achat

    # Filtrage statut produit
    if statut_filter == 'RUPTURE':
        produits_qs = produits_qs.filter(stock_actuel=0)
    elif statut_filter == 'FAIBLE':
        produits_qs = produits_qs.filter(stock_actuel__gt=0, stock_actuel__lte=F('seuil_alerte'))
    elif statut_filter == 'NORMAL':
        produits_qs = produits_qs.filter(stock_actuel__gt=F('seuil_alerte'), stock_actuel__lt=F('stock_maximum'))
    elif statut_filter == 'SURSTOCK':
        produits_qs = produits_qs.filter(stock_actuel__gte=F('stock_maximum'))

    mouvements_recents = MouvementStock.objects.select_related('produit', 'utilisateur').order_by('-date_mouvement')[:15]
    alertes_critiques = AlerteRupture.objects.filter(est_resolue=False).select_related('produit')[:10]
    categories = Categorie.objects.all()
    ajustement_form = AjustementStockForm()

    return render(request, 'stockapp/stock_inventaire.html', {
        'produits': produits_qs,
        'categories': categories,
        'total_produits': total_produits,
        'ruptures_count': ruptures_count,
        'stock_faible_count': stock_faible_count,
        'valeur_stock_achat': valeur_stock_achat,
        'valeur_stock_vente': valeur_stock_vente,
        'marge_estimee_stock': marge_estimee_stock,
        'mouvements_recents': mouvements_recents,
        'alertes_critiques': alertes_critiques,
        'ajustement_form': ajustement_form,
        'selected_query': query,
        'selected_categorie': categorie_id,
        'selected_statut': statut_filter,
    })


@login_required
@role_required('Admin', 'Manager', 'Magasinier')
def ajuster_stock_view(request):
    """Effectuer un ajustement manuel du stock ou une régularisation d'inventaire."""
    if request.method == 'POST':
        form = AjustementStockForm(request.POST)
        if form.is_valid():
            produit = form.cleaned_data['produit']
            nouveau_stock = form.cleaned_data['nouveau_stock']
            motif = form.cleaned_data['motif']
            ancien_stock = produit.stock_actuel
            ajuster_stock_manuel(produit, nouveau_stock, utilisateur=request.user, motif=motif)
            JournalAudit.log_action(
                utilisateur=request.user,
                action='AJUSTEMENT_STOCK',
                module='STOCK',
                objet_concerne=f"Produit #{produit.id} ({produit.nom})",
                description=f"Régularisation manuelle de stock pour '{produit.nom}' : {ancien_stock} -> {nouveau_stock} unité(s). Motif: {motif}",
                request=request
            )
            messages.success(request, f"✅ Stock du produit '{produit.nom}' ajusté à {nouveau_stock} unité(s).")
        else:
            messages.error(request, "Veuillez vérifier la saisie de l'ajustement.")
    return redirect('stockapp:stock-inventaire')


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def mouvements_list_view(request):
    """Consulter l'historique complet et détaillé des mouvements de stock (Audit Trail)."""
    type_mouvement = request.GET.get('type')
    produit_id = request.GET.get('produit')

    mouvements_qs = MouvementStock.objects.select_related('produit', 'utilisateur').all()

    if type_mouvement:
        mouvements_qs = mouvements_qs.filter(type_mouvement=type_mouvement)
    if produit_id:
        mouvements_qs = mouvements_qs.filter(produit_id=produit_id)

    produits = Produit.objects.order_by('nom')
    types_mouvements = MouvementStock.TYPE_MOUVEMENT_CHOICES

    return render(request, 'stockapp/mouvements.html', {
        'mouvements': mouvements_qs[:100],
        'produits': produits,
        'types_mouvements': types_mouvements,
        'selected_type': type_mouvement,
        'selected_produit': produit_id,
    })


# ==================== CATÉGORIES ====================


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def categories(request):
    if request.method == 'POST':
        form = CategorieForm(request.POST)
        if form.is_valid():
            cat = form.save()
            messages.success(request, f"Catégorie '{cat.nom}' créée.")
            return redirect('stockapp:categories-list')
        else:
            messages.error(request, "Erreur lors de la création de la catégorie.")
    else:
        form = CategorieForm()

    categories_qs = Categorie.objects.annotate(produits_count=Count('produit')).order_by('nom')
    return render(request, 'stockapp/categories.html', {
        'categories': categories_qs,
        'form': form,
    })


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def categorie_modifier(request, pk):
    cat = get_object_or_404(Categorie, pk=pk)
    if request.method == 'POST':
        form = CategorieForm(request.POST, instance=cat)
        if form.is_valid():
            form.save()
            messages.success(request, f"Catégorie '{cat.nom}' modifiée.")
            return redirect('stockapp:categories-list')
    else:
        form = CategorieForm(instance=cat)
    return render(request, 'stockapp/categorie_form.html', {'form': form, 'categorie': cat})


@login_required
@role_required('Admin')
def categorie_supprimer(request, pk):
    if request.method == 'POST':
        cat = get_object_or_404(Categorie, pk=pk)
        nom = cat.nom
        cat.delete()
        messages.success(request, f"Catégorie '{nom}' supprimée.")
    return redirect('stockapp:categories-list')


# ==================== VENTES & BILAN ====================

@login_required
@role_required('Admin', 'Caissier', 'Manager')
def ventes(request):
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
    else:
        debut_periode = selected_date
        fin_periode = selected_date
        label_periode = f"Journée du {selected_date.strftime('%d/%m/%Y')}"

    if request.method == 'POST':
        form = VenteForm(request.POST)
        if form.is_valid():
            vente = form.save(commit=False)
            vente._current_user = request.user
            vente.save()
            JournalAudit.log_action(
                utilisateur=request.user,
                action='VENTE',
                module='VENTE',
                objet_concerne=f"Vente #{vente.id} ({vente.produit.nom})",
                description=f"Vente manuelle de {vente.quantite}x '{vente.produit.nom}' pour un montant de {vente.prix_total} FCFA/€ ({vente.mode_paiement})",
                request=request
            )
            messages.success(request, f"Vente de {vente.quantite}x '{vente.produit.nom}' enregistrée (CA: {vente.prix_total} | Bénéfice: {vente.benefice_total} FCFA/€).")
            return redirect(f"{reverse('stockapp:ventes-list')}?date={selected_date.strftime('%Y-%m-%d')}&periode={periode}")
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = VenteForm()

    ventes_periode = Vente.objects.filter(
        date_vente__date__gte=debut_periode,
        date_vente__date__lte=fin_periode
    ).select_related('produit').order_by('date_vente')

    ventes_jour = Vente.objects.filter(date_vente__date=selected_date).select_related('produit').order_by('date_vente')

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

    chiffre_affaires_periode = sum(v.prix_total for v in ventes_periode)
    benefice_net_periode = sum(v.benefice_total for v in ventes_periode)
    total_articles_periode = sum(v.quantite for v in ventes_periode)

    produits_data = {
        p.id: {'prix_unitaire': float(p.prix_unitaire), 'prix_achat': float(p.prix_achat)}
        for p in Produit.objects.all()
    }

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
        'produits_prices_json': json.dumps(produits_data),
        'form': form,
        'periode_choices': [
            ('jour', 'Jour'),
            ('semaine', 'Semaine'),
            ('mois', 'Mois'),
            ('annee', 'Année'),
        ],
    })


@login_required
@role_required('Admin')
def vente_supprimer(request, pk):
    if request.method == 'POST':
        vente = get_object_or_404(Vente, pk=pk)
        nom = vente.produit.nom
        v_id = vente.id
        qte = vente.quantite
        total = vente.prix_total
        vente._current_user = request.user
        vente.delete()
        JournalAudit.log_action(
            utilisateur=request.user,
            action='SUPPRESSION',
            module='VENTE',
            objet_concerne=f"Vente #{v_id} ({nom})",
            description=f"Suppression et annulation de la vente #{v_id} de {qte}x '{nom}' (Montant: {total} FCFA/€)",
            request=request
        )
        messages.success(request, f"Vente de '{nom}' supprimée. Le stock a été réapprovisionné.")
    return redirect('stockapp:ventes-list')


@login_required
@role_required('Admin', 'Caissier')
def caisse_pos(request):
    """
    Interface de caisse enregistreuse POS moderne et interactive (Étape 3).
    Recherche rapide de produits, panier multi-articles, choix du client, mode de paiement,
    calcul de monnaie et encaissement atomique.
    """
    if request.method == 'POST':
        cart_data = request.POST.get('cart_data')
        client_id = request.POST.get('client_id')
        mode_paiement = request.POST.get('mode_paiement', 'ESPECES')
        remise_globale_str = request.POST.get('remise_globale', '0')
        notes = request.POST.get('notes', '')

        try:
            items = json.loads(cart_data) if cart_data else []
        except Exception:
            items = []

        if not items:
            messages.error(request, "Le panier est vide. Veuillez ajouter au moins un produit.")
            return redirect('stockapp:caisse-pos')

        client = None
        if client_id:
            client = Client.objects.filter(pk=client_id).first()

        if mode_paiement == 'CREDIT' and not client:
            messages.error(request, "Une vente à crédit exige obligatoirement la sélection d'une fiche client valide.")
            return redirect('stockapp:caisse-pos')

        try:
            remise_globale = Decimal(remise_globale_str)
        except Exception:
            remise_globale = Decimal('0.00')

        import uuid
        ticket_ref = f"TCK-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        ventes_creees = []
        total_panier_net = Decimal('0.00')

        with transaction.atomic():
            remise_par_item = remise_globale / Decimal(len(items)) if len(items) > 0 else Decimal('0.00')

            for item in items:
                produit_id = item.get('produit_id')
                qte = int(item.get('quantite', 1))
                pu = Decimal(str(item.get('prix_unitaire', 0)))

                produit = get_object_or_404(Produit, pk=produit_id)
                if qte > produit.stock_actuel:
                    messages.error(request, f"Stock insuffisant pour '{produit.nom}' (Stock actuel: {produit.stock_actuel}, Demandé: {qte})")
                    return redirect('stockapp:caisse-pos')

                vente = Vente(
                    produit=produit,
                    client=client,
                    quantite=qte,
                    prix_unitaire=pu,
                    prix_achat=produit.prix_achat,
                    remise=remise_par_item,
                    mode_paiement=mode_paiement,
                    reference_ticket=ticket_ref,
                    notes=notes
                )
                vente._current_user = request.user
                vente.save()
                ventes_creees.append(vente)
                total_panier_net += vente.prix_total

            # Imputation atomique sur l'encours crédit client
            if mode_paiement == 'CREDIT' and client:
                client.solde_credit += total_panier_net
                client.save(update_fields=['solde_credit'])

            JournalAudit.log_action(
                utilisateur=request.user,
                action='VENTE',
                module='VENTE',
                objet_concerne=f"Ticket {ticket_ref}",
                description=f"Encaissement POS Ticket {ticket_ref} : {len(ventes_creees)} article(s) pour un total de {total_panier_net:.2f} FCFA/€ ({mode_paiement})" + (f" - Client: {client.nom}" if client else ""),
                request=request
            )

        msg_extra = f" (Porté au compte crédit de {client.nom})" if (mode_paiement == 'CREDIT' and client) else ""
        messages.success(request, f"✅ Vente de {len(ventes_creees)} article(s) encaissée avec succès (Ticket {ticket_ref}){msg_extra}.")
        return redirect(f"{reverse('stockapp:caisse-pos')}?recu={ticket_ref}")

    produits_qs = Produit.objects.select_related('categorie').filter(statut='ACTIF').order_by('nom')
    clients_qs = Client.objects.all().order_by('nom')
    categories_qs = Categorie.objects.all().order_by('nom')

    produits_list_json = []
    for p in produits_qs:
        produits_list_json.append({
            'id': p.id,
            'nom': p.nom,
            'reference': p.reference,
            'sku': p.sku or '',
            'code_barres': p.code_barres or '',
            'prix_unitaire': float(p.prix_unitaire),
            'stock_actuel': p.stock_actuel,
            'statut_stock': p.statut_stock,
            'categorie': p.categorie.nom if p.categorie else 'Autre',
            'categorie_id': p.categorie_id or 0,
        })

    clients_list_json = [
        {
            'id': c.id,
            'nom': c.nom,
            'telephone': c.telephone or '',
            'solde_credit': float(c.solde_credit),
        }
        for c in clients_qs
    ]

    recu_ref = request.GET.get('recu')
    ventes_recu = []
    if recu_ref:
        ventes_recu = Vente.objects.filter(reference_ticket=recu_ref).select_related('produit', 'client')

    return render(request, 'stockapp/caisse_pos.html', {
        'produits': produits_qs,
        'clients': clients_qs,
        'categories': categories_qs,
        'produits_json': json.dumps(produits_list_json),
        'clients_json': json.dumps(clients_list_json),
        'ventes_recu': ventes_recu,
        'recu_ref': recu_ref,
        'mode_paiement_choices': Vente.MODE_PAIEMENT_CHOICES,
    })


@login_required
@role_required('Admin', 'Caissier', 'Manager')
def clients_list_view(request):
    """Gestion des fiches Clients."""
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Client '{client.nom}' enregistré avec succès.")
            return redirect('stockapp:clients-list')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire Client.")
    else:
        form = ClientForm()

    query = request.GET.get('q', '').strip()
    clients_qs = Client.objects.all()
    if query:
        clients_qs = clients_qs.filter(
            models.Q(nom__icontains=query) |
            models.Q(telephone__icontains=query) |
            models.Q(email__icontains=query)
        )

    return render(request, 'stockapp/clients.html', {
        'clients': clients_qs,
        'form': form,
        'selected_query': query,
    })


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def fournisseurs_list_view(request):
    """Gestion et répertoire des fiches Fournisseurs partenaires."""
    if request.method == 'POST':
        form = FournisseurForm(request.POST)
        if form.is_valid():
            fournisseur = form.save()
            messages.success(request, f"Fournisseur '{fournisseur.nom}' enregistré avec succès.")
            return redirect('stockapp:fournisseurs-list')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire Fournisseur.")
    else:
        form = FournisseurForm()

    query = request.GET.get('q', '').strip()
    fournisseurs_qs = Fournisseur.objects.all().prefetch_related('approvisionnements')
    if query:
        fournisseurs_qs = fournisseurs_qs.filter(
            models.Q(nom__icontains=query) |
            models.Q(telephone__icontains=query) |
            models.Q(email__icontains=query)
        )

    # Calculs de synthèse
    total_fournisseurs = fournisseurs_qs.count()
    total_dette_fournisseurs = sum(f.dette_fournisseur for f in fournisseurs_qs)

    return render(request, 'stockapp/fournisseurs.html', {
        'fournisseurs': fournisseurs_qs,
        'form': form,
        'selected_query': query,
        'total_fournisseurs': total_fournisseurs,
        'total_dette_fournisseurs': total_dette_fournisseurs,
        'regler_form': ReglerDetteFournisseurForm(),
    })


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def fournisseur_detail_view(request, pk):
    """Fiche détaillée d'un fournisseur avec historique de ses livraisons."""
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    approvisionnements = fournisseur.approvisionnements.select_related('produit').order_by('-date_approvisionnement')
    total_volume = sum(a.quantite for a in approvisionnements)
    total_depenses = sum(a.cout_total for a in approvisionnements)

    regler_form = ReglerDetteFournisseurForm()

    return render(request, 'stockapp/fournisseur_detail.html', {
        'fournisseur': fournisseur,
        'approvisionnements': approvisionnements,
        'total_volume': total_volume,
        'total_depenses': total_depenses,
        'regler_form': regler_form,
    })


@login_required
@role_required('Admin', 'Manager')
def fournisseur_regler_dette_view(request, pk):
    """Règlement partiel ou total de la dette d'un fournisseur."""
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    if request.method == 'POST':
        form = ReglerDetteFournisseurForm(request.POST)
        if form.is_valid():
            montant = form.cleaned_data['montant']
            moyen = form.cleaned_data['moyen_reglement']
            notes = form.cleaned_data.get('notes', '')

            ancienne_dette = fournisseur.dette_fournisseur
            nouvelle_dette = max(Decimal('0.00'), ancienne_dette - montant)
            fournisseur.dette_fournisseur = nouvelle_dette
            fournisseur.save(update_fields=['dette_fournisseur'])

            JournalAudit.log_action(
                utilisateur=request.user,
                action='REGLEMENT_DETTE',
                module='FOURNISSEUR',
                objet_concerne=f"Fournisseur #{fournisseur.id} ({fournisseur.nom})",
                description=f"Règlement dette fournisseur '{fournisseur.nom}' de {montant:,.2f} FCFA/€ ({moyen}). Dette résiduelle: {nouvelle_dette:,.2f} FCFA/€",
                request=request
            )

            messages.success(
                request,
                f"Règlement de {montant:,.2f} FCFA/€ ({moyen}) enregistré pour {fournisseur.nom}. "
                f"Dette résiduelle : {nouvelle_dette:,.2f} FCFA/€."
            )
        else:
            messages.error(request, "Erreur dans les données du règlement.")
    return redirect(request.META.get('HTTP_REFERER') or reverse('stockapp:fournisseurs-list'))


@login_required
@role_required('Admin', 'Caissier', 'Manager')
def telecharger_recu_pdf(request, pk):
    """
    Génération du Ticket / Facture de Caisse PDF professionnel SMART-TECH.
    Prend en charge les ventes individuelles ou les paniers multi-articles par reference_ticket.
    """
    vente_principale = get_object_or_404(Vente, pk=pk)
    if vente_principale.reference_ticket:
        ventes_items = Vente.objects.filter(reference_ticket=vente_principale.reference_ticket).select_related('produit', 'client')
    else:
        ventes_items = [vente_principale]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(240, 520), leftMargin=12, rightMargin=12, topMargin=15, bottomMargin=15)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>SMART-TECH</b>", styles['Title']))
    story.append(Paragraph("Solution Commerciale & Stock IA", styles['Normal']))
    story.append(Spacer(1, 6))

    ref_num = vente_principale.reference_ticket or f"TCK-#{vente_principale.pk:06d}"
    story.append(Paragraph(f"<b>Ticket / Reçu N° {ref_num}</b>", styles['Heading2']))
    story.append(Paragraph(f"Date : {vente_principale.date_vente.strftime('%d/%m/%Y à %H:%M')}", styles['Normal']))
    
    client_name = vente_principale.client.nom if vente_principale.client else "Client Comptoir"
    story.append(Paragraph(f"Client : {client_name}", styles['Normal']))
    story.append(Paragraph(f"Paiement : {vente_principale.get_mode_paiement_display()}", styles['Normal']))
    story.append(Spacer(1, 8))

    table_data = [['Produit', 'Qté', 'P.U', 'Total']]
    montant_total_ticket = Decimal('0.00')

    for v in ventes_items:
        tot_v = v.prix_total
        montant_total_ticket += tot_v
        table_data.append([
            v.produit.nom[:16],
            str(v.quantite),
            f"{v.prix_unitaire:.2f}",
            f"{tot_v:.2f}"
        ])

    tbl = Table(table_data, colWidths=[90, 30, 45, 50])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ('PADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))

    summary_data = [
        ['TOTAL NET', f"{montant_total_ticket:,.2f} FCFA/€"]
    ]
    if vente_principale.mode_paiement == 'CREDIT':
        summary_data.append(['RÈGLEMENT', 'À CRÉDIT'])
        if vente_principale.client:
            summary_data.append(['EN-COURS CLIENT', f"{vente_principale.client.solde_credit:,.2f} FCFA"])

    sum_tbl = Table(summary_data, colWidths=[115, 100])
    sum_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0891b2')),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 12))
    story.append(Paragraph("Merci de votre confiance ! À bientôt.", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="ticket_{ref_num}.pdf"'
    return response


@login_required
@role_required('Admin', 'Caissier', 'Manager')
def telecharger_facture_pdf(request, pk):
    """
    Génération d'une Facture Commerciale PDF A4 officielle SMART-TECH (Section 11).
    Prend en compte les informations complètes du client, le détail des produits,
    les remises, la TVA/Taxes et les coordonnées d'entreprise.
    """
    vente_principale = get_object_or_404(Vente, pk=pk)
    if vente_principale.reference_ticket:
        ventes_items = Vente.objects.filter(reference_ticket=vente_principale.reference_ticket).select_related('produit', 'client')
    else:
        ventes_items = [vente_principale]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=35, rightMargin=35, topMargin=35, bottomMargin=35)
    styles = getSampleStyleSheet()

    story = []

    inv_number = vente_principale.reference_ticket or f"FAC-{vente_principale.pk:06d}"
    if not inv_number.startswith('FAC-'):
        inv_number = inv_number.replace('TCK-', 'FAC-')

    header_data = [
        [
            Paragraph("<b>SMART-TECH GESTION COMMERCIALE</b><br/>Solutions d'Entreprise & Stock IA<br/>Cotonou, Bénin — contact@smart-tech.io", styles['Normal']),
            Paragraph(f"<font color='#0891b2'><b>FACTURE COMMERCIALE</b></font><br/><b>N° :</b> {inv_number}<br/><b>Date :</b> {vente_principale.date_vente.strftime('%d/%m/%Y à %H:%M')}", styles['Normal'])
        ]
    ]
    t_hdr = Table(header_data, colWidths=[320, 220])
    t_hdr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_hdr)
    story.append(Spacer(1, 15))

    client = vente_principale.client
    client_name = client.nom if client else "Client Comptoir"
    client_tel = client.telephone if client and client.telephone else "Non renseigné"
    client_email = client.email if client and client.email else "Non renseigné"
    client_addr = client.adresse if client and client.adresse else "Adresse standard"

    client_box = [
        [Paragraph(f"<b>FACTURÉ À :</b><br/><b>{client_name}</b><br/>Tél : {client_tel}<br/>Email : {client_email}<br/>Adresse : {client_addr}", styles['Normal']),
         Paragraph(f"<b>CONDITIONS DE RÈGLEMENT :</b><br/>Mode de paiement : <b>{vente_principale.get_mode_paiement_display()}</b><br/>Statut : <b>Payé / Acquitté</b>", styles['Normal'])]
    ]
    t_client = Table(client_box, colWidths=[320, 220])
    t_client.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_client)
    story.append(Spacer(1, 20))

    items_data = [['Réf.', 'Description du Produit', 'Qté', 'Prix Unit.', 'Remise', 'Total Net']]
    total_brut = Decimal('0.00')
    total_remise = Decimal('0.00')
    net_a_payer = Decimal('0.00')

    for v in ventes_items:
        brut = v.montant_brut
        rem = v.remise
        net = v.prix_total
        total_brut += brut
        total_remise += rem
        net_a_payer += net

        items_data.append([
            v.produit.reference,
            v.produit.nom,
            str(v.quantite),
            f"{v.prix_unitaire:.2f}",
            f"{v.remise:.2f}",
            f"{net:.2f} FCFA"
        ])

    tbl_items = Table(items_data, colWidths=[70, 220, 45, 65, 65, 75])
    tbl_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0891b2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTSIZE', (0, 1), (-1, -1), 8.5),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl_items)
    story.append(Spacer(1, 15))

    totaux_data = [
        ['Total Brut :', f"{total_brut:,.2f} FCFA/€"],
        ['Remise Accordée :', f"- {total_remise:,.2f} FCFA/€"],
        ['NET À PAYER TTC :', f"{net_a_payer:,.2f} FCFA/€"]
    ]
    t_tot = Table(totaux_data, colWidths=[120, 100])
    t_tot.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 11),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#0891b2')),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))

    wrapper_tot = Table([['', t_tot]], colWidths=[320, 220])
    wrapper_tot.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
    story.append(wrapper_tot)
    story.append(Spacer(1, 25))

    sig_data = [
        ['Visa & Cachet Client', 'Pour SMART-TECH (La Direction)'],
        ['\n\n__________________________', '\n\n__________________________']
    ]
    sig_tbl = Table(sig_data, colWidths=[270, 270])
    sig_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#475569')),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<font color='#94a3b8' size='7'>Facture établie conformément aux règles commerciales en vigueur. Document officiel émis par SMART-TECH.</font>", styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="facture_{inv_number}.pdf"'
    return response


@login_required
@role_required('Admin', 'Manager')
def previsions_decision_view(request):
    """
    Module de Prévisions IA & Aide à la Décision (Phase 8 - Intelligence Commerciale).
    Synthèse par produit : stock actuel, consommation moyenne, jours avant rupture,
    stock de sécurité, point de commande (ROP), budget prévisionnel et simulateur temporel.
    """
    categorie_id = request.GET.get('categorie', '').strip()
    query = request.GET.get('q', '').strip()

    items = get_decision_support_metrics(categorie_id=categorie_id, query=query)
    categories = Categorie.objects.all().order_by('nom')

    total_produits = len(items)
    nb_critique = sum(1 for x in items if x['niveau_risque'] == 'CRITIQUE')
    nb_eleve = sum(1 for x in items if x['niveau_risque'] == 'ELEVE')
    nb_dormant = sum(1 for x in items if x.get('is_dormant', False))
    nb_surstock = sum(1 for x in items if x['niveau_risque'] == 'SURSTOCK')
    nb_securise = sum(1 for x in items if x['niveau_risque'] == 'FAIBLE')
    budget_total_reappro = sum(x.get('budget_estime', 0.0) for x in items if x['action_requise'])

    # Sélection du produit pour initialiser le simulateur interactif
    selected_prod_id = request.GET.get('prod_id', '').strip()
    selected_item = None
    if selected_prod_id:
        selected_item = next((x for x in items if str(x['produit'].id) == selected_prod_id), None)
    if not selected_item and items:
        critiques = [x for x in items if x['action_requise']]
        selected_item = critiques[0] if critiques else items[0]

    simulator_data = None
    if selected_item:
        simulator_data = get_product_time_series_data(selected_item['produit'], days_lookback=14, days_ahead=14)

    return render(request, 'stockapp/previsions_decision.html', {
        'items': items,
        'categories': categories,
        'selected_categorie': categorie_id,
        'selected_query': query,
        'selected_item': selected_item,
        'total_produits': total_produits,
        'nb_critique': nb_critique,
        'nb_eleve': nb_eleve,
        'nb_dormant': nb_dormant,
        'nb_surstock': nb_surstock,
        'nb_securise': nb_securise,
        'budget_total_reappro': budget_total_reappro,
        'simulator_data': simulator_data,
        'simulator_json': json.dumps(simulator_data) if simulator_data else '{}',
    })


@login_required
@role_required('Admin', 'Manager')
def produit_prevision_chart_api(request, pk):
    """
    Endpoint JSON retournant les séries temporelles passées et projections futures
    pour le simulateur dynamique Chart.js (Phase 8).
    """
    produit = get_object_or_404(Produit, pk=pk)
    data = get_product_time_series_data(produit, days_lookback=14, days_ahead=14)
    return JsonResponse(data)


@login_required
@role_required('Admin', 'Manager')
def previsions_decision_pdf(request):
    """
    Génération du rapport exécutif d'aide à la décision & prévisions de réapprovisionnement (Phase 8).
    """
    items = get_decision_support_metrics()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        name='DecTitle',
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0F172A'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        name='DecSubtitle',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#64748B'),
        alignment=1
    )
    h2_style = ParagraphStyle(
        name='DecH2',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0891B2'),
        spaceBefore=10,
        spaceAfter=4
    )

    story = []
    story.append(Paragraph('SMART-TECH — PLAN D\'AIDE À LA DÉCISION & RÉAPPROVISIONNEMENT IA', title_style))
    story.append(Paragraph(f'Édité le {timezone.now().strftime("%d/%m/%Y à %H:%M")} | Moteur Prédictif Machine Learning', subtitle_style))
    story.append(Spacer(1, 14))

    # Résumé exécutif
    nb_critique = sum(1 for x in items if x['niveau_risque'] == 'CRITIQUE')
    nb_eleve = sum(1 for x in items if x['niveau_risque'] == 'ELEVE')
    nb_dormant = sum(1 for x in items if x.get('is_dormant', False))
    budget_total = sum(x.get('budget_estime', 0.0) for x in items if x['action_requise'])

    summary_data = [
        ['Articles Sous IA', 'Ruptures Critiques (≤3j)', 'Risque Élevé (≤7j)', 'Produits Dormants', 'Budget Réappro Requis'],
        [str(len(items)), str(nb_critique), str(nb_eleve), str(nb_dormant), f"{budget_total:,.2f} FCFA/€"]
    ]
    t_summary = Table(summary_data, colWidths=[105, 115, 110, 105, 115])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#F8FAFC')),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 12))

    story.append(Paragraph('Articles Prioritaires Nécessitant une Commande Fournisseur Immédiate', h2_style))

    table_data = [
        ['Produit / Réf', 'Stock', 'Sécurité', 'ROP', 'Cons/J', 'Rupture', 'À Commander', 'Budget Est.']
    ]
    urgents = [x for x in items if x['action_requise']]
    if not urgents:
        urgents = items[:10]

    for item in urgents[:25]:
        stockout_str = f"~{item['stockout_days']:.0f}j" if isinstance(item['stockout_days'], (int, float)) and item['stockout_days'] < 999 else "Épuisé"
        table_data.append([
            item['produit'].nom[:20],
            str(item['stock_actuel']),
            str(item.get('safety_stock', '-')),
            str(item.get('rop', '-')),
            f"{item['conso_moyenne']:.1f}",
            stockout_str,
            f"{item.get('qte_recommandee', 0)} un.",
            f"{item.get('budget_estime', 0.0):.2f}"
        ])

    table_prio = Table(table_data, colWidths=[140, 45, 50, 45, 50, 58, 72, 90])
    table_prio.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0891B2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(table_prio)

    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="plan_aide_decision_{timezone.now().strftime("%Y%m%d")}.pdf"'
    return response




# ==================== APPROVISIONNEMENTS ====================

@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def approvisionnements(request):
    """
    Gestion des Approvisionnements et Réceptions de marchandises SMART-TECH.
    Prend en charge l'enregistrement avec fournisseur relationnel, mise à jour
    automatique des prix d'achat, détection des dettes fournisseurs et traçabilité.
    """
    if request.method == 'POST':
        form = ApprovisionnementForm(request.POST)
        if form.is_valid():
            appro = form.save(commit=False)
            appro._current_user = request.user
            appro.save()

            # Imputation optionnelle sur la dette / compte fournisseur
            if request.POST.get('imputer_dette') == 'on' and appro.fournisseur_fk:
                cout = appro.cout_total
                if cout > 0:
                    appro.fournisseur_fk.dette_fournisseur += cout
                    appro.fournisseur_fk.save(update_fields=['dette_fournisseur'])

            JournalAudit.log_action(
                utilisateur=request.user,
                action='CREATION',
                module='APPROVISIONNEMENT',
                objet_concerne=f"Appro #{appro.id} ({appro.produit.nom})",
                description=f"Nouvel approvisionnement de +{appro.quantite}x '{appro.produit.nom}' auprès de '{appro.nom_fournisseur}' (Coût total: {appro.cout_total:.2f} FCFA/€)",
                request=request
            )

            messages.success(
                request,
                f"Approvisionnement de +{appro.quantite} '{appro.produit.nom}' enregistré avec succès "
                f"auprès de '{appro.nom_fournisseur}'."
            )
            return redirect('stockapp:approvisionnements-list')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire d'approvisionnement.")
    else:
        form = ApprovisionnementForm()

    query = request.GET.get('q', '').strip()
    fournisseur_filter = request.GET.get('fournisseur', '').strip()

    approvisionnements_qs = Approvisionnement.objects.select_related('produit', 'fournisseur_fk').order_by('-date_approvisionnement')

    if query:
        approvisionnements_qs = approvisionnements_qs.filter(
            models.Q(produit__nom__icontains=query) |
            models.Q(produit__reference__icontains=query) |
            models.Q(fournisseur__icontains=query)
        )

    if fournisseur_filter:
        approvisionnements_qs = approvisionnements_qs.filter(
            models.Q(fournisseur_fk_id=fournisseur_filter) |
            models.Q(fournisseur__icontains=fournisseur_filter)
        )

    # Métriques récapitulatives consolidées
    all_appros = Approvisionnement.objects.select_related('produit').all()
    total_quantite = all_appros.aggregate(total=Sum('quantite'))['total'] or 0
    total_operations = all_appros.count()
    total_depenses = sum(a.cout_total for a in all_appros)
    fournisseurs = Fournisseur.objects.all().order_by('nom')

    return render(request, 'stockapp/approvisionnements.html', {
        'approvisionnements': approvisionnements_qs[:100],
        'total_approvisionnements': total_quantite,
        'total_depenses': total_depenses,
        'total_operations': total_operations,
        'fournisseurs': fournisseurs,
        'selected_query': query,
        'selected_fournisseur': fournisseur_filter,
        'form': form,
    })


@login_required
@role_required('Admin', 'Manager')
def approvisionnement_supprimer(request, pk):
    """Annulation d'un approvisionnement avec restauration de stock sécurisée."""
    if request.method == 'POST':
        appro = get_object_or_404(Approvisionnement, pk=pk)
        nom = appro.produit.nom
        a_id = appro.id
        qte = appro.quantite
        appro._current_user = request.user
        appro.delete()
        JournalAudit.log_action(
            utilisateur=request.user,
            action='SUPPRESSION',
            module='APPROVISIONNEMENT',
            objet_concerne=f"Appro #{a_id} ({nom})",
            description=f"Suppression et annulation de l'approvisionnement #{a_id} (+{qte}x '{nom}')",
            request=request
        )
        messages.success(request, f"Approvisionnement de '{nom}' annulé. Le stock a été déduit conformément.")
    return redirect('stockapp:approvisionnements-list')


# ==================== BON DE COMMANDE IA & NOTIFICATIONS ====================

@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def bon_de_commande(request):
    """Centre de génération du Bon de Commande Fournisseur basé sur l'IA."""
    order_data = generate_purchase_order_data()
    fournisseurs = Fournisseur.objects.all().order_by('nom')
    return render(request, 'stockapp/bon_de_commande.html', {
        'order_data': order_data,
        'fournisseurs': fournisseurs,
    })


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def bon_de_commande_pdf(request):
    """Téléchargement du Bon de Commande Officiel PDF SMART-TECH."""
    order_data = generate_purchase_order_data()
    pdf_bytes = generate_purchase_order_pdf(order_data)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Bon_de_Commande_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
def bon_de_commande_valider(request):
    """Conversion en 1 clic du Bon de Commande IA en vrais approvisionnements."""
    if request.method == 'POST':
        fournisseur_id = request.POST.get('fournisseur_id')
        fournisseur_fk = None
        if fournisseur_id:
            fournisseur_fk = Fournisseur.objects.filter(pk=fournisseur_id).first()
        fournisseur_nom = request.POST.get('fournisseur_nom') or (fournisseur_fk.nom if fournisseur_fk else "Fournisseur Automatique IA")

        order_data = generate_purchase_order_data()
        count = convert_order_data_to_approvisionnements(
            order_data,
            fournisseur_nom=fournisseur_nom,
            fournisseur_fk=fournisseur_fk,
            user=request.user
        )
        messages.success(
            request,
            f"✅ {count} approvisionnement(s) créé(s) avec succès pour le fournisseur '{fournisseur_nom}' !"
        )
    return redirect('stockapp:approvisionnements-list')


@login_required
@role_required('Admin', 'Manager')
def envoyer_resume_journalier_view(request):
    if request.method == 'POST':
        res = generer_et_envoyer_resume_journalier()
        messages.success(
            request,
            f"📲 Résumé envoyé à l'administration ! (CA: {res['chiffre_affaires']} | Bénéfice: {res['benefice_net']} FCFA/€)"
        )
    return redirect(request.META.get('HTTP_REFERER', 'stockapp:dashboard'))


# ==================== PWA VIEWS ====================

def service_worker(request):
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
    manifest_path = os.path.join(settings.BASE_DIR, 'stockapp', 'static', 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = json.dumps({
            "name": "SMART-TECH Gestion Commerciale & Stock IA",
            "short_name": "SMART-TECH",
            "description": "Application PWA de gestion commerciale, stock et prédictions par IA.",
            "start_url": "/",
            "display": "standalone"
        })
    return HttpResponse(content, content_type='application/manifest+json')


def offline_view(request):
    """
    Page de secours hors-ligne PWA SMART-TECH (Phase 10).
    Affichée automatiquement par le Service Worker en l'absence de réseau.
    """
    return render(request, 'stockapp/offline.html')


# ==================== INFOS ET EXPORT ====================

def home(request):
    """
    Page d'accueil vitrine du site web SMART-TECH.
    Présentation des univers de produits, des articles en boutique,
    des services, horaires et accès à l'espace de gestion.
    """
    categories = Categorie.objects.annotate(nb_produits=Count('produit')).order_by('nom')[:8]
    produits_phares = Produit.objects.filter(statut='ACTIF').order_by('-stock_actuel')[:8]
    total_produits = Produit.objects.filter(statut='ACTIF').count()
    total_categories = Categorie.objects.count()
    context = {
        'categories': categories,
        'produits_phares': produits_phares,
        'total_produits': total_produits,
        'total_categories': total_categories,
    }
    return render(request, 'stockapp/home.html', context)


def info(request):
    return render(request, 'stockapp/info.html')


@login_required
@role_required('Admin', 'Magasinier', 'Manager')
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


# ==================== MODULE FINANCIER & TRÉSORERIE (PHASE 7) ====================

@login_required
@role_required('Admin', 'Manager')
def finances_view(request):
    """
    Centre Financier & Pilotage de Trésorerie (Phase 7).
    Restitue le P&L simplifié, l'audit de trésorerie, la balance créances/dettes
    et permet la saisie directe des dépenses opérationnelles.
    """
    if request.method == 'POST':
        form = DepenseForm(request.POST)
        if form.is_valid():
            depense = form.save(commit=False)
            depense.utilisateur = request.user
            depense.save()
            JournalAudit.log_action(
                utilisateur=request.user,
                action='DEPENSE',
                module='FINANCES',
                objet_concerne=f"Dépense #{depense.id} ({depense.titre})",
                description=f"Enregistrement de la dépense '{depense.titre}' de {depense.montant:.2f} FCFA/€ ({depense.get_categorie_display()})",
                request=request
            )
            messages.success(request, f"Dépense '{depense.titre}' de {depense.montant:.2f} FCFA/€ enregistrée avec succès.")
            return redirect('stockapp:finances')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire de dépense.")
    else:
        form = DepenseForm()

    metrics = get_financial_metrics()

    return render(request, 'stockapp/finances.html', {
        'metrics': metrics,
        'form': form,
        'chart_cashflow_labels_json': json.dumps(metrics['chart_cashflow_labels']),
        'chart_cashflow_data_json': json.dumps(metrics['chart_cashflow_data']),
        'chart_depenses_labels_json': json.dumps(metrics['chart_depenses_labels']),
        'chart_depenses_data_json': json.dumps(metrics['chart_depenses_data']),
    })


@login_required
@role_required('Admin', 'Manager')
def depense_supprimer(request, pk):
    """
    Supprime une dépense opérationnelle.
    """
    depense = get_object_or_404(Depense, pk=pk)
    if request.method == 'POST':
        titre = depense.titre
        d_id = depense.id
        montant = depense.montant
        depense.delete()
        JournalAudit.log_action(
            utilisateur=request.user,
            action='SUPPRESSION',
            module='FINANCES',
            objet_concerne=f"Dépense #{d_id} ({titre})",
            description=f"Suppression de la dépense #{d_id} '{titre}' ({montant:.2f} FCFA/€)",
            request=request
        )
        messages.success(request, f"La dépense '{titre}' a été supprimée.")
    return redirect('stockapp:finances')


@login_required
@role_required('Admin', 'Manager')
def finance_report_pdf(request):
    """
    Génération du rapport financier et de trésorerie exécutif en PDF (Phase 7).
    """
    metrics = get_financial_metrics()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='FinanceTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        name='FinanceSubtitle',
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        alignment=1
    )
    h2_style = ParagraphStyle(
        name='FinanceH2',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0891B2'),
        spaceBefore=12,
        spaceAfter=6
    )

    story.append(Paragraph('SMART-TECH — RAPPORT FINANCIER & TRÉSORERIE', title_style))
    story.append(Paragraph(f'Édité le {timezone.now().strftime("%d/%m/%Y à %H:%M")} | Gestion Commerciale Intelligente', subtitle_style))
    story.append(Spacer(1, 16))

    # 1. Compte de Résultat d'Exploitation (P&L)
    story.append(Paragraph('1. Compte de Résultat d\'Exploitation Synthétique', h2_style))
    pl_data = [
        ['Poste Financier', 'Montant (FCFA/€)', 'Commentaire / % CA'],
        ['Chiffre d\'Affaires Net Réalisé', f"{metrics['ca_total_net']:.2f}", '100.0% du CA'],
        ['(-) Coût des Ventes (COGS)', f"{metrics['cogs_total']:.2f}", 'Coût d\'achat des articles vendus'],
        ['(=) Marge Commerciale Brute', f"{metrics['marge_brute']:.2f}", f"Taux brut : {metrics['taux_recouvrement']}%"],
        ['(-) Charges & Dépenses d\'Exploitation', f"{metrics['total_depenses']:.2f}", 'Loyer, salaires, énergie...'],
        ['(=) Résultat Net d\'Exploitation', f"{metrics['resultat_net']:.2f}", f"Rentabilité nette : {metrics['taux_rentabilite_nette']}%"],
    ]
    pl_table = Table(pl_data, colWidths=[220, 130, 190])
    pl_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#ECFDF5')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#065F46')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor('#F0FDF4')),
        ('TEXTCOLOR', (0, 5), (-1, 5), colors.HexColor('#166534')),
        ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
    ]))
    story.append(pl_table)
    story.append(Spacer(1, 14))

    # 2. Bilan de Trésorerie & Liquidités
    story.append(Paragraph('2. Bilan de Trésorerie & Situation de Liquidité', h2_style))
    treso_data = [
        ['Flux Monétaire', 'Montant (FCFA/€)', 'Statut'],
        ['Cash Réel Encaissé (Ventes)', f"{metrics['cash_encaisse']:.2f}", 'Liquidités collectées'],
        ['(-) Règlements Fournisseurs Honorés', f"{metrics['achats_regles']:.2f}", 'Décaissements achats'],
        ['(-) Charges Opérationnelles Payées', f"{metrics['total_depenses']:.2f}", 'Décaissements charges'],
        ['(=) Flux Net de Trésorerie Théorique', f"{metrics['flux_net_cash']:.2f}", 'Solde net de caisse'],
        ['Créances Clients à Recouvrer', f"{metrics['creances_clients']:.2f}", 'Actif circulant à percevoir'],
        ['Dettes Fournisseurs en Cours', f"{metrics['dettes_fournisseurs']:.2f}", 'Passif à court terme'],
        ['(=) Position Nette Globale', f"{metrics['position_nette_globale']:.2f}", 'Solvabilité nette à date'],
    ]
    treso_table = Table(treso_data, colWidths=[220, 130, 190])
    treso_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0891B2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#EFF6FF')),
        ('FONTNAME', (0, 4), (-1, 4), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor('#F8FAFC')),
        ('FONTNAME', (0, 7), (-1, 7), 'Helvetica-Bold'),
    ]))
    story.append(treso_table)

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="rapport_financier_smart_tech_{timezone.now().strftime("%Y%m%d")}.pdf"'
    return response


# ==================== JOURNAL D'AUDIT EXÉCUTIF (PHASE 9) ====================

@login_required
@role_required('Admin')
def journal_audit_view(request):
    """
    Journal d'Audit Centralisé SMART-TECH (Phase 9 - Rôles, Permissions & Audit).
    Restitue l'ensemble des événements système, modifications tarifaires,
    ajustements d'inventaire, suppressions, encaissements et mouvements financiers.
    """
    from django.contrib.auth.models import User

    action_filter = request.GET.get('action', '').strip()
    module_filter = request.GET.get('module', '').strip()
    user_id_filter = request.GET.get('user', '').strip()
    query = request.GET.get('q', '').strip()

    metrics = get_audit_logs_metrics(
        action=action_filter or None,
        module=module_filter or None,
        user_id=user_id_filter or None,
        query=query or None,
        limit=150
    )

    users = User.objects.all().order_by('username')

    return render(request, 'stockapp/journal_audit.html', {
        'logs': metrics['logs'],
        'total_logs': metrics['total_logs'],
        'filtered_count': metrics['filtered_count'],
        'nb_prix_changes': metrics['nb_prix_changes'],
        'nb_suppressions': metrics['nb_suppressions'],
        'nb_ajustements': metrics['nb_ajustements'],
        'nb_users_actifs': metrics['nb_users_actifs'],
        'actions_choices': metrics['actions_choices'],
        'modules_choices': metrics['modules_choices'],
        'users': users,
        'selected_action': action_filter,
        'selected_module': module_filter,
        'selected_user': user_id_filter,
        'selected_query': query,
    })


@login_required
@role_required('Admin')
def journal_audit_export_csv(request):
    """
    Export CSV sécurisé du Journal d'Audit SMART-TECH.
    """
    action_filter = request.GET.get('action', '').strip()
    module_filter = request.GET.get('module', '').strip()
    user_id_filter = request.GET.get('user', '').strip()
    query = request.GET.get('q', '').strip()

    metrics = get_audit_logs_metrics(
        action=action_filter or None,
        module=module_filter or None,
        user_id=user_id_filter or None,
        query=query or None,
        limit=2000
    )

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"journal_audit_smart_tech_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # BOM UTF-8 pour compatibilité Excel
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['ID', 'Date & Heure', 'Utilisateur', 'Action', 'Module', 'Objet Concerné', 'Description', 'Adresse IP'])

    for log in metrics['logs']:
        writer.writerow([
            log.id,
            log.date_creation.strftime('%Y-%m-%d %H:%M:%S'),
            log.utilisateur.username if log.utilisateur else 'Système',
            log.get_action_display(),
            log.get_module_display(),
            log.objet_concerne,
            log.description,
            log.adresse_ip or '-',
        ])

    return response




# ==================== CLÔTURES DE CAISSE & RAPPORTS Z (PHASE 11) ====================

@login_required
@role_required('Admin', 'Manager', 'Caissier')
def clotures_caisse_list_view(request):
    """
    Historique et consultation des Clôtures de Caisse (Rapports Z).
    """
    date_debut_str = request.GET.get('date_debut', '').strip()
    date_fin_str = request.GET.get('date_fin', '').strip()
    caissier_id = request.GET.get('caissier', '').strip()
    statut = request.GET.get('statut', '').strip()

    from datetime import datetime
    date_debut = None
    date_fin = None
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    metrics = get_clotures_caisse_metrics(
        date_debut=date_debut,
        date_fin=date_fin,
        caissier_id=caissier_id or None,
        statut=statut or None
    )

    from django.contrib.auth.models import User
    caissiers = User.objects.filter(clotures_caisse__isnull=False).distinct().order_by('username')
    session_en_cours = get_caisse_session_summary()

    return render(request, 'stockapp/clotures_list.html', {
        'metrics': metrics,
        'clotures': metrics['clotures'],
        'caissiers': caissiers,
        'session_en_cours': session_en_cours,
        'selected_date_debut': date_debut_str,
        'selected_date_fin': date_fin_str,
        'selected_caissier': caissier_id,
        'selected_statut': statut,
    })


@login_required
@role_required('Admin', 'Manager', 'Caissier')
def cloture_caisse_view(request):
    """
    Interface de déclaration et de validation de la Clôture de Caisse (Rapport Z).
    Permet au caissier de compter son tiroir, saisir ses réels et clôturer la session.
    """
    session_summary = get_caisse_session_summary(caissier=request.user)

    if request.method == 'POST':
        form = ClotureCaisseForm(request.POST)
        if form.is_valid():
            fond_initial = form.cleaned_data['fond_de_caisse_initial'] or Decimal('0.00')
            especes_reel = form.cleaned_data['montant_especes_reel'] or Decimal('0.00')
            carte_reel = form.cleaned_data['montant_carte_reel'] or Decimal('0.00')
            momo_reel = form.cleaned_data['montant_mobile_money_reel'] or Decimal('0.00')
            cheque_reel = form.cleaned_data['montant_cheque_reel'] or Decimal('0.00')
            commentaire = form.cleaned_data.get('commentaire', '')

            ref_z = f"Z-{timezone.now().strftime('%Y%m%d-%H%M%S')}"

            # Récupérer les ventes non clôturées
            ventes_a_cloturer = list(session_summary['ventes'])
            date_ouv = session_summary['ventes'].earliest('date_vente').date_vente if session_summary['ventes'].exists() else timezone.now()

            with transaction.atomic():
                cloture = ClotureCaisse(
                    reference=ref_z,
                    caissier=request.user,
                    date_ouverture=date_ouv,
                    date_cloture=timezone.now(),
                    fond_de_caisse_initial=fond_initial,
                    total_especes_theorique=session_summary['total_especes'],
                    total_carte_theorique=session_summary['total_carte'],
                    total_mobile_money_theorique=session_summary['total_mobile_money'],
                    total_cheque_theorique=session_summary['total_cheque'],
                    total_credit_theorique=session_summary['total_credit'],
                    total_ventes_brut=session_summary['total_brut'],
                    total_remises=session_summary['total_remises'],
                    total_ventes_net=session_summary['total_net'],
                    nombre_tickets=session_summary['nb_tickets'],
                    nombre_articles=session_summary['nb_articles'],
                    montant_especes_reel=especes_reel,
                    montant_carte_reel=carte_reel,
                    montant_mobile_money_reel=momo_reel,
                    montant_cheque_reel=cheque_reel,
                    commentaire=commentaire,
                    valide_par=request.user if user_has_role(request.user, 'Admin', 'Manager') else None,
                )
                cloture.save()

                # Rattacher les ventes
                for v in ventes_a_cloturer:
                    v.cloture = cloture
                    v.save(update_fields=['cloture'])

                JournalAudit.log_action(
                    utilisateur=request.user,
                    action='CLOTURE_CAISSE',
                    module='CAISSE',
                    objet_concerne=f"Rapport Z #{cloture.reference}",
                    description=(
                        f"Clôture de session #{cloture.reference} par {request.user.username} : "
                        f"{len(ventes_a_cloturer)} vente(s) ({cloture.nombre_tickets} ticket(s)), "
                        f"CA Net: {cloture.total_ventes_net:.2f} FCFA/€, "
                        f"Écart Total: {cloture.ecart_total:+.2f} FCFA/€ ({cloture.get_statut_conformite_display()})"
                    ),
                    request=request
                )

            messages.success(request, f"✅ Clôture de caisse validée avec succès ! Rapport Z n° {cloture.reference}.")
            return redirect('stockapp:cloture-caisse-detail', pk=cloture.pk)
        else:
            messages.error(request, "Veuillez vérifier les montants saisis.")
    else:
        form = ClotureCaisseForm(initial={
            'fond_de_caisse_initial': Decimal('0.00'),
            'montant_especes_reel': session_summary['total_especes'],
            'montant_carte_reel': session_summary['total_carte'],
            'montant_mobile_money_reel': session_summary['total_mobile_money'],
            'montant_cheque_reel': session_summary['total_cheque'],
        })

    return render(request, 'stockapp/cloture_caisse.html', {
        'session_summary': session_summary,
        'form': form,
    })


@login_required
@role_required('Admin', 'Manager', 'Caissier')
def cloture_caisse_detail_view(request, pk):
    """
    Fiche détaillée d'un Rapport Z de Clôture de Caisse.
    """
    cloture = get_object_or_404(ClotureCaisse.objects.select_related('caissier', 'valide_par'), pk=pk)
    ventes = cloture.ventes.select_related('produit', 'client').order_by('-date_vente')

    return render(request, 'stockapp/cloture_detail.html', {
        'cloture': cloture,
        'ventes': ventes,
    })


@login_required
@role_required('Admin', 'Manager', 'Caissier')
def cloture_caisse_pdf_view(request, pk):
    """
    Génération du document officiel Rapport Z de Clôture de Caisse en PDF A4.
    """
    cloture = get_object_or_404(ClotureCaisse.objects.select_related('caissier', 'valide_par'), pk=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name='ZTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0F172A'),
        alignment=1
    )
    subtitle_style = ParagraphStyle(
        name='ZSubtitle',
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        alignment=1
    )
    h2_style = ParagraphStyle(
        name='ZH2',
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0891B2'),
        spaceBefore=10,
        spaceAfter=6
    )

    story.append(Paragraph(f"SMART-TECH — RAPPORT Z DE CLÔTURE DE CAISSE", title_style))
    story.append(Paragraph(f"Référence officielle : {cloture.reference} | Date : {cloture.date_cloture.strftime('%d/%m/%Y à %H:%M')}", subtitle_style))
    story.append(Spacer(1, 14))

    # Identifiants session
    info_data = [
        ['Caissier / Opérateur', cloture.caissier.get_full_name() or cloture.caissier.username, 'Statut Conformité', cloture.get_statut_conformite_display()],
        ['Date Ouverture', cloture.date_ouverture.strftime('%d/%m/%Y %H:%M'), 'Date Clôture', cloture.date_cloture.strftime('%d/%m/%Y %H:%M')],
        ['Nombre de Tickets', str(cloture.nombre_tickets), "Nombre d'Articles", str(cloture.nombre_articles)],
    ]
    info_table = Table(info_data, colWidths=[140, 130, 140, 130])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0F172A')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 12))

    # 1. Synthèse du Chiffre d'Affaires
    story.append(Paragraph("1. Synthèse Commerciale des Ventes", h2_style))
    sales_data = [
        ['Indicateur Commercial', 'Montant (FCFA/€)', 'Commentaire'],
        ['Total Ventes Brut', f"{cloture.total_ventes_brut:.2f}", f"{cloture.nombre_articles} article(s) vendus"],
        ['(-) Total des Remises Accordées', f"{cloture.total_remises:.2f}", 'Remises commerciales'],
        ["(=) Chiffre d'Affaires Net Réalisé", f"{cloture.total_ventes_net:.2f}", f"{cloture.nombre_tickets} ticket(s) encaissés"],
    ]
    sales_table = Table(sales_data, colWidths=[200, 140, 200])
    sales_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#ECFDF5')),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#065F46')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(sales_table)
    story.append(Spacer(1, 12))

    # 2. Ventilation des Règlements
    story.append(Paragraph("2. Ventilation par Mode de Règlement", h2_style))
    reg_data = [
        ['Mode de Paiement', 'Théorique Attendu', 'Réel Déclaré', 'Écart'],
        ['Espèces (Tiroir-Caisse)', f"{cloture.total_especes_theorique:.2f}", f"{cloture.montant_especes_reel:.2f}", f"{cloture.ecart_especes:+.2f}"],
        ['Carte Bancaire / TPE', f"{cloture.total_carte_theorique:.2f}", f"{cloture.montant_carte_reel:.2f}", f"{cloture.montant_carte_reel - cloture.total_carte_theorique:+.2f}"],
        ['Mobile Money', f"{cloture.total_mobile_money_theorique:.2f}", f"{cloture.montant_mobile_money_reel:.2f}", f"{cloture.montant_mobile_money_reel - cloture.total_mobile_money_theorique:+.2f}"],
        ['Chèque', f"{cloture.total_cheque_theorique:.2f}", f"{cloture.montant_cheque_reel:.2f}", f"{cloture.montant_cheque_reel - cloture.total_cheque_theorique:+.2f}"],
        ['Crédit Client (En-cours)', f"{cloture.total_credit_theorique:.2f}", '-', 'Compte client'],
        ['TOTAL CONSOLIDÉ', f"{cloture.total_ventes_net:.2f}", f"{cloture.total_declare_reel:.2f}", f"{cloture.ecart_total:+.2f}"],
    ]
    reg_table = Table(reg_data, colWidths=[160, 120, 130, 130])
    reg_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0891B2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(reg_table)
    story.append(Spacer(1, 12))

    # 3. Contrôle du Tiroir-Caisse
    story.append(Paragraph("3. Contrôle & Audit du Tiroir-Caisse", h2_style))
    tiroir_data = [
        ['Élément du Tiroir-Caisse', 'Montant (FCFA/€)'],
        ['Fond de Caisse Initial (Ouverture)', f"{cloture.fond_de_caisse_initial:.2f}"],
        ['(+) Ventes en Espèces Encaissées', f"{cloture.total_especes_theorique:.2f}"],
        ['(=) Total Attendu dans le Tiroir', f"{cloture.total_tiroir_theorique:.2f}"],
        ['Espèces Physiquement Comptées', f"{cloture.montant_especes_reel:.2f}"],
        ['Écart Constaté sur Espèces', f"{cloture.ecart_especes:+.2f}"],
        ['Écart Global Consolidé', f"{cloture.ecart_total:+.2f}"],
    ]
    tiroir_table = Table(tiroir_data, colWidths=[340, 200])
    ecart_color = colors.HexColor('#166534') if cloture.ecart_total == Decimal('0.00') else (colors.HexColor('#991B1B') if cloture.ecart_total < Decimal('0.00') else colors.HexColor('#1E40AF'))
    tiroir_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, -1), (1, -1), ecart_color),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(tiroir_table)
    story.append(Spacer(1, 16))

    # Notes / Commentaires
    if cloture.commentaire:
        story.append(Paragraph(f"<b>Notes / Justification :</b> {cloture.commentaire}", styles['BodyText']))
        story.append(Spacer(1, 14))

    # Cadres Signatures
    sig_data = [
        ['Visa & Signature du Caissier', 'Visa & Cachet Responsable / Superviseur'],
        ['\n\n\n_________________________________', '\n\n\n_________________________________'],
    ]
    sig_table = Table(sig_data, colWidths=[270, 270])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#0F172A')),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="rapport_z_{cloture.reference}.pdf"'
    return response


# ==================== HUB DES RAPPORTS & EXPORTS AVANCÉS (PHASE 11) ====================

@login_required
@role_required('Admin', 'Manager')
def rapports_hub_view(request):
    """
    Hub centralisé des rapports d'activité, exports comptables et clôtures Z (Phase 11).
    """
    exp_data = get_comptabilite_export_data()
    clotures_metrics = get_clotures_caisse_metrics()
    derniere_cloture = ClotureCaisse.objects.order_by('-date_cloture').first()

    return render(request, 'stockapp/rapports_hub.html', {
        'exp_data': exp_data,
        'clotures_metrics': clotures_metrics,
        'derniere_cloture': derniere_cloture,
    })


@login_required
@role_required('Admin', 'Manager', 'Magasinier')
def export_stock_valorise_csv(request):
    """
    Export CSV sécurisé de l'inventaire complet valorisé (coûts, prix de vente, marges).
    """
    exp_data = get_comptabilite_export_data()

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"smart_tech_inventaire_valorise_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'Référence', 'SKU', 'Nom du Produit', 'Catégorie', 'Stock Actuel',
        'Seuil Alerte', 'Prix Achat (Coût)', 'Prix Vente Unitaire',
        'Valeur Totale Achat', 'Valeur Totale Vente', 'Marge Potentielle', 'Taux de Marge (%)', 'Statut Stock'
    ])

    for row in exp_data['produits_inventaire']:
        p = row['produit']
        writer.writerow([
            p.reference,
            p.sku or '-',
            p.nom,
            p.categorie.nom if p.categorie else 'Général',
            p.stock_actuel,
            p.seuil_alerte,
            f"{p.prix_achat:.2f}",
            f"{p.prix_unitaire:.2f}",
            f"{row['valeur_achat']:.2f}",
            f"{row['valeur_vente']:.2f}",
            f"{row['marge_potentielle']:.2f}",
            f"{row['taux_marge']}%",
            p.statut_stock,
        ])

    return response


@login_required
@role_required('Admin', 'Manager')
def export_ventes_detaillees_csv(request):
    """
    Export CSV sécurisé du journal des ventes détaillé avec marges unitaires et réelles.
    """
    date_debut_str = request.GET.get('date_debut', '').strip()
    date_fin_str = request.GET.get('date_fin', '').strip()

    from datetime import datetime
    date_debut = None
    date_fin = None
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    exp_data = get_comptabilite_export_data(date_debut=date_debut, date_fin=date_fin)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"smart_tech_journal_ventes_marges_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')

    writer.writerow([
        'Date & Heure', 'Référence Ticket', 'Client', 'Produit', 'Réf Produit',
        'Quantité', 'Prix Vente Unit', 'Montant Brut', 'Remise', 'Net Encaissé',
        'Coût d\'Achat', 'Marge Réalisée', 'Mode de Règlement', 'Réf Clôture Z'
    ])

    for row in exp_data['ventes_detaillees']:
        v = row['vente']
        writer.writerow([
            v.date_vente.strftime('%Y-%m-%d %H:%M:%S'),
            v.reference_ticket or '-',
            v.client.nom if v.client else 'Client Comptoir',
            v.produit.nom,
            v.produit.reference,
            v.quantite,
            f"{v.prix_unitaire:.2f}",
            f"{row['montant_brut']:.2f}",
            f"{v.remise:.2f}",
            f"{row['montant_net']:.2f}",
            f"{row['cout_achat']:.2f}",
            f"{row['marge_realisee']:.2f}",
            v.get_mode_paiement_display(),
            v.cloture.reference if v.cloture else 'Session Ouverte',
        ])

    return response


@login_required
@role_required('Admin', 'Manager')
def export_compte_resultat_csv(request):
    """
    Export CSV sécurisé du compte de résultat d'exploitation synthétique.
    """
    exp_data = get_comptabilite_export_data()

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"smart_tech_compte_resultat_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')

    writer.writerow(['Poste Financier', 'Montant (FCFA/€)', 'Commentaire / Nature'])
    writer.writerow(['Chiffre d\'Affaires Brut', f"{exp_data['total_ca_brut']:.2f}", 'Ventes totales hors remises'])
    writer.writerow(['(-) Remises Accordées', f"{exp_data['total_remises']:.2f}", 'Remises commerciales consenties'])
    writer.writerow(['(=) Chiffre d\'Affaires Net', f"{exp_data['total_ca_net']:.2f}", 'Revenu d\'activité net'])
    writer.writerow(['(-) Coût des Marchandises Vendues (COGS)', f"{exp_data['total_cogs']:.2f}", 'Coût d\'achat des articles vendus'])
    writer.writerow(['(=) Marge Commerciale Brute', f"{exp_data['total_marge_realisee']:.2f}", 'Marge d\'exploitation brute'])
    writer.writerow(['(-) Charges & Dépenses d\'Exploitation', f"{exp_data['total_depenses']:.2f}", 'Loyer, salaires, énergie, télécoms, etc.'])
    writer.writerow(['(=) Résultat Net d\'Exploitation', f"{exp_data['resultat_net']:.2f}", 'Bénéfice net d\'exploitation estimé'])

    return response


# ==================== NOTIFICATIONS PROACTIVES & CENTRE D'ALERTES (PHASE 12) ====================

@login_required
def notifications_hub_view(request):
    """
    Centre de pilotage des alertes et notifications internes SMART-TECH (Phase 12).
    Affiche l'ensemble des alertes métier avec filtres avancés, indicateurs et actions rapides.
    """
    from django.core.paginator import Paginator

    # Déclenche un scan proactif pour s'assurer que les alertes sont à jour
    generer_alertes_proactives()

    statut_filter = request.GET.get('statut', 'non_lues').strip()
    type_filter = request.GET.get('type', '').strip()
    niveau_filter = request.GET.get('niveau', '').strip()
    query = request.GET.get('q', '').strip()

    include_read = (statut_filter in ['toutes', 'lues'])
    include_archived = (statut_filter == 'archivees')

    qs = get_notifications_pour_utilisateur(
        user=request.user,
        include_read=include_read,
        include_archived=include_archived,
        type_filtre=type_filter or None,
        niveau_filtre=niveau_filter or None
    )

    if statut_filter == 'lues':
        qs = qs.filter(est_lue=True, est_archivee=False)

    if query:
        qs = qs.filter(models.Q(titre__icontains=query) | models.Q(message__icontains=query))

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    metrics = get_notifications_metrics(request.user)

    context = {
        'page_obj': page_obj,
        'metrics': metrics,
        'statut_filter': statut_filter,
        'type_filter': type_filter,
        'niveau_filter': niveau_filter,
        'query': query,
    }
    return render(request, 'stockapp/notifications_hub.html', context)


@login_required
def marquer_notification_lue_view(request, pk):
    """
    Marque une notification comme lue.
    Supporte les requêtes AJAX (JSON) ou redirection standard.
    """
    if request.method == 'POST':
        success = marquer_notification_comme_lue(pk, request.user)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', '')
        if is_ajax:
            stats = get_statistiques_notifications(request.user)
            return JsonResponse({'success': success, 'unread_count': stats['non_lues']})
        if success:
            messages.success(request, "Notification marquée comme lue.")
        else:
            messages.error(request, "Notification introuvable.")

    next_url = request.META.get('HTTP_REFERER') or reverse('stockapp:notifications-hub')
    return redirect(next_url)


@login_required
def marquer_toutes_notifications_lues_view(request):
    """
    Marque toutes les notifications non lues comme lues.
    """
    if request.method == 'POST':
        count = marquer_toutes_comme_lues(request.user)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', '')
        if is_ajax:
            return JsonResponse({'success': True, 'count': count})
        messages.success(request, f"{count} notification(s) marquée(s) comme lue(s).")

    next_url = request.META.get('HTTP_REFERER') or reverse('stockapp:notifications-hub')
    return redirect(next_url)


@login_required
def archiver_notification_view(request, pk):
    """
    Archive une notification.
    """
    if request.method == 'POST':
        success = archiver_notification(pk, request.user)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('accept', '')
        if is_ajax:
            return JsonResponse({'success': success})
        if success:
            messages.success(request, "Notification archivée avec succès.")
        else:
            messages.error(request, "Notification introuvable.")

    next_url = request.META.get('HTTP_REFERER') or reverse('stockapp:notifications-hub')
    return redirect(next_url)


@login_required
def rafraichir_alertes_view(request):
    """
    Déclenche manuellement un scan proactif de toutes les alertes métier.
    """
    res = generer_alertes_proactives()
    messages.success(request, f"Actualisation réussie : {res['creations_count']} nouvelle(s) alerte(s) détectée(s).")
    return redirect('stockapp:notifications-hub')


@login_required
def api_unread_notifications_view(request):
    """
    API JSON pour le rafraîchissement dynamique de la cloche et du panneau navbar.
    """
    notifs = get_notifications_pour_utilisateur(
        user=request.user,
        include_read=False,
        include_archived=False
    )
    unread_count = notifs.count()
    critical_count = notifs.filter(niveau='CRITICAL').count()

    recent_qs = get_notifications_pour_utilisateur(
        user=request.user,
        include_read=True,
        include_archived=False,
        limit=5
    )

    recent_list = []
    for n in recent_qs:
        recent_list.append({
            'id': n.id,
            'titre': n.titre,
            'message': n.message[:120] + ('...' if len(n.message) > 120 else ''),
            'type': n.type_notification,
            'niveau': n.niveau,
            'lien': n.lien or '#',
            'est_lue': n.est_lue,
            'date': n.date_creation.strftime('%d/%m %H:%M'),
        })

    return JsonResponse({
        'unread_count': unread_count,
        'critical_count': critical_count,
        'recent': recent_list,
    })


# ==================== SAUVEGARDE, RESTAURATION & SÉCURITÉ (PHASE 13) ====================

@login_required
@role_required('Admin')
def sauvegardes_view(request):
    """
    Centre d'administration des sauvegardes et sécurité des données (Phase 13).
    Accessible exclusivement aux Administrateurs.
    """
    sauvegardes = lister_sauvegardes()
    integrite = verifier_integrite_base()

    context = {
        'sauvegardes': sauvegardes,
        'integrite': integrite,
    }
    return render(request, 'stockapp/sauvegardes.html', context)


@login_required
@role_required('Admin')
def creer_sauvegarde_view(request):
    """
    Déclenche la création d'une nouvelle sauvegarde système complète.
    """
    if request.method == 'POST':
        nom = request.POST.get('nom_personnalise', '').strip()
        inclure_medias = request.POST.get('inclure_medias', 'on') == 'on'

        try:
            res = creer_sauvegarde(
                nom_personnalise=nom or None,
                inclure_medias=inclure_medias,
                utilisateur=request.user,
                request=request
            )
            messages.success(request, f"Sauvegarde {res['nom_fichier']} ({res['taille_formatee']}) créée avec succès !")
        except Exception as e:
            messages.error(request, f"Erreur lors de la sauvegarde : {str(e)}")

    return redirect('stockapp:sauvegardes')


@login_required
@role_required('Admin')
def telecharger_sauvegarde_view(request, filename):
    """
    Téléchargement sécurisé d'une archive de sauvegarde ZIP.
    Protection anti path-traversal stricte.
    """
    if '..' in filename or '/' in filename or '\\' in filename:
        messages.error(request, "Nom de fichier invalide.")
        return redirect('stockapp:sauvegardes')

    backup_dir = get_backup_dir()
    file_path = backup_dir / filename

    if not file_path.exists():
        messages.error(request, "Archive de sauvegarde introuvable.")
        return redirect('stockapp:sauvegardes')

    response = FileResponse(open(file_path, 'rb'), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@role_required('Admin')
def restaurer_sauvegarde_view(request, filename):
    """
    Restaure les données depuis une archive de sauvegarde avec snapshot pré-restauration.
    """
    if request.method == 'POST':
        if '..' in filename or '/' in filename or '\\' in filename:
            messages.error(request, "Nom de fichier invalide.")
            return redirect('stockapp:sauvegardes')

        try:
            res = restaurer_sauvegarde(
                nom_fichier=filename,
                utilisateur=request.user,
                request=request
            )
            messages.success(
                request,
                f"Restauration réussie depuis {filename} ! (Snapshot de secours: {res['snapshot_pre_restauration']})"
            )
        except Exception as e:
            messages.error(request, f"Échec de la restauration : {str(e)}")

    return redirect('stockapp:sauvegardes')


@login_required
@role_required('Admin')
def supprimer_sauvegarde_view(request, filename):
    """
    Supprime définitivement une archive de sauvegarde.
    """
    if request.method == 'POST':
        try:
            success = supprimer_sauvegarde(
                nom_fichier=filename,
                utilisateur=request.user,
                request=request
            )
            if success:
                messages.success(request, f"Archive {filename} supprimée avec succès.")
            else:
                messages.error(request, f"Fichier {filename} introuvable.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la suppression : {str(e)}")

    return redirect('stockapp:sauvegardes')


@login_required
@role_required('Admin')
def purger_logs_audit_view(request):
    """
    Purge les entrées anciennes du journal d'audit.
    """
    if request.method == 'POST':
        try:
            jours = int(request.POST.get('jours', 90))
        except (ValueError, TypeError):
            jours = 90

        nb = purger_anciens_logs_audit(
            jours_retention=jours,
            utilisateur=request.user,
            request=request
        )
        messages.success(request, f"Purge effectuée : {nb} log(s) d'audit de plus de {jours} jours supprimé(s).")

    return redirect('stockapp:sauvegardes')


# ==================== MODULE GESTION DES UTILISATEURS & PROFILS (RBAC) ====================

@login_required
@role_required('Admin')
def utilisateurs_list_view(request):
    """
    Console d'administration centrale des comptes utilisateurs et profils SMART-TECH.
    Permet à l'Administrateur de superviser, filtrer, créer, modifier, réinitialiser
    les mots de passe, activer/désactiver et supprimer des comptes.
    """
    search_query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '').strip()
    statut_filter = request.GET.get('statut', '').strip()

    # S'assurer que les 4 groupes de rôles existent
    for r in [ROLE_ADMIN, ROLE_MANAGER, ROLE_MAGASINIER, ROLE_CAISSIER]:
        Group.objects.get_or_create(name=r)

    users_qs = User.objects.prefetch_related('groups').order_by('-date_joined')

    # Filtrage par recherche
    if search_query:
        users_qs = users_qs.filter(
            models.Q(username__icontains=search_query) |
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(email__icontains=search_query)
        )

    # Filtrage par statut
    if statut_filter == 'actif':
        users_qs = users_qs.filter(is_active=True)
    elif statut_filter == 'inactif':
        users_qs = users_qs.filter(is_active=False)

    all_users = list(users_qs)
    enriched_users = []
    nb_admins = 0
    nb_managers = 0
    nb_magasiniers = 0
    nb_caissiers = 0
    nb_actifs = 0

    for u in all_users:
        code = get_user_role_code(u)
        label = get_user_primary_role(u)
        conf = ROLES_CONFIG.get(code, ROLES_CONFIG[ROLE_ADMIN])

        # Compteurs globaux
        if code == ROLE_ADMIN:
            nb_admins += 1
        elif code == ROLE_MANAGER:
            nb_managers += 1
        elif code == ROLE_MAGASINIER:
            nb_magasiniers += 1
        elif code == ROLE_CAISSIER:
            nb_caissiers += 1

        if u.is_active:
            nb_actifs += 1

        # Filtre de rôle
        if role_filter and code != role_filter:
            continue

        enriched_users.append({
            'user': u,
            'role_code': code,
            'role_label': label,
            'role_config': conf,
            'is_current_user': (u.id == request.user.id),
        })

    create_form = UtilisateurCreateForm()

    return render(request, 'stockapp/utilisateurs.html', {
        'utilisateurs': enriched_users,
        'total_count': len(all_users),
        'nb_admins': nb_admins,
        'nb_managers': nb_managers,
        'nb_magasiniers': nb_magasiniers,
        'nb_caissiers': nb_caissiers,
        'nb_actifs': nb_actifs,
        'selected_search': search_query,
        'selected_role': role_filter,
        'selected_statut': statut_filter,
        'roles_choices': ROLES_CHOICES,
        'roles_config': ROLES_CONFIG,
        'create_form': create_form,
    })


@login_required
@role_required('Admin')
def utilisateur_creer_view(request):
    """
    Création d'un nouveau compte utilisateur avec attribution immédiate de rôle.
    """
    if request.method == 'POST':
        form = UtilisateurCreateForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            password = form.cleaned_data['password']
            is_active = form.cleaned_data['is_active']

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active
            )
            assign_user_role(user, role)

            role_label = ROLES_CONFIG.get(role, {}).get('label', role)
            JournalAudit.log_action(
                utilisateur=request.user,
                action='CREATION',
                module='SECURITE',
                objet_concerne=f"Utilisateur @{username}",
                description=(
                    f"Création du compte '{username}' ({user.get_full_name() or username}) "
                    f"avec le profil {role_label} par l'administrateur {request.user.username}."
                ),
                request=request
            )
            messages.success(request, f"Le compte utilisateur '{username}' ({role_label}) a été créé avec succès.")
            return redirect('stockapp:utilisateurs-list')
        else:
            first_error = next(iter(form.errors.values()))[0] if form.errors else "Erreur de validation"
            messages.error(request, f"Impossible de créer l'utilisateur : {first_error}")

    return redirect('stockapp:utilisateurs-list')


@login_required
@role_required('Admin')
def utilisateur_modifier_view(request, pk):
    """
    Modification d'un utilisateur existant (Informations personnelles, profil/rôle, statut).
    """
    target_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = UtilisateurUpdateForm(request.POST)
        if form.is_valid():
            new_first_name = form.cleaned_data['first_name']
            new_last_name = form.cleaned_data['last_name']
            new_email = form.cleaned_data['email']
            new_role = form.cleaned_data['role']
            new_active = form.cleaned_data['is_active']

            # Garde-fou : Un administrateur ne peut pas se rétrograder ou se désactiver lui-même
            if target_user.id == request.user.id:
                if new_role != ROLE_ADMIN or not new_active:
                    messages.warning(
                        request,
                        "Sécurité : Vous ne pouvez pas modifier votre propre statut administrateur actif."
                    )
                    return redirect('stockapp:utilisateurs-list')

            ancien_role = get_user_primary_role(target_user)
            target_user.first_name = new_first_name
            target_user.last_name = new_last_name
            target_user.email = new_email
            target_user.is_active = new_active
            target_user.save()

            assign_user_role(target_user, new_role)
            nouveau_role = ROLES_CONFIG.get(new_role, {}).get('label', new_role)

            JournalAudit.log_action(
                utilisateur=request.user,
                action='MODIFICATION',
                module='SECURITE',
                objet_concerne=f"Utilisateur @{target_user.username}",
                description=(
                    f"Mise à jour du profil de @{target_user.username} : Rôle '{ancien_role}' -> '{nouveau_role}', "
                    f"Statut {'Actif' if new_active else 'Désactivé'}."
                ),
                request=request
            )
            messages.success(request, f"Le profil de l'utilisateur '{target_user.username}' a été mis à jour.")
        else:
            first_error = next(iter(form.errors.values()))[0] if form.errors else "Erreur de validation"
            messages.error(request, f"Erreur de modification : {first_error}")

    return redirect('stockapp:utilisateurs-list')


@login_required
@role_required('Admin')
def utilisateur_reinitialiser_mdp_view(request, pk):
    """
    Réinitialisation administrative du mot de passe d'un utilisateur.
    """
    target_user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = UtilisateurPasswordResetForm(request.POST)
        if form.is_valid():
            new_pass = form.cleaned_data['new_password']
            target_user.set_password(new_pass)
            target_user.save()

            JournalAudit.log_action(
                utilisateur=request.user,
                action='MODIFICATION',
                module='SECURITE',
                objet_concerne=f"Utilisateur @{target_user.username}",
                description=f"Réinitialisation administrative du mot de passe de @{target_user.username} par {request.user.username}.",
                request=request
            )
            messages.success(
                request,
                f"Le mot de passe de l'utilisateur '{target_user.username}' a été réinitialisé avec succès."
            )
        else:
            first_error = next(iter(form.errors.values()))[0] if form.errors else "Erreur"
            messages.error(request, f"Échec de réinitialisation du mot de passe : {first_error}")

    return redirect('stockapp:utilisateurs-list')


@login_required
@role_required('Admin')
def utilisateur_basculer_statut_view(request, pk):
    """
    Active ou désactive un compte utilisateur en 1 clic (sans effacer son historique).
    """
    target_user = get_object_or_404(User, pk=pk)

    if target_user.id == request.user.id:
        messages.warning(request, "Sécurité : Vous ne pouvez pas désactiver votre propre compte actif.")
        return redirect('stockapp:utilisateurs-list')

    if request.method == 'POST':
        target_user.is_active = not target_user.is_active
        target_user.save(update_fields=['is_active'])

        etat = "activé" if target_user.is_active else "suspendu / désactivé"
        JournalAudit.log_action(
            utilisateur=request.user,
            action='MODIFICATION',
            module='SECURITE',
            objet_concerne=f"Utilisateur @{target_user.username}",
            description=f"Compte de @{target_user.username} {etat} par l'administrateur {request.user.username}.",
            request=request
        )
        messages.success(request, f"Le compte '{target_user.username}' a été {etat}.")

    return redirect('stockapp:utilisateurs-list')


@login_required
@role_required('Admin')
def utilisateur_supprimer_view(request, pk):
    """
    Suppression définitive et sécurisée d'un compte utilisateur.
    Permet à l'administrateur de purger ou de recréer un profil.
    """
    target_user = get_object_or_404(User, pk=pk)

    # Garde-fou 1 : Pas d'auto-suppression
    if target_user.id == request.user.id:
        messages.error(request, "Action interdite : Vous ne pouvez pas supprimer votre propre compte actuellement connecté.")
        return redirect('stockapp:utilisateurs-list')

    # Garde-fou 2 : Empêcher la suppression du dernier administrateur
    if target_user.is_superuser or target_user.groups.filter(name=ROLE_ADMIN).exists():
        admin_count = User.objects.filter(models.Q(is_superuser=True) | models.Q(groups__name=ROLE_ADMIN)).distinct().count()
        if admin_count <= 1:
            messages.error(request, "Action interdite : Impossible de supprimer l'unique administrateur restant du système.")
            return redirect('stockapp:utilisateurs-list')

    if request.method == 'POST':
        uname = target_user.username
        role_label = get_user_primary_role(target_user)
        target_user.delete()

        JournalAudit.log_action(
            utilisateur=request.user,
            action='SUPPRESSION',
            module='SECURITE',
            objet_concerne=f"Utilisateur @{uname}",
            description=f"Suppression définitive du compte @{uname} (Profil: {role_label}) par {request.user.username}.",
            request=request
        )
        messages.success(request, f"L'utilisateur '{uname}' a été supprimé définitivement. Vous pouvez recréer un profil si souhaité.")

    return redirect('stockapp:utilisateurs-list')



