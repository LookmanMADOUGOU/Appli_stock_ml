# Audit du Projet Django — Gestion de Stock et Prédictions

## Contexte

Application Django de gestion de stock avec alertes, prévisions et API REST.

## Routes disponibles

- / : page d'accueil
- /dashboard/ : dashboard
- /admin/ : administration
- /api/ : API principale
- /api/exports/products/ : export CSV produits
- /dashboard/export/pdf/ : export PDF stock

## Branches

- `main` : version stable, conçue pour rester propre et simple. La gestion des objets se fait principalement via l’administration Django, tandis que le dashboard fournit une vue de consultation et de suivi.
- `advanced-features` : version expérimentale et évolutive. Elle active des prototypes UI, des commandes IA, un support PWA et des améliorations de navigation.

## Modèles métiers

### Categorie
- `nom` unique

### Produit
- `categorie`, `nom`, `reference`, `stock_actuel`, `seuil_alerte`
- propriétés : `rupture`, `prediction_ml`, `prediction_rupture`, `prediction_stockout`

### Vente
- `produit`, `quantite`, `date_vente`

### Approvisionnement
- `produit`, `quantite`, `date_approvisionnement`, `fournisseur`

### AlerteRupture
- `produit`, `niveau`, `message`, `date_creation`, `date_resolution`, `est_resolue`

## Points clés

- Signaux Django pour mise à jour automatique du stock
- Export CSV produits disponible
- API REST exposée pour les produits, ventes, approvisionnements, alertes, statistiques et graphiques
- Page d'accueil premium et dashboard cohérent

## Observations

- L'API est publique sans authentification
- `reportlab` est utilisé dans `stockapp/views.py` pour le PDF mais est absent de `requirements.txt`
- Les prévisions sont calculées à la volée sur le modèle Produit
- Le projet utilise deux branches principales : `main` pour la version stable et `advanced-features` pour les nouveautés et expérimentations UI/produit.

## Recommandations

1. Ajouter `reportlab` dans `requirements.txt` si l'export PDF est utilisé en production.
2. Mettre en place une authentification API.
3. Ajouter pagination et filtrage sur les endpoints.
4. Ajouter des tests d'intégration API.
