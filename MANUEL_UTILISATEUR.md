# Manuel Utilisateur Officiel — SMART-TECH

**Application de Gestion Commerciale Intelligente, Stock & Intelligence Artificielle**  
*Version : 14.0 Enterprise — Révision Septembre 2026*

---

## Sommaire

1. [Introduction & Prise en Main](#1-introduction--prise-en-main)
2. [Profil Caissier : Point de Vente & Caisse POS](#2-profil-caissier--point-de-vente--caisse-pos)
3. [Profil Magasinier : Gestion du Stock & Approvisionnements](#3-profil-magasinier--gestion-du-stock--approvisionnements)
4. [Profil Manager : Pilotage, Finances & Intelligence ML](#4-profil-manager--pilotage-finances--intelligence-ml)
5. [Profil Administrateur : Sécurité, Rôles & Sauvegardes](#5-profil-administrateur--sécurité-rôles--sauvegardes)
6. [Utilisation Mobile & PWA Hors-Ligne](#6-utilisation-mobile--pwa-hors-ligne)
7. [Foire Aux Questions & Dépannage](#7-foire-aux-questions--dépannage)

---

## 1. Introduction & Prise en Main

**SMART-TECH** est une plateforme intégrée conçue pour les commerces, boutiques et distributeurs modernes. Elle combine la gestion opérationnelle quotidienne (ventes, stocks, achats, tiers), le pilotage stratégique (dashboard, P&L, marges réelles) et l'aide à la décision prédictive par Machine Learning.

### Connexion à la plateforme
1. Rendez-vous sur votre navigateur à l'adresse : `http://127.0.0.1:8000/` ou le nom de domaine interne configuré.
2. Entrez votre nom d'utilisateur et votre mot de passe.
3. Le système vous redirige automatiquement vers votre espace de travail adapté à vos habilitations.

---

## 2. Profil Caissier : Point de Vente & Caisse POS

### 2.1 Terminal Tactile de Caisse (`/dashboard/caisse/`)
L'interface de caisse est optimisée pour une saisie ultra-rapide des ventes au comptoir :
- **Sélection des articles** : Cliquez sur les vignettes des produits ou scannez directement leur code-barres / référence avec un lecteur optique.
- **Gestion des quantités** : Ajustez via les boutons `+` et `-` dans le panier actif ou saisissez la quantité directement.
- **Recherche instantanée** : Filtrez les produits par nom, référence ou catégorie sans recharger la page.

### 2.2 Modes de Règlement & Encaissements
Le système gère nativement 5 modes de règlement :
- **Espèces** : Saisissez le montant remis par le client, le système calcule instantanément la monnaie exacte à rendre.
- **Carte Bancaire / TPE** : Rapprochement direct du montant net sans calcul de monnaie.
- **Mobile Money** : Paiement par portefeuille électronique (Wave, Moov, Orange, MTN).
- **Chèque** : Enregistrement du numéro de chèque et du titulaire dans les notes.
- **Crédit Client** : Sélectionnez impérativement un client enregistré. Le montant impayé est automatiquement ajouté à son `solde_credit`.

### 2.3 Remises & Édition de Tickets
- **Application d'une remise** : Saisissez le montant en devise de la remise avant validation. La marge brute et le chiffre d'affaires net sont automatiquement recalculés.
- **Impression instantanée** :
  - **Ticket de caisse thermique (80mm)** : Format compact optimisé pour imprimantes ticket.
  - **Facture commerciale A4 (ReportLab)** : Document PDF formel avec mentions légales, tableau des articles, TVA et bas de page.

### 2.4 Clôture de Caisse Journalière — Rapport Z (`/dashboard/caisse/cloture/`)
En fin de journée ou de shift :
1. Cliquez sur le bouton **"Clôturer la Caisse (Rapport Z)"** dans le bandeau de caisse.
2. Saisissez le **fond de caisse initial** de départ.
3. Comptez et déclarez le montant réel présent dans le tiroir-caisse (Espèces, Carte, Mobile Money, Chèques).
4. Le système compare automatiquement les montants théoriques et réels et établit le diagnostic :
   - **CONFORME** : Écart nul.
   - **EXCÉDENT** : Montant physique supérieur au théorique.
   - **DÉFICIT** : Manquant en caisse (génère une alerte critique superviseur).
5. Téléchargez et imprimez le **Rapport Z officiel en PDF A4** pour archivage et signature.

---

## 3. Profil Magasinier : Gestion du Stock & Approvisionnements

### 3.1 Catalogue & Fiches Produits (`/dashboard/produits/`)
- **Création d'un produit** : Renseignez le nom, la référence unique, la catégorie, le prix d'achat HT, le prix de vente TTC, le stock actuel, le seuil d'alerte minimal et le stock maximum.
- **Statut dynamique du stock** :
  - 🔴 **Rupture** : Stock à 0.
  - 🟡 **Stock Faible** : Stock inférieur ou égal au seuil d'alerte.
  - 🟢 **Stock Normal** : Stock régulier sous le plafond.
  - 🔵 **Surstock** : Stock excédant le stock maximum recommandé.

### 3.2 Ajustements Manuels & Inventaire Tournant (`/dashboard/stock/ajuster/`)
Toute correction manuelle de stock doit être justifiée :
- Sélectionnez le produit et saisissez la nouvelle quantité physique constatée.
- Choisissez ou précisez le motif : *Inventaire annuel, Casse / Dépréciation, Don / Échantillon, Erreur de saisie*.
- Chaque ajustement génère un enregistrement inaltérable dans l'historique des **Mouvements de Stock** et dans le **Journal d'Audit**.

### 3.3 Approvisionnements & Bons de Commande (`/dashboard/approvisionnements/`)
- **Enregistrement des réceptions** : Sélectionnez le fournisseur partenaire, le produit et la quantité livrée avec le coût unitaire réel d'achat.
- **Mise à jour automatique** : Le stock du produit est immédiatement incrémenté, et si l'achat est à crédit, la dette du fournisseur est augmentée en conséquence.
- **Génération de Bon de Commande PDF** : Éditez des bons de commande officiels prêts à être transmis aux fournisseurs.

---

## 4. Profil Manager : Pilotage, Finances & Intelligence ML

### 4.1 Dashboard Exécutif (`/dashboard/`)
- Tableau de bord décisionnel central avec indicateurs de croissance :
  - Chiffre d'affaires du jour vs J-1, de la semaine vs S-1, du mois vs M-1.
  - Panier moyen, marge brute globale et taux de rentabilité.
  - Graphiques d'évolution des ventes et répartition par catégories.

### 4.2 Centre Financier & Trésorerie (`/dashboard/finances/`)
- **Compte de Résultat d'Exploitation (P&L)** : CA brut, remises accordées, CA net, coût des marchandises vendues (COGS), marge commerciale brute, charges opérationnelles (OPEX) et résultat d'exploitation net.
- **Bilan de Solvabilité** : Créances clients recouvrables vs dettes fournisseurs à régler.
- **Saisie des dépenses** : Enregistrement des charges courantes (*Loyer, Électricité, Salaires, Transport, etc.*).
- **Export PDF Officiel** : Téléchargement du rapport financier consolidé de l'entreprise.

### 4.3 Intelligence Commerciale & Simulateur Prédictif (`/dashboard/previsions-decision/`)
- **Calcul scientifique du Point de Commande (ROP)** :
  $$ROP = (d \times L) + SS$$
  Où $d$ est la demande journalière moyenne, $L$ le délai fournisseur, et $SS$ le stock de sécurité statistique calculé sur l'écart-type de la demande.
- **Détection des capitaux dormants (*Dead Stock*)** : Identification des références sans rotation sur les 30 derniers jours avec calcul de la valeur immobilisée.
- **Simulateur graphique interactif** : Visualisation des séries temporelles historiques combinées aux projections futures Machine Learning (Random Forest / Ridge Regression).
- **Plan décisionnel d'achat PDF** : Liste prête à l'emploi des quantités recommandées à commander avec budget prévisionnel estimé.

### 4.4 Centre de Rapports & Exports Multi-formats (`/dashboard/rapports/`)
Téléchargement en un clic de rapports sécurisés au format CSV / Excel :
- Inventaire valorisé complet du stock au coût d'achat et au prix de vente.
- Journal détaillé des ventes avec marges unitaires et réelles.
- Compte de résultat périodique pour la comptabilité.

---

## 5. Profil Administrateur : Sécurité, Rôles & Sauvegardes

### 5.1 Rôles & Permissions
SMART-TECH applique un contrôle d'accès strict basé sur le rôle principal de l'utilisateur :
- **Admin** : Accès intégral, gestion des utilisateurs, journal d'audit et sauvegardes.
- **Manager** : Pilotage stratégique, finances, rapports et aide à la décision.
- **Magasinier** : Gestion opérationnelle du catalogue, des stocks et approvisionnements.
- **Caissier** : Accès dédié au terminal POS et à la clôture de caisse.

### 5.2 Journal d'Audit Exécutif (`/dashboard/securite/audit/`)
Traçabilité complète et immuable des événements sensibles :
- Modifications de prix de vente des produits.
- Ajustements manuels de stock.
- Règlements de dettes fournisseurs et créances clients.
- Suppressions critiques de documents ou de données.
- Filtres avancés par module, type d'action, utilisateur et export CSV d'audit.

### 5.3 Centre de Sauvegarde & Sécurité (`/dashboard/securite/sauvegardes/`)
- **Création de sauvegardes à chaud** : Cliché instantané sans coupure de service. L'archive `.zip` contient la base SQLite, l'export JSON Django et tous les médias.
- **Diagnostic de santé SQL** : Exécution des contrôles `PRAGMA integrity_check` et `PRAGMA foreign_key_check`.
- **Restauration sécurisée** : Avant toute réécriture de la base, un snapshot de pré-restauration de secours est automatiquement créé.
- **Politique de rotation** : Conservation automatique des $N$ dernières archives et purge des événements d'audit anciens.

---

## 6. Utilisation Mobile & PWA Hors-Ligne

SMART-TECH est une **Progressive Web App (PWA)** installable :
- **Installation sur smartphone / tablette / PC** : Cliquez sur le bouton "Installer l'application" dans la bannière ou le menu du navigateur.
- **Navigation mobile optimisée** : Barre inférieure avec raccourci direct vers le terminal de caisse.
- **Mode Hors-Ligne** : En cas de coupure réseau, une page sécurisée `/offline/` informe l'utilisateur et rétablit l'application dès que la connectivité est restaurée.

---

## 7. Foire Aux Questions & Dépannage

**Q : Que faire si le tiroir-caisse présente un écart lors de la clôture Z ?**  
*R :* Renseignez le montant exact compté physiquement. L'écart est calculé et journalisé. En cas de déficit notable, ajoutez une note explicative dans le champ commentaire du formulaire de clôture.

**Q : Comment annuler une vente erronée ?**  
*R :* Un utilisateur ayant le rôle Manager ou Admin peut supprimer la vente depuis la liste des ventes. Le stock des articles sera automatiquement réintégré et l'action sera consignée dans le Journal d'Audit.

**Q : Où sont stockées les sauvegardes système ?**  
*R :* Dans le répertoire `backups/` du serveur. Elles sont également téléchargeables directement au format ZIP depuis l'interface administrateur.
