"""
Signaux Django pour gérer les modifications de stock.

Au lieu de modifier le stock directement dans save(),
on utilise les signaux pour maintenir la cohérence des données.
"""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction

from .models import Vente, Approvisionnement
from .services.stock_service import (
    increase_stock,
    reduce_stock,
    restore_sale,
    revert_approvisionnement,
)


@receiver(post_save, sender=Vente)
def maj_stock_vente(sender, instance, created, **kwargs):
    """
    Réduire le stock quand une vente est créée.
    """
    if created:
        reduce_stock(instance.produit, instance.quantite)


@receiver(post_save, sender=Approvisionnement)
def maj_stock_approvisionnement(sender, instance, created, **kwargs):
    """
    Augmenter le stock quand un approvisionnement est créé.
    """
    if created:
        increase_stock(instance.produit, instance.quantite)


@receiver(pre_delete, sender=Vente)
def annuler_vente(sender, instance, **kwargs):
    """
    Restaurer le stock si une vente est supprimée.
    """
    restore_sale(instance.produit, instance.quantite)


@receiver(pre_delete, sender=Approvisionnement)
def annuler_approvisionnement(sender, instance, **kwargs):
    """
    Réduire le stock si un approvisionnement est supprimé.
    """
    revert_approvisionnement(instance.produit, instance.quantite)
