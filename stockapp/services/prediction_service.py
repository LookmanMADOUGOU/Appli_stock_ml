"""
Module de prédiction ML pour les ventes et ruptures de stock.

Utilise scikit-learn (LinearRegression) et pandas pour :
- Prédire la quantité vendue pour le jour suivant
- Estimer le nombre de jours avant rupture de stock
- Analyser les tendances de ventes sur une période
"""

import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from django.db.models import QuerySet
from django.utils import timezone
from datetime import timedelta


def predict_sales(product, days_lookback: int = 30) -> float | str:
    """
    Prédire la quantité vendue pour le jour suivant.
    
    Utilise une régression linéaire sur les ventes historiques.
    
    Args:
        product: Instance du modèle Produit
        days_lookback: Nombre de jours d'historique à analyser
        
    Returns:
        float: Quantité prédite (ou message d'erreur en str)
    """
    from stockapp.models import Vente
    
    # Récupérer les ventes des N derniers jours
    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    # Besoin d'au moins 3 données points
    if ventes.count() < 3:
        return "Pas assez de données"

    # Préparer les données
    data = []
    for index, vente in enumerate(ventes):
        data.append([
            index + 1,
            vente.quantite
        ])

    df = pd.DataFrame(
        data,
        columns=["jour", "quantite"]
    )

    # Entraîner le modèle
    X = df[["jour"]]
    y = df["quantite"]

    modele = LinearRegression()
    modele.fit(X, y)

    # Prédire le jour suivant
    prochain_jour = [[len(df) + 1]]
    prediction = modele.predict(prochain_jour)[0]

    # Assurer que la prédiction est positive
    return round(max(prediction, 0), 1)


def predict_stockout(product) -> float | str:
    """
    Prédire le nombre de jours avant rupture de stock.
    
    Calcul simple basé sur la moyenne des ventes récentes.
    
    Args:
        product: Instance du modèle Produit
        
    Returns:
        float: Nombre de jours avant rupture
        str: Message d'erreur si pas assez de données
    """
    from stockapp.models import Vente
    
    ventes = Vente.objects.filter(
        produit=product
    )

    if not ventes.exists():
        return "Pas assez de données"

    total = sum(v.quantite for v in ventes)
    moyenne = total / ventes.count()

    if moyenne == 0:
        return "Stock stable"

    jours = product.stock_actuel / moyenne
    return round(jours, 1)


def predict_stockout_ml(product, days_lookback: int = 30) -> float | str:
    """
    Prédiction ML du nombre de jours avant rupture.
    
    Combine la tendance de ventes et le stock actuel.
    
    Args:
        product: Instance du modèle Produit
        days_lookback: Nombre de jours d'historique
        
    Returns:
        float: Nombre de jours estimés avant rupture
        str: Message d'erreur
    """
    from stockapp.models import Vente
    
    # Récupérer les ventes
    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    if ventes.count() < 3:
        return "Pas assez de données"

    # Préparer les données
    data = []
    for index, vente in enumerate(ventes):
        data.append([index + 1, vente.quantite])

    df = pd.DataFrame(data, columns=["jour", "quantite"])

    # Entraîner le modèle
    X = df[["jour"]]
    y = df["quantite"]
    
    modele = LinearRegression()
    modele.fit(X, y)

    # Calculer la moyenne journalière prédite
    derniers_jours_pred = []
    for i in range(len(df), len(df) + 7):
        pred = modele.predict([[i]])[0]
        derniers_jours_pred.append(max(pred, 0))

    moyenne_pred = sum(derniers_jours_pred) / len(derniers_jours_pred)

    if moyenne_pred == 0:
        return "Stock stable"

    jours = product.stock_actuel / moyenne_pred
    return round(jours, 1)


def get_sales_trend(product, days: int = 30) -> dict:
    """
    Obtenir la tendance des ventes sur une période.
    
    Analyse statistique des ventes avec sklearn.
    
    Args:
        product: Instance du modèle Produit
        days: Nombre de jours à analyser
        
    Returns:
        dict: Statistiques et tendance
    """
    from stockapp.models import Vente
    
    # Récupérer les ventes des X derniers jours
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
            'trend': 'Pas de données'
        }

    quantites = [v.quantite for v in ventes]
    total = sum(quantites)
    moyenne = total / len(quantites)
    
    # Analyser la tendance
    data = []
    for index, vente in enumerate(ventes):
        data.append([index + 1, vente.quantite])
    
    df = pd.DataFrame(data, columns=["jour", "quantite"])
    X = df[["jour"]]
    y = df["quantite"]
    
    modele = LinearRegression()
    modele.fit(X, y)
    
    # Déterminer la tendance
    pente = modele.coef_[0]
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
        'count': len(quantites),
        'periode_jours': days,
        'trend': trend,
        'pente': round(pente, 3)
    }


def get_demand_forecast(product, days_ahead: int = 7, days_lookback: int = 30) -> dict | str:
    """
    Prédiction de la demande pour les N jours à venir.
    
    Utilise une régression linéaire sur l'historique.
    
    Args:
        product: Instance du modèle Produit
        days_ahead: Nombre de jours à prédire
        days_lookback: Nombre de jours d'historique
        
    Returns:
        dict: Prédictions jour par jour
        str: Message d'erreur
    """
    from stockapp.models import Vente
    
    since = timezone.now() - timedelta(days=days_lookback)
    ventes = Vente.objects.filter(
        produit=product,
        date_vente__gte=since
    ).order_by("date_vente")

    if ventes.count() < 3:
        return "Pas assez de données"

    # Préparer les données
    data = []
    for index, vente in enumerate(ventes):
        data.append([index + 1, vente.quantite])

    df = pd.DataFrame(data, columns=["jour", "quantite"])

    # Entraîner le modèle
    X = df[["jour"]]
    y = df["quantite"]
    
    modele = LinearRegression()
    modele.fit(X, y)

    # Prédire les jours à venir
    predictions = {}
    current_date = timezone.now()
    
    for i in range(1, days_ahead + 1):
        pred_day = len(df) + i
        pred_quantite = modele.predict([[pred_day]])[0]
        future_date = current_date + timedelta(days=i)
        
        predictions[future_date.strftime("%Y-%m-%d")] = round(max(pred_quantite, 0), 1)

    return {
        'produit_id': product.id,
        'produit_nom': product.nom,
        'period': f"+{days_ahead} jours",
        'predictions': predictions,
        'model_accuracy': 'À améliorer (simple LinearRegression)'
    }


def compare_products_forecast(products_list, days: int = 30) -> list:
    """
    Comparer les prédictions de plusieurs produits.
    
    Args:
        products_list: Liste de produits
        days: Nombre de jours à analyser
        
    Returns:
        list: Comparaison des tendances
    """
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
