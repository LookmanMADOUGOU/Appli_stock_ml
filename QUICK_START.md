# 🚀 Guide Rapide de Démarrage

Ce document explique comment démarrer rapidement le projet, utiliser le dashboard et tester l'API.

## 1. Activer l'environnement

```powershell
.\stockml\Scripts\Activate.ps1
```

## Branches du projet


- `main` : version stable. Toutes les actions de gestion (ajouts, modifications, suppressions) doivent être effectuées via l'administration Django. Le dashboard sert uniquement à la consultation sur `main`.
- `advanced-features` : version avancée avec les dernières améliorations UI et fonctions expérimentales (PWA, commandes IA, enrichissements de tableau de bord). Sur cette branche, des opérations expérimentales depuis le dashboard peuvent être disponibles.

Changer de branche :

```bash
git checkout main
```

```bash
git checkout advanced-features
```

> Astuce : vérifiez toujours la branche active avant de lancer le serveur ou d’appliquer des migrations.

## Avant d'appliquer des migrations ou de lancer le serveur

- **Vérifier la branche active :**

```bash
git status --porcelain --branch
```

- **Récupérer les dernières modifications de `main` (si vous êtes sur `main`) :**

```bash
git fetch origin
git pull origin main
```

- **Si vous travaillez sur une branche de fonctionnalité, synchronisez-la avec `main` avant d'exécuter des migrations :**

```bash
git checkout feature/<nom_de_la_feature>
git fetch origin
git merge origin/main
```

> Important : Exécuter les migrations sur `main` en production uniquement après revue et sauvegarde de la base.

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
curl -X POST http://localhost:8000/api/ventes/   -H "Content-Type: application/json"   -d '{"produit": 1, "quantite": 2}'
```

### Obtenir les prédictions

```bash
curl http://localhost:8000/api/previsions/
```

### Exporter les produits au format CSV

```bash
curl http://localhost:8000/api/exports/products/ -o produits.csv
```
