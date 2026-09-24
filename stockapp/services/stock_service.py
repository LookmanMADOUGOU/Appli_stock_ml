"""
Service métier centralisé de gestion du stock et traçabilité des mouvements (Audit Trail).

Gère tous les mouvements de stock avec enregistrement automatique dans MouvementStock:
- Entrées / Achats
- Sorties / Ventes
- Retours
- Ajustements manuels & inventaire
- Qualification du statut de stock (RUPTURE, STOCK FAIBLE, SURSTOCK, STOCK NORMAL)
"""

from django.db import transaction
from stockapp.models import Produit, MouvementStock
from .alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire


def qualifier_statut_stock(produit: Produit) -> str:
    """
    Logique métier centralisée et réutilisable pour qualifier le statut du stock :
    - stock == 0 → RUPTURE
    - stock <= seuil_alerte → STOCK FAIBLE
    - stock >= stock_maximum → SURSTOCK
    - sinon → STOCK NORMAL
    """
    return produit.statut_stock


def create_mouvement_stock(produit: Produit, quantite: int, type_mouvement: str, stock_avant: int, stock_apres: int, utilisateur=None, reference: str = '', commentaire: str = None) -> MouvementStock:
    """
    Crée un enregistrement d'historique MouvementStock.
    """
    return MouvementStock.objects.create(
        produit=produit,
        quantite=quantite,
        type_mouvement=type_mouvement,
        stock_avant=stock_avant,
        stock_apres=stock_apres,
        utilisateur=utilisateur,
        reference=reference,
        commentaire=commentaire or f"Mouvement {type_mouvement} de {quantite} unité(s)"
    )


def reduce_stock(produit: Produit, quantite: int, type_mouvement: str = 'VENTE', utilisateur=None, reference: str = '', commentaire: str = None) -> int:
    """Réduire le stock sans jamais passer sous zéro et enregistrer le mouvement."""
    if quantite < 0:
        raise ValueError('La quantité doit être positive.')

    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        stock_avant = produit.stock_actuel
        stock_apres = max(stock_avant - quantite, 0)
        produit.stock_actuel = stock_apres
        produit.save(update_fields=['stock_actuel'])

        create_mouvement_stock(
            produit=produit,
            quantite=quantite,
            type_mouvement=type_mouvement,
            stock_avant=stock_avant,
            stock_apres=stock_apres,
            utilisateur=utilisateur,
            reference=reference,
            commentaire=commentaire
        )

        if produit.rupture:
            creer_alerte_si_necessaire(produit)
        else:
            resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel


def increase_stock(produit: Produit, quantite: int, type_mouvement: str = 'ACHAT', utilisateur=None, reference: str = '', commentaire: str = None) -> int:
    """Augmenter le stock et enregistrer le mouvement."""
    if quantite < 0:
        raise ValueError('La quantité doit être positive.')

    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        stock_avant = produit.stock_actuel
        stock_apres = stock_avant + quantite
        produit.stock_actuel = stock_apres
        produit.save(update_fields=['stock_actuel'])

        create_mouvement_stock(
            produit=produit,
            quantite=quantite,
            type_mouvement=type_mouvement,
            stock_avant=stock_avant,
            stock_apres=stock_apres,
            utilisateur=utilisateur,
            reference=reference,
            commentaire=commentaire
        )

        resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel


def restore_sale(produit: Produit, quantite: int, utilisateur=None) -> int:
    """Restaurer le stock lors de l'annulation d'une vente."""
    if quantite < 0:
        raise ValueError('La quantité de vente à restaurer doit être positive.')
    return increase_stock(produit, quantite, type_mouvement='RETOUR', utilisateur=utilisateur, commentaire="Annulation de vente")


def revert_approvisionnement(produit: Produit, quantite: int, utilisateur=None) -> int:
    """Réduire le stock lors de l'annulation d'un approvisionnement."""
    if quantite < 0:
        raise ValueError('La quantité à annuler doit être positive.')

    return reduce_stock(produit, quantite, type_mouvement='SORTIE', utilisateur=utilisateur, commentaire="Annulation d'approvisionnement")


def ajuster_stock_manuel(produit: Produit, nouveau_stock: int, utilisateur=None, motif: str = '') -> int:
    """Ajustement manuel ou régularisation d'inventaire."""
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        stock_avant = produit.stock_actuel
        diff = nouveau_stock - stock_avant
        type_mouvement = 'AJUSTEMENT' if diff >= 0 else 'INVENTAIRE'

        produit.stock_actuel = max(nouveau_stock, 0)
        produit.save(update_fields=['stock_actuel'])

        create_mouvement_stock(
            produit=produit,
            quantite=abs(diff),
            type_mouvement=type_mouvement,
            stock_avant=stock_avant,
            stock_apres=produit.stock_actuel,
            utilisateur=utilisateur,
            commentaire=motif or f"Ajustement d'inventaire [{stock_avant} -> {produit.stock_actuel}]"
        )

        if produit.rupture:
            creer_alerte_si_necessaire(produit)
        else:
            resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel
