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
