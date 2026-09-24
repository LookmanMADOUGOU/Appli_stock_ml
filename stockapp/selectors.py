"""
Module des Selectors pour SMART-TECH.
Centralise toutes les requêtes complexes, agrégations SQL et calculs d'indicateurs de décision.
"""

from decimal import Decimal
from datetime import timedelta
from django.db.models import Sum, F, Count, Q, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncDate
from django.utils import timezone
from .models import Produit, Vente, MouvementStock, AlerteRupture, Client, Fournisseur, Categorie, Depense, Approvisionnement, JournalAudit, ClotureCaisse, Notification
from .services.prediction_service import (
    get_sales_trend,
    predict_stockout_ml,
    get_demand_forecast,
    calculate_reorder_point_and_safety_stock,
    get_product_time_series_data,
)


def get_dashboard_metrics() -> dict:
    """
    Centre de pilotage exécutif SMART-TECH (Phase 5).
    Optimisé via des agrégations SQL natives pures, éliminant les boucles N+1
    et fournissant les comparaisons périodiques (Jour J vs J-1, Mois M vs M-1, etc.).
    """
    now = timezone.now()
    today = now.date()

    # 1. Agrégations SQL sur les Produits et le Stock (1 seule requête)
    produits_agg = Produit.objects.aggregate(
        total_count=Count('id'),
        stock_total=Sum('stock_actuel'),
        valeur_stock_achat=Sum(
            ExpressionWrapper(F('stock_actuel') * F('prix_achat'), output_field=DecimalField(max_digits=14, decimal_places=2))
        ),
        valeur_stock_vente=Sum(
            ExpressionWrapper(F('stock_actuel') * F('prix_unitaire'), output_field=DecimalField(max_digits=14, decimal_places=2))
        ),
        produits_rupture=Count('id', filter=Q(stock_actuel__lte=0)),
        produits_faible=Count('id', filter=Q(stock_actuel__gt=0, stock_actuel__lte=F('seuil_alerte'))),
        produits_surstock=Count('id', filter=Q(stock_actuel__gte=F('stock_maximum'))),
        produits_normal=Count('id', filter=Q(stock_actuel__gt=F('seuil_alerte'), stock_actuel__lt=F('stock_maximum'))),
    )

    produits_count = produits_agg['total_count'] or 0
    stock_total = produits_agg['stock_total'] or 0
    valeur_stock_achat = produits_agg['valeur_stock_achat'] or Decimal('0.00')
    valeur_stock_vente = produits_agg['valeur_stock_vente'] or Decimal('0.00')
    marge_estimee_stock = valeur_stock_vente - valeur_stock_achat

    produits_en_rupture_count = (produits_agg['produits_rupture'] or 0) + (produits_agg['produits_faible'] or 0)
    rupture_rate = round((produits_en_rupture_count / produits_count) * 100, 1) if produits_count else 0.0

    # 2. Agrégations Globales SQL sur les Ventes (1 seule requête)
    ventes_agg = Vente.objects.aggregate(
        total_ventes=Sum('quantite'),
        chiffre_affaires_total=Sum(
            ExpressionWrapper(F('quantite') * F('prix_unitaire') - F('remise'), output_field=DecimalField(max_digits=14, decimal_places=2))
        ),
        benefice_net_total=Sum(
            ExpressionWrapper(
                (F('quantite') * F('prix_unitaire') - F('remise')) - (F('quantite') * F('prix_achat')),
                output_field=DecimalField(max_digits=14, decimal_places=2)
            )
        ),
    )
    chiffre_affaires_total = ventes_agg['chiffre_affaires_total'] or Decimal('0.00')
    benefice_net_total = ventes_agg['benefice_net_total'] or Decimal('0.00')

    # 3. Créances et Dettes Partenaires (2 requêtes SQL légères)
    creances_clients = Client.objects.aggregate(tot=Sum('solde_credit'))['tot'] or Decimal('0.00')
    dettes_fournisseurs = Fournisseur.objects.aggregate(tot=Sum('dette_fournisseur'))['tot'] or Decimal('0.00')

    # 4. Comparaisons Périodiques Dynamiques (Section 11)
    # Jour : Aujourd'hui vs Hier
    hier = today - timedelta(days=1)
    ventes_jour_agg = Vente.objects.filter(date_vente__date=today).aggregate(
        ca=Sum(F('quantite') * F('prix_unitaire') - F('remise')),
        benef=Sum((F('quantite') * F('prix_unitaire') - F('remise')) - (F('quantite') * F('prix_achat'))),
        volume=Sum('quantite')
    )
    ventes_hier_agg = Vente.objects.filter(date_vente__date=hier).aggregate(
        ca=Sum(F('quantite') * F('prix_unitaire') - F('remise'))
    )
    ca_jour = ventes_jour_agg['ca'] or Decimal('0.00')
    benef_jour = ventes_jour_agg['benef'] or Decimal('0.00')
    ca_hier = ventes_hier_agg['ca'] or Decimal('0.00')

    if ca_hier > 0:
        evolution_jour_pct = round(float((ca_jour - ca_hier) / ca_hier) * 100, 1)
    else:
        evolution_jour_pct = 100.0 if ca_jour > 0 else 0.0

    # Mois : Ce Mois (M) vs Mois Précédent (M-1)
    premier_jour_mois = today.replace(day=1)
    dernier_jour_mois_prec = premier_jour_mois - timedelta(days=1)
    premier_jour_mois_prec = dernier_jour_mois_prec.replace(day=1)

    ventes_mois_agg = Vente.objects.filter(date_vente__date__gte=premier_jour_mois).aggregate(
        ca=Sum(F('quantite') * F('prix_unitaire') - F('remise')),
        benef=Sum((F('quantite') * F('prix_unitaire') - F('remise')) - (F('quantite') * F('prix_achat')))
    )
    ventes_mois_prec_agg = Vente.objects.filter(
        date_vente__date__gte=premier_jour_mois_prec,
        date_vente__date__lte=dernier_jour_mois_prec
    ).aggregate(
        ca=Sum(F('quantite') * F('prix_unitaire') - F('remise'))
    )
    ca_mois = ventes_mois_agg['ca'] or Decimal('0.00')
    benef_mois = ventes_mois_agg['benef'] or Decimal('0.00')
    ca_mois_prec = ventes_mois_prec_agg['ca'] or Decimal('0.00')

    if ca_mois_prec > 0:
        evolution_mois_pct = round(float((ca_mois - ca_mois_prec) / ca_mois_prec) * 100, 1)
    else:
        evolution_mois_pct = 100.0 if ca_mois > 0 else 0.0

    # 5. Série temporelle des 14 derniers jours via 1 SEULE requête SQL avec TruncDate
    start_14 = today - timedelta(days=13)
    sales_by_day = (
        Vente.objects.filter(date_vente__date__gte=start_14)
        .annotate(day=TruncDate('date_vente'))
        .values('day')
        .annotate(ca=Sum(F('quantite') * F('prix_unitaire') - F('remise')))
        .order_by('day')
    )
    sales_map = {row['day']: float(row['ca'] or 0) for row in sales_by_day}

    days_14_list = [start_14 + timedelta(days=i) for i in range(14)]
    chart_dates = [d.strftime('%d/%m') for d in days_14_list]
    chart_sales_values = [sales_map.get(d, 0.0) for d in days_14_list]

    # 6. Top Produits, Alertes actives, Ventes et Mouvements récents
    top_produits_ventes = (
        Vente.objects
        .values('produit__id', 'produit__nom')
        .annotate(total_ventes=Sum('quantite'))
        .order_by('-total_ventes')[:5]
    )
    ventes_recentes = Vente.objects.select_related('produit', 'client').order_by('-date_vente')[:8]
    mouvements_recents = MouvementStock.objects.select_related('produit', 'utilisateur').order_by('-date_mouvement')[:8]
    alertes_actives = AlerteRupture.objects.filter(est_resolue=False).select_related('produit')[:10]
    alertes_actives_count = AlerteRupture.objects.filter(est_resolue=False).count()

    return {
        # Métriques Stock
        'total_produits': produits_count,
        'stock_total': stock_total,
        'valeur_stock_achat': valeur_stock_achat,
        'valeur_stock_vente': valeur_stock_vente,
        'marge_estimee_stock': marge_estimee_stock,
        'produits_en_rupture': produits_en_rupture_count,
        'rupture_rate': rupture_rate,
        'nb_rupture_stricte': produits_agg['produits_rupture'] or 0,
        'nb_stock_faible': produits_agg['produits_faible'] or 0,
        'nb_surstock': produits_agg['produits_surstock'] or 0,
        'nb_stock_normal': produits_agg['produits_normal'] or 0,
        # Métriques Financières Globales
        'chiffre_affaires_total': chiffre_affaires_total,
        'benefice_net_total': benefice_net_total,
        'creances_clients': creances_clients,
        'dettes_fournisseurs': dettes_fournisseurs,
        # Métriques Périodiques & Évolution
        'ca_jour': ca_jour,
        'benef_jour': benef_jour,
        'ca_hier': ca_hier,
        'evolution_jour_pct': evolution_jour_pct,
        'ca_mois': ca_mois,
        'benef_mois': benef_mois,
        'ca_mois_prec': ca_mois_prec,
        'evolution_mois_pct': evolution_mois_pct,
        # Graphiques & Tables
        'chart_dates': chart_dates,
        'chart_sales_values': chart_sales_values,
        'top_produits_ventes': top_produits_ventes,
        'ventes_recentes': ventes_recentes,
        'mouvements_recents': mouvements_recents,
        'alertes_actives': alertes_actives,
        'alertes_actives_count': alertes_actives_count,
    }


def get_decision_support_metrics(categorie_id: str = None, query: str = None) -> list:
    """
    Génère l'analyse d'aide à la décision par produit (Section 15 / Phase 8 - Intelligence Commerciale) :
    - Stock actuel & seuils
    - Consommation moyenne journalière
    - Stock de Sécurité calculé & Point de Commande Optimal (ROP)
    - Jours restants estimés avant rupture
    - Diagnostic de Risque et Dynamique de vente (accélération, ralentissement, dormant)
    - Recommandation d'action claire & Pédagogie de décision ("Pourquoi commander ?")
    - Quantité et Budget estimé de réapprovisionnement
    """
    qs = Produit.objects.select_related('categorie').all()

    if query:
        qs = qs.filter(Q(nom__icontains=query) | Q(reference__icontains=query) | Q(sku__icontains=query))
    if categorie_id:
        qs = qs.filter(categorie_id=categorie_id)

    results = []
    for produit in qs:
        intel = calculate_reorder_point_and_safety_stock(produit, lead_time_days=5, service_level_z=1.65, lookback_days=30)

        results.append({
            'produit': produit,
            'stock_actuel': produit.stock_actuel,
            'seuil_alerte': produit.seuil_alerte,
            'stock_maximum': produit.stock_maximum,
            'conso_moyenne': intel['conso_moyenne'],
            'tendance': intel['dynamique'],
            'stockout_days': intel['jours_rupture_estimes'],
            'niveau_risque': intel['statut_code'],
            'label_risque': intel['statut_label'],
            'badge_color': intel['badge_color'],
            'recommandation': intel['explication'],
            'action_requise': intel['action_requise'],
            # Enrichissements Phase 8
            'safety_stock': intel['safety_stock'],
            'rop': intel['rop'],
            'lead_time_days': intel['lead_time_days'],
            'is_dormant': intel['is_dormant'],
            'qte_recommandee': intel['qte_recommandee'],
            'budget_estime': intel['budget_estime'],
            'prix_achat': intel['prix_achat'],
        })

    # Trier les produits par niveau d'urgence (CRITIQUE en premier)
    ordre_priorite = {'CRITIQUE': 1, 'ELEVE': 2, 'DORMANT': 3, 'MODERE': 4, 'SURSTOCK': 5, 'FAIBLE': 6}
    results.sort(key=lambda x: ordre_priorite.get(x['niveau_risque'], 99))
    return results


def get_advanced_analytics_metrics() -> dict:
    """
    Module Analytics Avancé & Performance Financière (Phase 6).
    Fournit une analyse multidimensionnelle des ventes :
    1. Performance Financière Globale :
       - CA net global (après déduction des remises)
       - COGS (Coût d'achat global des articles vendus)
       - Marge brute réelle et Taux de marge moyen (%)
       - Volume total d'articles vendus
       - Nombre de transactions / tickets uniques et Panier Moyen
    2. Performance par Catégorie de Produits :
       - CA net, COGS, Bénéfice net, Taux de marge (%), Volume, Part de marché (%)
    3. Matrice de Rentabilité Produits (BCG SMART-TECH) :
       - Catégorisation intelligente de chaque produit vendu :
         * STAR (⭐) : Volume élevé ET Marge % supérieure à la moyenne
         * VACHE À LAIT (🐄) : Volume élevé, Marge % inférieure à la moyenne (générateur de cash)
         * À FORT POTENTIEL (🚀) : Faible volume mais Marge % très attractive
         * DORMANT / POIDS MORT (💤) : Faible volume ET marge faible
    4. Répartition des Modes de Paiement :
       - Montant total encaissé/à crédit, nombre de transactions, part (%) dans le CA global
    5. Données sérialisables JSON pour graphiques Chart.js (Doughnut catégories, Bars modes de paiement)
    """
    # 1. Base Queryset annoté au niveau ligne pour éviter les conflits d'agrégats dans les GROUP BY
    base_ventes = Vente.objects.annotate(
        row_ca=ExpressionWrapper(F('quantite') * F('prix_unitaire') - F('remise'), output_field=DecimalField(max_digits=14, decimal_places=2)),
        row_cogs=ExpressionWrapper(F('quantite') * F('prix_achat'), output_field=DecimalField(max_digits=14, decimal_places=2)),
        row_benef=ExpressionWrapper((F('quantite') * F('prix_unitaire') - F('remise')) - (F('quantite') * F('prix_achat')), output_field=DecimalField(max_digits=14, decimal_places=2))
    )

    global_agg = base_ventes.aggregate(
        total_ca=Sum('row_ca'),
        total_cogs=Sum('row_cogs'),
        total_benefice=Sum('row_benef'),
        total_volume=Sum('quantite'),
        total_lignes=Count('id')
    )

    ca_global = global_agg['total_ca'] or Decimal('0.00')
    cogs_global = global_agg['total_cogs'] or Decimal('0.00')
    benefice_global = global_agg['total_benefice'] or Decimal('0.00')
    volume_global = global_agg['total_volume'] or 0
    total_lignes = global_agg['total_lignes'] or 0

    taux_marge_global = round(float(benefice_global / ca_global * 100), 2) if ca_global > 0 else 0.0

    # Nombre de tickets uniques (paniers)
    nb_tickets = Vente.objects.exclude(reference_ticket__isnull=True).exclude(reference_ticket='').values('reference_ticket').distinct().count()
    if nb_tickets == 0 and total_lignes > 0:
        nb_tickets = total_lignes
    panier_moyen = round(float(ca_global) / nb_tickets, 2) if nb_tickets > 0 and ca_global > 0 else 0.0
    articles_par_panier = round(float(volume_global) / nb_tickets, 1) if nb_tickets > 0 and volume_global > 0 else 0.0

    # 2. Performance par Catégorie
    cat_rows = (
        base_ventes
        .values('produit__categorie__id', 'produit__categorie__nom')
        .annotate(
            quantite=Sum('quantite'),
            ca=Sum('row_ca'),
            cogs=Sum('row_cogs'),
            benefice=Sum('row_benef')
        )
        .order_by('-ca')
    )
    cat_summary = []
    for r in cat_rows:
        ca_cat = r['ca'] or Decimal('0.00')
        benef_cat = r['benefice'] or Decimal('0.00')
        cogs_cat = r['cogs'] or Decimal('0.00')
        qte_cat = r['quantite'] or 0
        marge_pct = round(float(benef_cat / ca_cat * 100), 2) if ca_cat > 0 else 0.0
        part_ca_pct = round(float(ca_cat / ca_global * 100), 1) if ca_global > 0 else 0.0

        cat_summary.append({
            'id': r['produit__categorie__id'],
            'nom': r['produit__categorie__nom'] or 'Général / Sans catégorie',
            'quantite': qte_cat,
            'chiffre_affaires': ca_cat,
            'cogs': cogs_cat,
            'benefice': benef_cat,
            'marge_pct': marge_pct,
            'part_ca_pct': part_ca_pct,
        })

    # 3. Matrice de Rentabilité Produits (BCG SMART-TECH)
    prod_rows = (
        base_ventes
        .values('produit__id', 'produit__nom', 'produit__reference', 'produit__categorie__nom', 'produit__stock_actuel')
        .annotate(
            quantite=Sum('quantite'),
            ca=Sum('row_ca'),
            benefice=Sum('row_benef')
        )
        .order_by('-ca')
    )

    prod_summary = []
    total_prod_qte = sum(r['quantite'] or 0 for r in prod_rows)
    avg_qte = (total_prod_qte / len(prod_rows)) if prod_rows else 0
    seuil_marge_ref = taux_marge_global if taux_marge_global > 0 else 25.0

    nb_stars = 0
    nb_cash_cows = 0
    nb_potentials = 0
    nb_dormants = 0

    for r in prod_rows:
        ca_p = r['ca'] or Decimal('0.00')
        benef_p = r['benefice'] or Decimal('0.00')
        qte_p = r['quantite'] or 0
        marge_pct_p = round(float(benef_p / ca_p * 100), 1) if ca_p > 0 else 0.0

        est_fort_volume = qte_p >= avg_qte
        est_forte_marge = marge_pct_p >= seuil_marge_ref

        if est_fort_volume and est_forte_marge:
            matrice_cat = 'STAR'
            matrice_label = 'Produit Star'
            matrice_badge = 'bg-amber-100 text-amber-800 border border-amber-300'
            matrice_icon = 'fas fa-star text-amber-500'
            matrice_desc = 'Fort volume & forte rentabilité'
            nb_stars += 1
        elif est_fort_volume and not est_forte_marge:
            matrice_cat = 'CASH_COW'
            matrice_label = 'Vache à Lait'
            matrice_badge = 'bg-emerald-100 text-emerald-800 border border-emerald-300'
            matrice_icon = 'fas fa-money-bill-wave text-emerald-600'
            matrice_desc = 'Fort volume régulier, marge modérée'
            nb_cash_cows += 1
        elif not est_fort_volume and est_forte_marge:
            matrice_cat = 'POTENTIAL'
            matrice_label = 'Fort Potentiel'
            matrice_badge = 'bg-cyan-100 text-cyan-800 border border-cyan-300'
            matrice_icon = 'fas fa-rocket text-cyan-600'
            matrice_desc = 'Marge unitaire élevée, volume à accélérer'
            nb_potentials += 1
        else:
            matrice_cat = 'DORMANT'
            matrice_label = 'Dormant'
            matrice_badge = 'bg-slate-100 text-slate-700 border border-slate-300'
            matrice_icon = 'fas fa-bed text-slate-400'
            matrice_desc = 'Faible volume et rentabilité basse'
            nb_dormants += 1

        prod_summary.append({
            'produit_id': r['produit__id'],
            'nom': r['produit__nom'],
            'reference': r['produit__reference'],
            'categorie': r['produit__categorie__nom'] or 'Général',
            'stock_actuel': r['produit__stock_actuel'],
            'quantite': qte_p,
            'ca': ca_p,
            'benefice': benef_p,
            'marge_pct': marge_pct_p,
            'matrice_cat': matrice_cat,
            'matrice_label': matrice_label,
            'matrice_badge': matrice_badge,
            'matrice_icon': matrice_icon,
            'matrice_desc': matrice_desc,
        })

    # Articles jamais vendus
    articles_jamais_vendus = Produit.objects.exclude(id__in=Vente.objects.values_list('produit_id', flat=True)).count()

    # 4. Répartition des Modes de Paiement
    modes_dict = dict(Vente.MODE_PAIEMENT_CHOICES)
    modes_rows = (
        base_ventes
        .values('mode_paiement')
        .annotate(
            quantite=Sum('quantite'),
            ca=Sum('row_ca'),
            nb_trans=Count('id')
        )
        .order_by('-ca')
    )
    modes_summary = []
    for r in modes_rows:
        ca_m = r['ca'] or Decimal('0.00')
        part_m = round(float(ca_m / ca_global * 100), 1) if ca_global > 0 else 0.0
        mode_code = r['mode_paiement'] or 'ESPECES'
        modes_summary.append({
            'mode_code': mode_code,
            'mode_label': modes_dict.get(mode_code, mode_code),
            'total_ca': ca_m,
            'total_ventes': r['quantite'] or 0,
            'nb_transactions': r['nb_trans'] or 0,
            'part_pct': part_m,
        })

    # 5. Données pour graphiques Chart.js
    chart_cat_labels = [c['nom'] for c in cat_summary[:8]]
    chart_cat_ca = [float(c['chiffre_affaires']) for c in cat_summary[:8]]
    chart_cat_benef = [float(c['benefice']) for c in cat_summary[:8]]

    chart_modes_labels = [m['mode_label'] for m in modes_summary]
    chart_modes_ca = [float(m['total_ca']) for m in modes_summary]

    return {
        'ca_global': ca_global,
        'cogs_global': cogs_global,
        'benefice_global': benefice_global,
        'volume_global': volume_global,
        'taux_marge_global': taux_marge_global,
        'nb_tickets': nb_tickets,
        'panier_moyen': panier_moyen,
        'articles_par_panier': articles_par_panier,
        'cat_summary': cat_summary,
        'prod_summary': prod_summary,
        'modes_summary': modes_summary,
        'articles_jamais_vendus': articles_jamais_vendus,
        'counts_matrice': {
            'stars': nb_stars,
            'cash_cows': nb_cash_cows,
            'potentials': nb_potentials,
            'dormants': nb_dormants,
        },
        'chart_cat_labels': chart_cat_labels,
        'chart_cat_ca': chart_cat_ca,
        'chart_cat_benef': chart_cat_benef,
        'chart_modes_labels': chart_modes_labels,
        'chart_modes_ca': chart_modes_ca,
    }


def get_financial_metrics(period_days: int = None) -> dict:
    """
    Module Financier & Trésorerie (Phase 7).
    Fournit un bilan financier complet et un audit de trésorerie :
    1. Recettes & Encaissements :
       - CA Total Net
       - Cash réel encaissé (Espèces, Carte, Mobile Money, Chèque)
       - Ventes à crédit (Crédit / Avoir)
       - Solde total des créances clients en cours
       - Taux de recouvrement du CA (%)
    2. Achats & Fournisseurs :
       - Total des achats/approvisionnements réceptionnés
       - Dettes fournisseurs en cours à régler
       - Achats déjà réglés
    3. Charges & Dépenses d'Exploitation (OPEX) :
       - Total des charges opérationnelles (loyer, salaires, énergie...)
       - Répartition des dépenses par catégorie
       - Liste des dépenses récentes
    4. Compte de Résultat d'Exploitation Simplifié (P&L) :
       - CA Net Réalisé
       - (-) Coût des Marchandises Vendues (COGS)
       - (=) Marge Commerciale Brute
       - (-) Charges d'Exploitation (OPEX)
       - (=) Résultat Net d'Exploitation
       - Taux de Rentabilité Nette (%)
    5. Bilan de Trésorerie & Solvabilité Globale :
       - Trésorerie Nette Disponible Théorique = Cash Ventes Encaissé - Achats Réglés - Dépenses
       - Position Globale Nette = Cash Encaissé + Créances Clients - Dettes Fournisseurs - Total Dépenses
    6. Données sérialisables Chart.js (Flux de trésorerie, Répartition des Dépenses)
    """
    base_ventes = Vente.objects.annotate(
        row_ca=ExpressionWrapper(F('quantite') * F('prix_unitaire') - F('remise'), output_field=DecimalField(max_digits=14, decimal_places=2)),
        row_cogs=ExpressionWrapper(F('quantite') * F('prix_achat'), output_field=DecimalField(max_digits=14, decimal_places=2)),
        row_benef=ExpressionWrapper((F('quantite') * F('prix_unitaire') - F('remise')) - (F('quantite') * F('prix_achat')), output_field=DecimalField(max_digits=14, decimal_places=2))
    )

    # 1. Recettes et Ventes
    global_ventes = base_ventes.aggregate(
        ca_total=Sum('row_ca'),
        cogs_total=Sum('row_cogs'),
        benefice_brut=Sum('row_benef'),
        volume_total=Sum('quantite')
    )
    ca_total_net = global_ventes['ca_total'] or Decimal('0.00')
    cogs_total = global_ventes['cogs_total'] or Decimal('0.00')
    marge_brute = global_ventes['benefice_brut'] or Decimal('0.00')

    # Cash encaissé vs Ventes à crédit
    cash_encaisse_agg = base_ventes.exclude(mode_paiement='CREDIT').aggregate(tot=Sum('row_ca'))
    cash_encaisse = cash_encaisse_agg['tot'] or Decimal('0.00')

    ventes_credit_agg = base_ventes.filter(mode_paiement='CREDIT').aggregate(tot=Sum('row_ca'))
    ventes_credit = ventes_credit_agg['tot'] or Decimal('0.00')

    creances_clients = Client.objects.aggregate(tot=Sum('solde_credit'))['tot'] or Decimal('0.00')
    taux_recouvrement = round(float(cash_encaisse / ca_total_net * 100), 1) if ca_total_net > 0 else 0.0

    # 2. Achats & Fournisseurs
    all_appros = Approvisionnement.objects.filter(statut='RECU')
    total_achats = sum(a.cout_total for a in all_appros) or Decimal('0.00')
    dettes_fournisseurs = Fournisseur.objects.aggregate(tot=Sum('dette_fournisseur'))['tot'] or Decimal('0.00')
    achats_regles = max(total_achats - dettes_fournisseurs, Decimal('0.00'))

    # 3. Charges & Dépenses d'Exploitation (OPEX)
    total_depenses = Depense.objects.aggregate(tot=Sum('montant'))['tot'] or Decimal('0.00')

    depenses_cat_dict = dict(Depense.CATEGORIE_DEPENSE_CHOICES)
    depenses_par_cat_rows = (
        Depense.objects
        .values('categorie')
        .annotate(tot=Sum('montant'), count=Count('id'))
        .order_by('-tot')
    )
    depenses_par_categorie = []
    for r in depenses_par_cat_rows:
        m = r['tot'] or Decimal('0.00')
        pct = round(float(m / total_depenses * 100), 1) if total_depenses > 0 else 0.0
        code = r['categorie']
        depenses_par_categorie.append({
            'code': code,
            'nom': depenses_cat_dict.get(code, code),
            'montant': m,
            'count': r['count'] or 0,
            'part_pct': pct,
        })

    depenses_recentes = Depense.objects.select_related('utilisateur').order_by('-date_depense', '-date_creation')[:10]

    # 4. Compte de Résultat d'Exploitation (P&L)
    resultat_net = marge_brute - total_depenses
    taux_rentabilite_nette = round(float(resultat_net / ca_total_net * 100), 1) if ca_total_net > 0 else 0.0

    # 5. Situation de Trésorerie & Liquidité
    total_cash_in = cash_encaisse
    total_cash_out = achats_regles + total_depenses
    flux_net_cash = total_cash_in - total_cash_out
    tresorerie_theorique_cash = flux_net_cash
    position_nette_globale = (cash_encaisse + creances_clients) - (dettes_fournisseurs + total_depenses)

    # 6. Séries Chart.js
    chart_cashflow_labels = ['Cash In (Ventes)', 'Achats Réglés', 'Charges d\'Exploitation', 'Flux Net Trésorerie']
    chart_cashflow_data = [
        float(cash_encaisse),
        float(achats_regles),
        float(total_depenses),
        float(flux_net_cash)
    ]

    chart_depenses_labels = [d['nom'] for d in depenses_par_categorie[:6]]
    chart_depenses_data = [float(d['montant']) for d in depenses_par_categorie[:6]]

    return {
        # Recettes
        'ca_total_net': ca_total_net,
        'cogs_total': cogs_total,
        'marge_brute': marge_brute,
        'cash_encaisse': cash_encaisse,
        'ventes_credit': ventes_credit,
        'creances_clients': creances_clients,
        'taux_recouvrement': taux_recouvrement,
        # Achats
        'total_achats': total_achats,
        'dettes_fournisseurs': dettes_fournisseurs,
        'achats_regles': achats_regles,
        # Dépenses
        'total_depenses': total_depenses,
        'depenses_par_categorie': depenses_par_categorie,
        'depenses_recentes': depenses_recentes,
        # P&L
        'resultat_net': resultat_net,
        'taux_rentabilite_nette': taux_rentabilite_nette,
        # Trésorerie
        'total_cash_in': total_cash_in,
        'total_cash_out': total_cash_out,
        'flux_net_cash': flux_net_cash,
        'tresorerie_theorique_cash': tresorerie_theorique_cash,
        'position_nette_globale': position_nette_globale,
        # Graphiques
        'chart_cashflow_labels': chart_cashflow_labels,
        'chart_cashflow_data': chart_cashflow_data,
        'chart_depenses_labels': chart_depenses_labels,
        'chart_depenses_data': chart_depenses_data,
    }


def get_audit_logs_metrics(action: str = None, module: str = None, user_id: str = None, query: str = None, limit: int = 150) -> dict:
    """
    Module Journal d'Audit Exécutif (Phase 9 - Rôles, Permissions & Audit).
    Filtre et agrège l'ensemble des événements de sécurité et modifications système.
    """
    qs = JournalAudit.objects.select_related('utilisateur').all()

    if action:
        qs = qs.filter(action=action)
    if module:
        qs = qs.filter(module=module)
    if user_id:
        qs = qs.filter(utilisateur_id=user_id)
    if query:
        qs = qs.filter(
            Q(objet_concerne__icontains=query) |
            Q(description__icontains=query) |
            Q(utilisateur__username__icontains=query)
        )

    all_logs_count = JournalAudit.objects.count()
    filtered_count = qs.count()

    nb_prix_changes = JournalAudit.objects.filter(action='MODIFICATION_PRIX').count()
    nb_suppressions = JournalAudit.objects.filter(action='SUPPRESSION').count()
    nb_ajustements = JournalAudit.objects.filter(action='AJUSTEMENT_STOCK').count()
    nb_users_actifs = JournalAudit.objects.filter(utilisateur__isnull=False).values('utilisateur').distinct().count()

    logs = list(qs[:limit])

    return {
        'logs': logs,
        'total_logs': all_logs_count,
        'filtered_count': filtered_count,
        'nb_prix_changes': nb_prix_changes,
        'nb_suppressions': nb_suppressions,
        'nb_ajustements': nb_ajustements,
        'nb_users_actifs': nb_users_actifs,
        'actions_choices': JournalAudit.ACTION_CHOICES,
        'modules_choices': JournalAudit.MODULE_CHOICES,
    }


def get_caisse_session_summary(caissier=None, date_debut=None, date_fin=None) -> dict:
    """
    Synthèse des encaissements en direct de la session de caisse en cours (Phase 11).
    Agrège toutes les ventes non encore clôturées (cloture__isnull=True),
    ou filtrées par période / caissier.
    Permet au caissier de préparer son Rapport Z et de constater les totaux théoriques.
    """
    ventes_qs = Vente.objects.filter(cloture__isnull=True).select_related('produit', 'client')

    if date_debut:
        ventes_qs = ventes_qs.filter(date_vente__gte=date_debut)
    if date_fin:
        ventes_qs = ventes_qs.filter(date_vente__lte=date_fin)

    # Agrégations par mode de paiement
    modes_agg = {}
    for code, label in Vente.MODE_PAIEMENT_CHOICES:
        total_mode = Decimal('0.00')
        qs_mode = ventes_qs.filter(mode_paiement=code)
        for v in qs_mode:
            total_mode += v.prix_total
        modes_agg[code] = total_mode

    total_brut = Decimal('0.00')
    total_remises = Decimal('0.00')
    total_net = Decimal('0.00')
    total_articles = 0

    tickets_set = set()
    for v in ventes_qs:
        total_brut += (Decimal(str(v.quantite)) * v.prix_unitaire)
        total_remises += v.remise
        total_net += v.prix_total
        total_articles += v.quantite
        if v.reference_ticket:
            tickets_set.add(v.reference_ticket)

    derniere_cloture = ClotureCaisse.objects.order_by('-date_cloture').first()

    return {
        'ventes': ventes_qs,
        'nb_ventes': ventes_qs.count(),
        'nb_tickets': len(tickets_set) if tickets_set else (1 if ventes_qs.exists() else 0),
        'nb_articles': total_articles,
        'total_brut': total_brut,
        'total_remises': total_remises,
        'total_net': total_net,
        'total_especes': modes_agg.get('ESPECES', Decimal('0.00')),
        'total_carte': modes_agg.get('CARTE', Decimal('0.00')),
        'total_mobile_money': modes_agg.get('MOBILE_MONEY', Decimal('0.00')),
        'total_cheque': modes_agg.get('CHEQUE', Decimal('0.00')),
        'total_credit': modes_agg.get('CREDIT', Decimal('0.00')),
        'derniere_cloture': derniere_cloture,
    }


def get_clotures_caisse_metrics(date_debut=None, date_fin=None, caissier_id=None, statut=None) -> dict:
    """
    Indicateurs de pilotage et historique des clôtures de caisse (Phase 11).
    """
    qs = ClotureCaisse.objects.select_related('caissier', 'valide_par').all()

    if date_debut:
        qs = qs.filter(date_cloture__date__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_cloture__date__lte=date_fin)
    if caissier_id:
        qs = qs.filter(caissier_id=caissier_id)
    if statut:
        qs = qs.filter(statut_conformite=statut)

    total_clotures = qs.count()
    total_ca_cloture = Decimal('0.00')
    total_ecarts_net = Decimal('0.00')
    nb_conformes = 0
    nb_ecarts = 0

    for c in qs:
        total_ca_cloture += c.total_ventes_net
        total_ecarts_net += c.ecart_total
        if c.statut_conformite == 'CONFORME':
            nb_conformes += 1
        else:
            nb_ecarts += 1

    taux_conformite = round((nb_conformes / total_clotures * 100), 1) if total_clotures > 0 else 100.0

    return {
        'clotures': qs,
        'total_clotures': total_clotures,
        'total_ca_cloture': total_ca_cloture,
        'total_ecarts_net': total_ecarts_net,
        'nb_conformes': nb_conformes,
        'nb_ecarts': nb_ecarts,
        'taux_conformite': taux_conformite,
    }


def get_comptabilite_export_data(date_debut=None, date_fin=None) -> dict:
    """
    Génération des jeux de données d'exportation comptable et valorisation (Phase 11).
    - Inventaire valorisé (coût achat vs valeur vente vs marge potentielle)
    - Ventes détaillées (produits, marge réalisée, remises, moyens de paiement)
    - Compte de résultat périodique
    """
    produits_qs = Produit.objects.select_related('categorie').order_by('nom')
    produits_data = []
    total_valeur_achat = Decimal('0.00')
    total_valeur_vente = Decimal('0.00')

    for p in produits_qs:
        val_achat = Decimal(str(p.stock_actuel)) * p.prix_achat
        val_vente = Decimal(str(p.stock_actuel)) * p.prix_unitaire
        marge_pot = val_vente - val_achat
        total_valeur_achat += val_achat
        total_valeur_vente += val_vente

        produits_data.append({
            'produit': p,
            'valeur_achat': val_achat,
            'valeur_vente': val_vente,
            'marge_potentielle': marge_pot,
            'taux_marge': round(float((marge_pot / val_achat) * 100), 1) if val_achat > 0 else 0.0,
        })

    ventes_qs = Vente.objects.select_related('produit', 'client', 'cloture').order_by('-date_vente')
    if date_debut:
        ventes_qs = ventes_qs.filter(date_vente__date__gte=date_debut)
    if date_fin:
        ventes_qs = ventes_qs.filter(date_vente__date__lte=date_fin)

    ventes_data = []
    total_ca_brut = Decimal('0.00')
    total_remises = Decimal('0.00')
    total_ca_net = Decimal('0.00')
    total_cogs = Decimal('0.00')
    total_marge = Decimal('0.00')

    for v in ventes_qs:
        brut = Decimal(str(v.quantite)) * v.prix_unitaire
        net = v.prix_total
        cout = Decimal(str(v.quantite)) * v.prix_achat
        marge = net - cout

        total_ca_brut += brut
        total_remises += v.remise
        total_ca_net += net
        total_cogs += cout
        total_marge += marge

        ventes_data.append({
            'vente': v,
            'montant_brut': brut,
            'montant_net': net,
            'cout_achat': cout,
            'marge_realisee': marge,
        })

    # Dépenses
    depenses_qs = Depense.objects.all()
    if date_debut:
        depenses_qs = depenses_qs.filter(date_depense__gte=date_debut)
    if date_fin:
        depenses_qs = depenses_qs.filter(date_depense__lte=date_fin)

    total_depenses = depenses_qs.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
    resultat_net = total_marge - total_depenses

    return {
        'produits_inventaire': produits_data,
        'total_valeur_achat': total_valeur_achat,
        'total_valeur_vente': total_valeur_vente,
        'total_marge_potentielle': total_valeur_vente - total_valeur_achat,
        'ventes_detaillees': ventes_data,
        'total_ca_brut': total_ca_brut,
        'total_remises': total_remises,
        'total_ca_net': total_ca_net,
        'total_cogs': total_cogs,
        'total_marge_realisee': total_marge,
        'total_depenses': total_depenses,
        'resultat_net': resultat_net,
    }


def get_notifications_metrics(user=None) -> dict:
    """
    Métriques globales et KPIs du centre de notifications (Phase 12).
    """
    qs = Notification.objects.all()
    if user and user.is_authenticated:
        qs = qs.filter(Q(destinataire=user) | Q(destinataire__isnull=True))
    else:
        qs = qs.filter(destinataire__isnull=True)

    total_actives = qs.filter(est_archivee=False).count()
    non_lues = qs.filter(est_archivee=False, est_lue=False).count()
    critiques = qs.filter(est_archivee=False, niveau='CRITICAL').count()
    avertissements = qs.filter(est_archivee=False, niveau='WARNING').count()
    infos = qs.filter(est_archivee=False, niveau='INFO').count()
    archivees = qs.filter(est_archivee=True).count()

    total_stock = qs.filter(est_archivee=False, type_notification__in=['STOCK_RUPTURE', 'STOCK_FAIBLE']).count()
    total_dettes = qs.filter(est_archivee=False, type_notification='DETTE_FOURNISSEUR').count()
    total_creances = qs.filter(est_archivee=False, type_notification='CREANCE_CLIENT').count()
    total_caisse = qs.filter(est_archivee=False, type_notification='ANOMALIE_CAISSE').count()
    total_systeme = qs.filter(est_archivee=False, type_notification='SYSTEME').count()

    return {
        'total_actives': total_actives,
        'non_lues': non_lues,
        'critiques': critiques,
        'avertissements': avertissements,
        'infos': infos,
        'archivees': archivees,
        'repartition_type': {
            'stock': total_stock,
            'dettes': total_dettes,
            'creances': total_creances,
            'caisse': total_caisse,
            'systeme': total_systeme,
        }
    }




