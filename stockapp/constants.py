"""
Constantes et choix centralisés pour SMART-TECH.
Module assurant une source unique de vérité pour les statuts, types et configurations.
"""

# Statuts de stock centralisés
STATUT_RUPTURE = "RUPTURE"
STATUT_FAIBLE = "STOCK FAIBLE"
STATUT_NORMAL = "STOCK NORMAL"
STATUT_SURSTOCK = "SURSTOCK"

STOCK_STATUS = {
    "RUPTURE": "Rupture de stock",
    "FAIBLE": "Stock faible",
    "NORMAL": "En stock",
    "SURSTOCK": "Surstock"
}

STOCK_STATUS_CHOICES = [
    ('RUPTURE', 'Rupture de stock (0 unité)'),
    ('FAIBLE', 'Stock faible (<= seuil d\'alerte)'),
    ('NORMAL', 'Stock normal'),
    ('SURSTOCK', 'Surstock (>= capacité max)'),
]

# Types de mouvements de stock
TYPE_MOUVEMENT_CHOICES = [
    ('ENTREE', 'Entrée de stock'),
    ('SORTIE', 'Sortie de stock'),
    ('VENTE', 'Vente client'),
    ('ACHAT', 'Achat / Approvisionnement'),
    ('RETOUR', 'Retour produit'),
    ('AJUSTEMENT', 'Ajustement manuel'),
    ('INVENTAIRE', 'Régularisation d\'inventaire'),
]

# Modes de paiement supportés
MODE_PAIEMENT_CHOICES = [
    ('ESPECES', 'Espèces'),
    ('CARTE', 'Carte Bancaire'),
    ('MOBILE_MONEY', 'Mobile Money'),
    ('CHEQUE', 'Chèque'),
    ('CREDIT', 'Crédit / En-cours'),
]

# Niveaux d'alerte
ALERTE_NIVEAU_CHOICES = [
    ('info', 'Information'),
    ('alerte', 'Alerte'),
    ('critique', 'Critique'),
]

# Rôles d'utilisateurs
ROLES = ['Admin', 'Manager', 'Caissier', 'Magasinier']

# Niveaux de risque de rupture IA
RISQUE_RUPTURE = {
    'CRITIQUE': 'Rupture imminente (<= 3 jours)',
    'ELEVE': 'Risque élevé (<= 7 jours)',
    'MODERE': 'Vigilance (<= 14 jours)',
    'FAIBLE': 'Stock sécurisé (> 14 jours)',
}
