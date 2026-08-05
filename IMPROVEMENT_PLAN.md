# Plan d'Amélioration du Projet

## Objectif

Améliorer la robustesse, la maintenabilité et la préparation à la production du projet.

## Priorités immédiates

- Ajouter `reportlab` dans `requirements.txt` si l'export PDF est utilisé.
- Activer la pagination sur les endpoints API.
- Ajouter le filtrage et la recherche sur `ProduitViewSet`.
- Renforcer les tests API et d'intégration.
- Documenter les paramètres et les formats des endpoints.

## Fonctionnalités à développer

### Authentification et sécurité
- Ajouter JWT ou authentification token pour l'API.
- Restreindre les endpoints sensibles aux utilisateurs authentifiés.
- Protéger le dashboard si nécessaire.

### Export / Import
- Compléter l'export PDF et s'assurer de la dépendance `reportlab`.
- Ajouter l'import CSV pour les produits.
- Prévoir un import CSV pour les approvisionnements.

### Dashboard
- Ajouter des filtres par période et par produit.
- Ajouter une recherche produit.
- Ajouter un tableau comparatif des tendances.
- Ajouter des KPI exportables.

### ML / Prédictions
- Ajouter un endpoint de prédiction journalier détaillé.
- Stocker les prédictions calculées pour améliorer les performances.
- Ajouter des prévisions multi-journées et des prévisions de stock.

## Scalabilité

### Base de données
- Migrer vers PostgreSQL pour la production.
- Ajouter des index de recherche sur les produits.

### Cache et asynchrone
- Ajouter Redis pour le cache de résultats API.
- Ajouter Celery pour les tâches asynchrones (alertes, rapports, import CSV).

### Monitoring

- Ajouter Sentry.
- Ajouter des métriques de performance.

## Branches et workflow

- `main` : flux stable, destiné à la production ou à une version de référence propre.
- `advanced-features` : flux expérimental, destiné aux nouvelles fonctionnalités et prototypes UI.
- Maintenir `main` propre et stable, en utilisant `advanced-features` pour les développements en cours.

## Roadmap

1. Sécuriser l'API
2. Renforcer les tests
3. Ajouter export/import de données
4. Migrer vers une architecture de production
