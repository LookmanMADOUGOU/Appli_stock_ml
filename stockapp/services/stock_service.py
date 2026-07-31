"""
Service métier de gestion du stock pour les ventes et les approvisionnements.
"""

from django.db import transaction
from stockapp.models import Produit
from .alert_service import creer_alerte_si_necessaire, resoudre_alerte_si_necessaire


def reduce_stock(produit: Produit, quantite: int) -> int:
    """Réduire le stock sans jamais passer sous zéro."""
    if quantite < 0:
        raise ValueError('La quantité de vente doit être positive.')

    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        nouvelle_valeur = max(produit.stock_actuel - quantite, 0)
        produit.stock_actuel = nouvelle_valeur
        produit.save(update_fields=['stock_actuel'])

        if produit.rupture:
            creer_alerte_si_necessaire(produit)
        else:
            resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel


def increase_stock(produit: Produit, quantite: int) -> int:
    """Augmenter le stock de livraison."""
    if quantite < 0:
        raise ValueError('La quantité d\'approvisionnement doit être positive.')

    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        produit.stock_actuel += quantite
        produit.save(update_fields=['stock_actuel'])

        resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel


def restore_sale(produit: Produit, quantite: int) -> int:
    """Restaurer le stock lors de l'annulation d'une vente."""
    if quantite < 0:
        raise ValueError('La quantité de vente à restaurer doit être positive.')
    return increase_stock(produit, quantite)


def revert_approvisionnement(produit: Produit, quantite: int) -> int:
    """Réduire le stock lors de l'annulation d'un approvisionnement."""
    if quantite < 0:
        raise ValueError('La quantité d\'approvisionnement à annuler doit être positive.')

    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit.pk)
        produit.stock_actuel = max(produit.stock_actuel - quantite, 0)
        produit.save(update_fields=['stock_actuel'])

        if produit.rupture:
            creer_alerte_si_necessaire(produit)
        else:
            resoudre_alerte_si_necessaire(produit)

    return produit.stock_actuel
