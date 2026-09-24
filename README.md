# 📘 SMART-TECH — Gestion Commerciale Intelligente, Stock & IA

> **Plateforme d'Entreprise Full-Stack Django : Gestion Commerciale, Pilotage Financier, Intelligence Artificielle Prédictive, Caisse POS Tactile, Clôture Journalière Rapport Z, Alertes Proactives et Sécurité des Données.**

---

## 🎯 Présentation Globale & Vision

**SMART-TECH** transforme la gestion des commerces, superettes et distributeurs à travers 3 niveaux d'excellence :

1. **Niveau 1 — Gestion Opérationnelle** :
   - Catalogue produits dynamique avec codes-barres, marges et statuts de stock.
   - Terminal de caisse tactile POS ultra-rapide (multi-articles, remises, calcul de monnaie, crédit client).
   - Édition instantanée de tickets thermiques (80mm) et de factures commerciales A4 (ReportLab).
   - Clôture de caisse journalière (Rapport Z officiel PDF) avec réconciliation et contrôle d'écarts.
   - Gestion intégrée des clients (crédits/créances) et fournisseurs (achats/dettes).
   - Suivi d'Audit Trail inaltérable pour chaque mouvement de stock.

2. **Niveau 2 — Pilotage Financier & Décisionnel** :
   - Dashboard exécutif temps réel avec comparatifs d'évolution (J vs J-1, S vs S-1, M vs M-1).
   - Centre financier et compte de résultat d'exploitation (P&L, COGS, charges OPEX, résultat net).
   - Hub de rapports d'exportation comptables (Inventaire valorisé, ventes réelles, rentabilité CSV/Excel).
   - Centre de notifications proactives et cloche interactive (détection des ruptures, retards et anomalies).

3. **Niveau 3 — Intelligence Artificielle Prédictive** :
   - Modèles de Machine Learning Scikit-Learn (Random Forest, Ridge Regression) pour la projection des ventes.
   - Calcul scientifique du Point de Commande ($ROP$) et du Stock de Sécurité statistique ($SS$).
   - Détection automatique des capitaux dormants (*Dead Stock* / produits sans rotation).
   - Simulateur prédictif interactif et génération assistée de bons de commande fournisseurs optimisés.

4. **Niveau 4 — Sécurité & Continuité d'Activité** :
   - Contrôle d'accès par rôle (Admin, Manager, Caissier, Magasinier).
   - Journal d'audit complet de toutes les opérations sensibles.
   - Moteur de sauvegarde SQLite à chaud (archives ZIP, JSON dump, médias, empreinte SHA-256).
   - Diagnostic d'intégrité SQL direct (`PRAGMA integrity_check`) et snapshots de secours pré-restauration.
   - PWA mobile installable avec mode hors-ligne résilient.

---

## 🚀 Démarrage en 1 Clic

### Sous Windows
Double-cliquez simplement sur le script fourni à la racine :
```cmd
run_smart_tech.bat
```
*Le script configure l'environnement, applique les migrations, initialise les rôles, vérifie l'intégrité de la base et ouvre automatiquement votre navigateur sur `http://127.0.0.1:8000/`.*

### Sous Linux / macOS
```bash
chmod +x run_smart_tech.sh
./run_smart_tech.sh
```

### Avec Docker & Docker Compose
```bash
cp .env.example .env
docker compose up -d --build
```
L'application démarre immédiatement sur `http://localhost:8000/`.

---

## ⚙️ Installation Manuelle Standard

1. **Activer l'environnement virtuel** :
   ```powershell
   # Windows
   .\.venv\Scripts\Activate.ps1
   # Linux/macOS
   source .venv/bin/activate
   ```

2. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
   ```

3. **Appliquer les migrations de schéma** :
   ```bash
   python manage.py migrate --noinput
   ```

4. **Initialiser les rôles métier de sécurité** :
   ```bash
   python manage.py init_roles
   ```
   *(Crée automatiquement les groupes `Admin`, `Manager`, `Caissier`, `Magasinier` avec leurs permissions respectives)*

5. **Créer le compte Administrateur** :
   ```bash
   python manage.py createsuperuser
   ```

6. **Lancer le serveur de développement** :
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

---

## 🌐 Cartographie des Modules & URLs

| Module | URL | Rôle Recommandé | Description |
| :--- | :--- | :--- | :--- |
| **Accueil & Présentation** | `/` | Tous | Portail de présentation |
| **Connexion** | `/login/` | Tous | Authentification sécurisée |
| **Dashboard Exécutif** | `/dashboard/` | Tous | Indicateurs clés, graphiques et KPIs |
| **Caisse Enregistreuse POS** | `/dashboard/caisse/` | Caissier, Manager, Admin | Terminal de vente tactile rapide |
| **Clôture de Caisse (Rapport Z)**| `/dashboard/caisse/cloture/` | Caissier, Manager, Admin | Équilibrage tiroir et Rapport Z PDF |
| **Historique des Clôtures** | `/dashboard/caisse/clotures/` | Manager, Admin | Audit des sessions de caisse |
| **Catalogue Produits** | `/dashboard/produits/` | Magasinier, Manager, Admin | Fiches articles, prix, marges, codes-barres |
| **Stock & Inventaire** | `/dashboard/stock/` | Magasinier, Manager, Admin | Alertes et ajustements justifiés |
| **Mouvements d'Audit Trail** | `/dashboard/mouvements/` | Magasinier, Manager, Admin | Historique de chaque variation de stock |
| **Journal des Ventes** | `/dashboard/ventes/` | Caissier, Manager, Admin | Tickets, factures A4 ReportLab |
| **Centre Financier (P&L)** | `/dashboard/finances/` | Manager, Admin | Marges, COGS, charges, résultat net |
| **Prévisions ML & Décision** | `/dashboard/previsions-decision/`| Manager, Admin | Point de commande ROP, aide aux achats |
| **Hub d'Export & Rapports** | `/dashboard/rapports/` | Manager, Admin | Exports comptables CSV / Excel |
| **Centre d'Alertes** | `/dashboard/notifications/` | Tous | Notifications proactives et dédupliquées |
| **Fiches Clients & Crédits** | `/dashboard/clients/` | Caissier, Manager, Admin | Encaissements et créances |
| **Fiches Fournisseurs** | `/dashboard/fournisseurs/` | Manager, Admin | Dettes et historiques d'achats |
| **Approvisionnements** | `/dashboard/approvisionnements/`| Magasinier, Admin | Réceptions et bons de commande |
| **Journal d'Audit Exécutif** | `/dashboard/securite/audit/` | Admin, Manager | Traçabilité des opérations sensibles |
| **Sauvegardes & Restauration** | `/dashboard/securite/sauvegardes/`| Admin | Clichés SQLite à chaud & intégrité |
| **Mode Hors-Ligne PWA** | `/offline/` | Tous | Écran de résilience déconnexion |

---

## 🛠️ Commandes CLI d'Exploitation & Maintenance

| Commande | Syntaxe | Rôle |
|---|---|---|
| **Sauvegarde Système** | `python manage.py backup_system [--name <nom>] [--retention <jours>] [--max <quota>]` | Crée une archive ZIP complète (base, dump JSON, médias, SHA256) |
| **Restauration Système** | `python manage.py restore_system <nom_archive.zip> [--no-input]` | Restaure la base avec snapshot de sécurité préventif |
| **Diagnostic d'Intégrité** | `python manage.py check_system_integrity` | Analyse physique `PRAGMA integrity_check` et volumes SQL |
| **Initialisation Rôles** | `python manage.py init_roles` | Configure les 4 groupes RBAC standards |

---

## 📚 Documentation Associée

Pour approfondir l'exploitation de la plateforme :
- **[Manuel Utilisateur Officiel](MANUEL_UTILISATEUR.md)** : Guide opérationnel détaillé par profil de poste (Caissier, Magasinier, Manager, Administrateur).
- **[Guide de Déploiement & Production](GUIDE_DEPLOIEMENT.md)** : Instructions pour Docker, Linux Systemd/Nginx, Windows Server et plan de reprise d'activité.

---

## 🧪 Tests Automatisés & Assurance Qualité

Le projet intègre une suite de tests automatisés couvrant 100% des cas d'usage critiques des 14 phases :

```bash
# Exécution de la suite complète
python manage.py test

# Exécution ciblée par phase
python manage.py test stockapp.tests.Phase13BackupAndDataSecurityTests
python manage.py test stockapp.tests.Phase11ClotureCaisseAndAdvancedReportsTests
python manage.py test stockapp.tests.Phase12NotificationsAndAlertsTests
```
