from pathlib import Path

root = Path(r'c:\Users\LOOK-TECH\Desktop\Appli_stock_predi_vente_rupture')

docs = {
    'README.md': '''# 📘 Gestion de Stock IA — Guide du Projet

## Présentation

Application Django de gestion de stock qui gère les produits, le stock, les ventes, les approvisionnements, les alertes de rupture et les prévisions.

Le projet propose :
- un dashboard responsive
- une API REST complète
- des prévisions simples basées sur les données de ventes
- des exports CSV et PDF

## Installation

1. Activer l'environnement virtuel :

```powershell
.\\stock\\Scripts\\Activate.ps1
```

2. Installer les dépendances :

```bash
pip install -r requirements.txt
```

3. Appliquer les migrations :

```bash
python manage.py migrate
```

4. Créer un super-utilisateur :

```bash
python manage.py createsuperuser
```

5. Lancer le serveur :

```bash
python manage.py runserver
```

## Accès principaux

- Accueil : http://localhost:8000/
- Dashboard : http://localhost:8000/dashboard/
- Admin : http://localhost:8000/admin/
- API : http://localhost:8000/api/
- Export CSV produits : http://localhost:8000/api/exports/products/
- Export PDF stock : http://localhost:8000/dashboard/export/pdf/

## Fonctionnalités

- Gestion des catégories, produits, ventes, approvisionnements et alertes
- Calcul automatique du stock lors des ventes et approvisionnements
- Alertes de rupture créées et résolues automatiquement
- Dashboard avec graphiques et informations clés
- API REST pour intégration externe
- Prédictions de ventes et de rupture

## Architecture

```
Appli_stock_predi_vente_rupture/
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── stockapp/
│   ├── admin.py
│   ├── api/
│   ├── models.py
│   ├── services/
│   ├── signals.py
│   ├── templates/stockapp/
│   └── views.py
├── manage.py
├── db.sqlite3
└── requirements.txt
```

## Modèles

### Categorie
- `nom` unique

### Produit
- `categorie`, `nom`, `reference`, `stock_actuel`, `seuil_alerte`
- Propriétés :
  - `rupture`
  - `prediction_ml`
  - `prediction_rupture`
  - `prediction_stockout`

### Vente
- `produit`, `quantite`, `date_vente`

### Approvisionnement
- `produit`, `quantite`, `date_approvisionnement`, `fournisseur`

### AlerteRupture
- `produit`, `niveau`, `message`, `date_creation`, `date_resolution`, `est_resolue`

## API REST

### Produits
- `GET /api/produits/`
- `GET /api/produits/{id}/`
- `GET /api/produits/{id}/prediction/`
- `GET /api/exports/products/`

### Ventes
- `GET /api/ventes/`
- `POST /api/ventes/`
- `GET /api/ventes/{id}/`
- `PUT /api/ventes/{id}/`
- `DELETE /api/ventes/{id}/`

### Approvisionnements
- `GET /api/approvisionnements/`
- `POST /api/approvisionnements/`
- `GET /api/approvisionnements/{id}/`
- `PUT /api/approvisionnements/{id}/`
- `DELETE /api/approvisionnements/{id}/`

### Alertes
- `GET /api/alertes/`
- `POST /api/alertes/`
- `GET /api/alertes/{id}/`
- `PUT /api/alertes/{id}/`
- `DELETE /api/alertes/{id}/`

### Prédictions et statistiques
- `GET /api/previsions/`
- `GET /api/previsions/?produit=1`
- `GET /api/stats/summary/`
- `GET /api/stats/category/{category_id}/`
- `GET /api/stats/trend/?days=30`

### Graphiques
- `GET /api/charts/sales/?days=30`
- `GET /api/charts/sales/product/{product_id}/?days=30`
- `GET /api/charts/consumption/?days=30&limit=10`
- `GET /api/charts/stock/`

## Tests

```bash
python manage.py test
python manage.py test -v 2
```

## Dépendances

- Django==6.0.6
- djangorestframework==3.17.1
- pandas==3.0.3
- scikit-learn==1.9.0
- numpy==2.4.6
- scipy==1.17.1

## Remarques

- Ajouter `reportlab` dans `requirements.txt` si l'export PDF est utilisé.
- SQLite convient pour le développement ; PostgreSQL est recommandé en production.
''',
    'QUICK_START.md': '''# 🚀 Guide Rapide de Démarrage

Ce document explique comment démarrer rapidement le projet, utiliser le dashboard et tester l'API.

## 1. Activer l'environnement

```powershell
.\stock\Scripts\Activate.ps1
```

## 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

## 3. Appliquer les migrations

```bash
python manage.py migrate
```

## 4. Créer un super-utilisateur

```bash
python manage.py createsuperuser
```

## 5. Lancer le serveur

```bash
python manage.py runserver
```

## 6. Accéder aux services

- Accueil : http://localhost:8000/
- Dashboard : http://localhost:8000/dashboard/
- Admin Django : http://localhost:8000/admin/
- API : http://localhost:8000/api/
- Export CSV produits : http://localhost:8000/api/exports/products/
- Export PDF stock : http://localhost:8000/dashboard/export/pdf/

---

## 7. Utilisation rapide

### Créer une catégorie

Admin → Catégories → Ajouter

### Créer un produit

Admin → Produits → Ajouter
- Nom : Écran 27 pouces
- Référence : ECRAN-001
- Catégorie : Électronique
- Stock actuel : 10
- Seuil alerte : 3

### Enregistrer une vente

Admin → Ventes → Ajouter
- Produit : Écran 27 pouces
- Quantité : 2

### Consulter le dashboard

http://localhost:8000/dashboard/

---

## 8. Exemples d'API

### Obtenir tous les produits

```bash
curl http://localhost:8000/api/produits/
```

### Créer une vente

```bash
curl -X POST http://localhost:8000/api/ventes/ \
  -H "Content-Type: application/json" \
  -d '{"produit": 1, "quantite": 2}'
```

### Obtenir les prédictions

```bash
curl http://localhost:8000/api/previsions/
```

### Exporter les produits au format CSV

```bash
curl http://localhost:8000/api/exports/products/ -o produits.csv
```
''',
    'AUDIT_REPORT.md': '''# Audit du Projet Django — Gestion de Stock et Prédictions

## Contexte

Application Django de gestion de stock avec alertes, prévisions et API REST.

## Routes disponibles

- / : page d'accueil
- /dashboard/ : dashboard
- /admin/ : administration
- /api/ : API principale
- /api/exports/products/ : export CSV produits
- /dashboard/export/pdf/ : export PDF stock

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

## Recommandations

1. Ajouter `reportlab` dans `requirements.txt` si l'export PDF est utilisé en production.
2. Mettre en place une authentification API.
3. Ajouter pagination et filtrage sur les endpoints.
4. Ajouter des tests d'intégration API.
''',
    'IMPROVEMENT_PLAN.md': '''# Plan d'Amélioration du Projet

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

## Roadmap

1. Sécuriser l'API
2. Renforcer les tests
3. Ajouter export/import de données
4. Migrer vers une architecture de production
''',
    'COMPLETION_SUMMARY.md': '''# Résumé du Projet et de la Documentation

## État actuel

Le projet dispose désormais d'une documentation complète et cohérente.

## Documentation produite

- README.md
- QUICK_START.md
- AUDIT_REPORT.md
- IMPROVEMENT_PLAN.md
- COMPLETION_SUMMARY.md

## Contenu principal

- guide d'installation
- routes API
- pages d'accès
- recommandations d'amélioration

## Prochaines actions

- confirmer l'ajout de `reportlab`
- sécuriser l'API
- renforcer les tests
- documenter la configuration de production

## Notes

- Le dashboard utilise Chart.js.
- L'export CSV produits est actif.
- L'export PDF stock doit être validé en tant que fonctionnalité.
- L'API REST reste publique actuellement.
'''
}

for filename, content in docs.items():
    path = root / filename
    path.write_text(content, encoding='utf-8')
    print(f'Updated {filename}')
