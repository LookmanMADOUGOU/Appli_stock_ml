# 📘 Gestion de Stock IA — Guide du Projet

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
.\stock\Scripts\Activate.ps1
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
