"""
Module de prédiction ML avancé pour les ventes et ruptures de stock.

Utilise scikit-learn (RandomForestRegressor, Ridge, LinearRegression) et pandas pour :
- Prédire les ventes en incluant la saisonnalité (jour de semaine, week-ends)
- Estimer le nombre de jours avant rupture de stock avec prédiction multi-jours
- Analyser les tendances de ventes et générer des prévisions précises
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge, LinearRegression
from django.utils import timezone
from datetime import timedelta


def _prepare_time_series_features(ventes_queryset):
    """
    Construit un DataFrame avec caractéristiques temporelles & saisonnières à partir des ventes.
    
    Features extraites:
    - day_index: Index temporel continu
    - day_of_week: Jour de la semaine (0 = Lundi, 6 = Dimanche)
    - is_weekend: 1 si Samedi/Dimanche, 0 sinon
    - quantite: Quantité vendue cumulée du jour
    """
    if not ventes_queryset.exists():
        return None

    records = []
    for v in ventes_queryset:
        records.append({
            'date': v.date_vente.date(),
            'quantite': v.quantite,
        })

    df = pd.DataFrame(records)
    # Agrégation par jour
    df_daily = df.groupby('date')['quantite'].sum().reset_index()
    df_daily = df_daily.sort_values('date').reset_index(drop=True)

    if len(df_daily) < 3:
        return None

    df_daily['day_index'] = np.arange(1, len(df_daily) + 1)
    df_daily['day_of_week'] = df_daily['date'].apply(lambda d: d.weekday())
    df_daily['is_weekend'] = df_daily['day_of_week'].apply(lambda w: 1 if w >= 5 else 0)

    return df_daily


def train_sales_model(df_daily):
    """
    Entraîne le meilleur modèle ML disponible (RandomForestRegressor ou Ridge) selon le volume de données.
    """
    X = df_daily[['day_index', 'day_of_week', 'is_weekend']]
    y = df_daily['quantite']

    if len(df_daily) >= 7:
        model = RandomForestRegressor(n_estimators=50, random_state=42, max_depth=5)
    else:
        model = Ridge(alpha=1.0)

    model.fit(X, y)
    return model


def predict_sales(product, days_lookback: int = 30) -> float | str:
    """
    Prédire la quantité vendue pour le jour suivant en tenant compte de la saisonnalité.
    """
    from stockapp.models import Vente

    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    df_daily = _prepare_time_series_features(ventes)
    if df_daily is None or len(df_daily) < 3:
        return "Pas assez de données"

    model = train_sales_model(df_daily)

    # Demain
    next_date = timezone.now().date() + timedelta(days=1)
    next_day_index = len(df_daily) + 1
    next_day_of_week = next_date.weekday()
    next_is_weekend = 1 if next_day_of_week >= 5 else 0

    X_next = pd.DataFrame([[next_day_index, next_day_of_week, next_is_weekend]],
                          columns=['day_index', 'day_of_week', 'is_weekend'])
    prediction = model.predict(X_next)[0]

    return round(max(prediction, 0), 1)


def predict_stockout(product) -> float | str:
    """
    Prédire le nombre de jours avant rupture de stock (moyenne simple).
    """
    from stockapp.models import Vente

    ventes = Vente.objects.filter(produit=product)
    if not ventes.exists():
        return "Pas assez de données"

    records = [v.quantite for v in ventes]
    total = sum(records)
    moyenne = total / max(len(records), 1)

    if moyenne == 0:
        return "Stock stable"

    jours = product.stock_actuel / moyenne
    return round(jours, 1)


def predict_stockout_ml(product, days_lookback: int = 30) -> float | str:
    """
    Prédiction ML de rupture de stock en simulant la demande jour par jour sur 14 jours.
    """
    from stockapp.models import Vente

    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    df_daily = _prepare_time_series_features(ventes)
    if df_daily is None or len(df_daily) < 3:
        return "Pas assez de données"

    model = train_sales_model(df_daily)

    # Simuler la demande jour par jour pour les 14 prochains jours
    current_date = timezone.now().date()
    stock_restant = float(product.stock_actuel)
    days_to_stockout = 0

    for i in range(1, 30):
        target_date = current_date + timedelta(days=i)
        day_index = len(df_daily) + i
        day_of_week = target_date.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0

        X_pred = pd.DataFrame([[day_index, day_of_week, is_weekend]],
                              columns=['day_index', 'day_of_week', 'is_weekend'])
        pred_daily_demand = max(float(model.predict(X_pred)[0]), 0.0)

        stock_restant -= pred_daily_demand
        days_to_stockout = i

        if stock_restant <= 0:
            return float(days_to_stockout)

    return "> 30 jours" if product.stock_actuel > 0 else 0.0


def get_sales_trend(product, days: int = 30) -> dict:
    """
    Obtenir la tendance des ventes et statistiques.
    """
    from stockapp.models import Vente

    depuis = timezone.now() - timedelta(days=days)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=depuis
    ).order_by('date_vente')

    if not ventes.exists():
        return {
            'total': 0,
            'moyenne': 0,
            'min': 0,
            'max': 0,
            'trend': 'Pas de données',
            'pente': 0
        }

    df_daily = _prepare_time_series_features(ventes)
    if df_daily is None:
        quantites = [v.quantite for v in ventes]
        return {
            'total': sum(quantites),
            'moyenne': round(sum(quantites) / len(quantites), 2),
            'min': min(quantites),
            'max': max(quantites),
            'count': len(quantites),
            'periode_jours': days,
            'trend': 'Stable',
            'pente': 0
        }

    quantites = df_daily['quantite'].tolist()
    total = sum(quantites)
    moyenne = total / len(quantites)

    X = df_daily[['day_index']]
    y = df_daily['quantite']

    lin_model = LinearRegression()
    lin_model.fit(X, y)
    pente = lin_model.coef_[0]

    if pente > 0.1:
        trend = "Hausse"
    elif pente < -0.1:
        trend = "Baisse"
    else:
        trend = "Stable"

    return {
        'total': total,
        'moyenne': round(moyenne, 2),
        'min': min(quantites),
        'max': max(quantites),
        'count': len(df_daily),
        'periode_jours': days,
        'trend': trend,
        'pente': round(pente, 3)
    }


def get_demand_forecast(product, days_ahead: int = 7, days_lookback: int = 30) -> dict | str:
    """
    Prédiction de la demande pour les N jours à venir (avec saisonnalité).
    """
    from stockapp.models import Vente

    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    df_daily = _prepare_time_series_features(ventes)
    if df_daily is None or len(df_daily) < 3:
        return "Pas assez de données"

    model = train_sales_model(df_daily)

    predictions = {}
    current_date = timezone.now().date()

    for i in range(1, days_ahead + 1):
        target_date = current_date + timedelta(days=i)
        day_index = len(df_daily) + i
        day_of_week = target_date.weekday()
        is_weekend = 1 if day_of_week >= 5 else 0

        X_future = pd.DataFrame([[day_index, day_of_week, is_weekend]],
                                columns=['day_index', 'day_of_week', 'is_weekend'])
        pred_quantite = model.predict(X_future)[0]
        predictions[target_date.strftime("%Y-%m-%d")] = round(max(pred_quantite, 0), 1)

    model_type = "RandomForest (Saisonnier)" if len(df_daily) >= 7 else "Ridge Regression"

    return {
        'produit_id': product.id,
        'produit_nom': product.nom,
        'period': f"+{days_ahead} jours",
        'predictions': predictions,
        'model_accuracy': f'Optimisé ({model_type})'
    }


def compare_products_forecast(products_list, days: int = 30) -> list:
    result = []
    for product in products_list:
        trend = get_sales_trend(product, days)
        forecast = predict_sales(product, days)

        result.append({
            'produit_id': product.id,
            'produit_nom': product.nom,
            'stock_actuel': product.stock_actuel,
            'rupture': product.rupture,
            'forecast': forecast,
            'trend': trend.get('trend', 'N/A'),
            'average_sales': trend.get('moyenne', 0)
        })

    return sorted(result, key=lambda x: x['average_sales'], reverse=True)


def calculate_reorder_point_and_safety_stock(
    product,
    lead_time_days: int = 5,
    service_level_z: float = 1.65,
    lookback_days: int = 30
) -> dict:
    """
    Module d'Intelligence Commerciale & Aide à la Décision (Phase 8).
    Calcule scientifiquement :
    - La consommation journalière moyenne (d_moyen)
    - L'écart-type de la demande journalière (sigma_d)
    - Le Stock de Sécurité dynamique : SS = ceil(Z * sigma_d * sqrt(L))
    - Le Point de Commande Optimal : ROP = ceil((d_moyen * L) + SS)
    - La Quantité Optimale de Commande (QOC)
    - Le Budget d'achat prévisionnel
    - Le Diagnostic et l'Explication pédagogique d'aide à la décision
    """
    import math
    from stockapp.models import Vente

    since = timezone.now() - timedelta(days=lookback_days)
    ventes = Vente.objects.filter(produit=product, date_vente__gte=since).order_by('date_vente')

    daily_sales = {}
    for v in ventes:
        d = v.date_vente.date()
        daily_sales[d] = daily_sales.get(d, 0) + v.quantite

    today = timezone.now().date()
    quantities = []
    for i in range(lookback_days):
        day = today - timedelta(days=i)
        quantities.append(daily_sales.get(day, 0))

    total_sales = sum(quantities)
    d_moyen = total_sales / float(lookback_days) if lookback_days > 0 else 0.0

    if total_sales > 0:
        variance = sum((q - d_moyen) ** 2 for q in quantities) / float(lookback_days)
        sigma_d = math.sqrt(variance)
    else:
        sigma_d = 0.0

    # Stock de Sécurité (SS)
    if sigma_d > 0:
        safety_stock_calc = int(math.ceil(service_level_z * sigma_d * math.sqrt(lead_time_days)))
        safety_stock = max(safety_stock_calc, product.seuil_alerte)
    else:
        safety_stock = product.seuil_alerte

    # Point de Commande (Reorder Point - ROP)
    demand_during_lead_time = d_moyen * float(lead_time_days)
    rop = int(math.ceil(demand_during_lead_time + safety_stock))

    # Tendance des 7 derniers jours vs 30 jours
    sales_7j = sum(quantities[:7])
    avg_7j = sales_7j / 7.0
    if d_moyen > 0:
        ratio_acceleration = avg_7j / d_moyen
        if ratio_acceleration >= 1.25:
            dynamique = "Forte Accélération (+)"
        elif ratio_acceleration <= 0.75:
            dynamique = "Ralentissement (-)"
        else:
            dynamique = "Rythme Stable"
    else:
        dynamique = "Aucune vente récente"

    # Détection Produit Dormant / Dead Stock
    is_dormant = (total_sales == 0 and product.stock_actuel > 0)

    # Jours avant rupture estimés
    if d_moyen > 0:
        jours_rupture_estimes = round(product.stock_actuel / d_moyen, 1)
    else:
        jours_rupture_estimes = 999.0 if product.stock_actuel > 0 else 0.0

    # Diagnostic & Recommandation
    prix_achat = float(product.prix_achat or 0.0)
    if product.stock_actuel <= 0:
        statut_code = 'CRITIQUE'
        statut_label = 'Rupture effective'
        badge_color = 'bg-rose-100 text-rose-800 border-rose-300'
        action_requise = True
        qte_recommandee = max(product.stock_maximum, int(math.ceil(d_moyen * 14)) if d_moyen > 0 else 10)
        explication = f"Rupture totale. Délai de réapprovisionnement de {lead_time_days}j. Commander d'urgence {qte_recommandee} unité(s)."
    elif product.stock_actuel <= safety_stock:
        statut_code = 'CRITIQUE'
        statut_label = f"Stock sécurité entamé (~{jours_rupture_estimes:.0f}j)"
        badge_color = 'bg-rose-100 text-rose-800 border-rose-300'
        action_requise = True
        qte_recommandee = max(product.stock_maximum - product.stock_actuel, int(math.ceil(d_moyen * 14)), 5)
        explication = (
            f"Stock actuel ({product.stock_actuel}) sous le stock de sécurité ({safety_stock}). "
            f"Au rythme actuel ({d_moyen:.1f} un./j), rupture sous ~{jours_rupture_estimes:.0f} jours. "
            f"Commander {qte_recommandee} unité(s) immédiatement."
        )
    elif product.stock_actuel <= rop:
        statut_code = 'ELEVE'
        statut_label = f"Point commande atteint (~{jours_rupture_estimes:.0f}j)"
        badge_color = 'bg-amber-100 text-amber-800 border-amber-300'
        action_requise = True
        qte_recommandee = max(product.stock_maximum - product.stock_actuel, int(math.ceil(d_moyen * 14)), 5)
        explication = (
            f"Point de commande (ROP={rop}) franchi. Compte tenu du délai fournisseur de {lead_time_days}j "
            f"et de la demande prévisionnelle ({demand_during_lead_time:.1f} un.), commander maintenant prévient la rupture."
        )
    elif is_dormant:
        statut_code = 'DORMANT'
        statut_label = 'Produit dormant (Dead stock)'
        badge_color = 'bg-purple-100 text-purple-800 border-purple-300'
        action_requise = False
        qte_recommandee = 0
        explication = (
            f"Aucune vente enregistrée sur les 30 derniers jours pour {product.stock_actuel} unité(s) en rayon. "
            f"Capital immobilisé : {product.valeur_stock_achat:.2f} FCFA/€. Proposer une promotion ou mise en avant."
        )
    elif product.stock_actuel >= product.stock_maximum and product.stock_maximum > 0:
        statut_code = 'SURSTOCK'
        statut_label = 'Surstock avéré'
        badge_color = 'bg-blue-100 text-blue-800 border-blue-300'
        action_requise = False
        qte_recommandee = 0
        explication = f"Stock ({product.stock_actuel}) supérieur ou égal au stock maximum ({product.stock_maximum}). Bloquer tout réapprovisionnement."
    else:
        statut_code = 'FAIBLE'
        statut_label = f"Niveau sain (~{jours_rupture_estimes:.0f}j)"
        badge_color = 'bg-emerald-100 text-emerald-800 border-emerald-300'
        action_requise = False
        qte_recommandee = 0
        explication = f"Stock suffisant pour environ {jours_rupture_estimes:.0f} jours de ventes. Aucun réapprovisionnement requis."

    budget_estime = round(qte_recommandee * prix_achat, 2)

    return {
        'produit': product,
        'produit_id': product.id,
        'produit_nom': product.nom,
        'reference': product.reference,
        'stock_actuel': product.stock_actuel,
        'seuil_alerte': product.seuil_alerte,
        'stock_maximum': product.stock_maximum,
        'conso_moyenne': round(d_moyen, 2),
        'sigma_d': round(sigma_d, 2),
        'safety_stock': safety_stock,
        'lead_time_days': lead_time_days,
        'rop': rop,
        'dynamique': dynamique,
        'is_dormant': is_dormant,
        'jours_rupture_estimes': jours_rupture_estimes,
        'statut_code': statut_code,
        'statut_label': statut_label,
        'badge_color': badge_color,
        'action_requise': action_requise,
        'qte_recommandee': qte_recommandee,
        'prix_achat': prix_achat,
        'budget_estime': budget_estime,
        'explication': explication,
    }


def get_product_time_series_data(product, days_lookback: int = 14, days_ahead: int = 14) -> dict:
    """
    Génère la série temporelle complète (historique récent + projections ML)
    pour affichage interactif Chart.js dans le simulateur de prévisions.
    """
    from stockapp.models import Vente

    today = timezone.now().date()
    since = today - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(produit=product, date_vente__date__gte=since).order_by('date_vente')

    daily_map = {}
    for v in ventes:
        d_str = v.date_vente.strftime("%d/%m")
        daily_map[d_str] = daily_map.get(d_str, 0) + v.quantite

    labels = []
    historical = []
    forecast = []

    # 1. Historique passé
    for i in range(days_lookback, 0, -1):
        day = today - timedelta(days=i)
        d_str = day.strftime("%d/%m")
        labels.append(d_str)
        historical.append(daily_map.get(d_str, 0))
        forecast.append(None)

    # Point aujourd'hui
    today_str = today.strftime("%d/%m")
    labels.append(today_str)
    today_val = daily_map.get(today_str, 0)
    historical.append(today_val)
    forecast.append(today_val)

    # 2. Projections futures ML
    demand_info = get_demand_forecast(product, days_ahead=days_ahead, days_lookback=30)
    predictions_map = {}
    if isinstance(demand_info, dict) and 'predictions' in demand_info:
        for iso_date, val in demand_info['predictions'].items():
            try:
                dt = timezone.datetime.strptime(iso_date, "%Y-%m-%d").date()
                predictions_map[dt.strftime("%d/%m")] = val
            except Exception:
                pass

    for i in range(1, days_ahead + 1):
        future_day = today + timedelta(days=i)
        d_str = future_day.strftime("%d/%m")
        labels.append(d_str)
        historical.append(None)
        pred_val = predictions_map.get(d_str)
        if pred_val is None:
            pred_val = round(float(product.seuil_alerte or 1) / 3.0, 1)
        forecast.append(pred_val)

    analysis = calculate_reorder_point_and_safety_stock(product)

    return {
        'produit_id': product.id,
        'produit_nom': product.nom,
        'labels': labels,
        'historical': historical,
        'forecast': forecast,
        'stock_actuel': product.stock_actuel,
        'safety_stock': analysis['safety_stock'],
        'rop': analysis['rop'],
        'statut_label': analysis['statut_label'],
        'explication': analysis['explication'],
        'budget_estime': analysis['budget_estime'],
        'qte_recommandee': analysis['qte_recommandee'],
    }

