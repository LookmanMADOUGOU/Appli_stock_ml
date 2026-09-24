"""
Signaux Django pour gérer la cohérence atomique du stock et l'Audit Trail.

Prend en charge :
- Création d'une vente -> décrémente le stock et trace le mouvement VENTE
- Modification d'une vente -> calcule le delta et ajuste le stock avec traçabilité
- Suppression d'une vente -> réintègre la quantité vendue (RETOUR)
- Création d'un approvisionnement -> incrémente le stock et trace le mouvement ACHAT
- Modification d'un approvisionnement -> calcule le delta et ajuste le stock
- Suppression d'un approvisionnement -> décrémente la quantité approvisionnée (SORTIE)
- Enregistrement de l'opérateur utilisateur si disponible
"""

from django.db.models.signals import pre_save, post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction

from .models import Vente, Approvisionnement, Produit
from .services.stock_service import (
    increase_stock,
    reduce_stock,
    restore_sale,
    revert_approvisionnement,
)


@receiver(pre_save, sender=Vente)
def preparer_delta_vente(sender, instance, **kwargs):
    """Capture l'état en base de données avant enregistrement pour calculer le delta."""
    if instance.pk:
        ancien = Vente.objects.filter(pk=instance.pk).first()
        if ancien:
            instance._old_quantite = ancien.quantite
            instance._old_produit_id = ancien.produit_id
        else:
            instance._old_quantite = None
            instance._old_produit_id = None
    else:
        instance._old_quantite = None
        instance._old_produit_id = None


@receiver(post_save, sender=Vente)
def maj_stock_vente(sender, instance, created, **kwargs):
    """
    Met à jour le stock lors de la création ou modification d'une vente.
    """
    user = getattr(instance, '_current_user', None)
    ref = instance.reference_ticket or f"TCK-#{instance.pk}"

    if created:
        reduce_stock(
            instance.produit,
            instance.quantite,
            type_mouvement='VENTE',
            utilisateur=user,
            reference=ref,
            commentaire=f"Vente #{instance.pk} ({instance.quantite}x)"
        )
    else:
        old_qte = getattr(instance, '_old_quantite', None)
        old_produit_id = getattr(instance, '_old_produit_id', None)

        if old_qte is not None and old_produit_id is not None:
            if instance.produit_id == old_produit_id:
                delta = instance.quantite - old_qte
                if delta > 0:
                    reduce_stock(
                        instance.produit,
                        delta,
                        type_mouvement='VENTE',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification vente #{instance.pk} : augmentation (+{delta})"
                    )
                elif delta < 0:
                    increase_stock(
                        instance.produit,
                        abs(delta),
                        type_mouvement='RETOUR',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification vente #{instance.pk} : réduction (-{abs(delta)})"
                    )
            else:
                # Le produit associé à la vente a été modifié
                ancien_produit = Produit.objects.filter(pk=old_produit_id).first()
                if ancien_produit:
                    increase_stock(
                        ancien_produit,
                        old_qte,
                        type_mouvement='RETOUR',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification vente #{instance.pk} : retour ancien produit"
                    )
                reduce_stock(
                    instance.produit,
                    instance.quantite,
                    type_mouvement='VENTE',
                    utilisateur=user,
                    reference=ref,
                    commentaire=f"Modification vente #{instance.pk} : sortie nouveau produit"
                )


@receiver(pre_save, sender=Approvisionnement)
def preparer_delta_approvisionnement(sender, instance, **kwargs):
    """Capture l'état en base de données avant enregistrement pour calculer le delta."""
    if instance.pk:
        ancien = Approvisionnement.objects.filter(pk=instance.pk).first()
        if ancien:
            instance._old_quantite = ancien.quantite
            instance._old_produit_id = ancien.produit_id
        else:
            instance._old_quantite = None
            instance._old_produit_id = None
    else:
        instance._old_quantite = None
        instance._old_produit_id = None


@receiver(post_save, sender=Approvisionnement)
def maj_stock_approvisionnement(sender, instance, created, **kwargs):
    """
    Met à jour le stock lors de la création ou modification d'un approvisionnement.
    """
    user = getattr(instance, '_current_user', None)
    ref = f"APPRO-#{instance.pk}"

    # Mettre à jour le dernier prix d'achat du produit si spécifié
    if instance.cout_unitaire and instance.cout_unitaire > 0:
        if instance.produit.prix_achat != instance.cout_unitaire:
            instance.produit.prix_achat = instance.cout_unitaire
            instance.produit.save(update_fields=['prix_achat'])

    fournisseur_label = instance.nom_fournisseur

    if created:
        increase_stock(
            instance.produit,
            instance.quantite,
            type_mouvement='ACHAT',
            utilisateur=user,
            reference=ref,
            commentaire=f"Approvisionnement #{instance.pk} (+{instance.quantite}) - {fournisseur_label}"
        )
    else:
        old_qte = getattr(instance, '_old_quantite', None)
        old_produit_id = getattr(instance, '_old_produit_id', None)

        if old_qte is not None and old_produit_id is not None:
            if instance.produit_id == old_produit_id:
                delta = instance.quantite - old_qte
                if delta > 0:
                    increase_stock(
                        instance.produit,
                        delta,
                        type_mouvement='ACHAT',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification appro #{instance.pk} : augmentation (+{delta})"
                    )
                elif delta < 0:
                    reduce_stock(
                        instance.produit,
                        abs(delta),
                        type_mouvement='SORTIE',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification appro #{instance.pk} : réduction (-{abs(delta)})"
                    )
            else:
                ancien_produit = Produit.objects.filter(pk=old_produit_id).first()
                if ancien_produit:
                    reduce_stock(
                        ancien_produit,
                        old_qte,
                        type_mouvement='SORTIE',
                        utilisateur=user,
                        reference=ref,
                        commentaire=f"Modification appro #{instance.pk} : annulation ancien produit"
                    )
                increase_stock(
                    instance.produit,
                    instance.quantite,
                    type_mouvement='ACHAT',
                    utilisateur=user,
                    reference=ref,
                    commentaire=f"Modification appro #{instance.pk} : entrée nouveau produit"
                )


@receiver(pre_delete, sender=Vente)
def annuler_vente(sender, instance, **kwargs):
    """Restaurer le stock si une vente est supprimée."""
    user = getattr(instance, '_current_user', None)
    restore_sale(instance.produit, instance.quantite, utilisateur=user)


@receiver(pre_delete, sender=Approvisionnement)
def annuler_approvisionnement(sender, instance, **kwargs):
    """Réduire le stock si un approvisionnement est supprimé."""
    user = getattr(instance, '_current_user', None)
    revert_approvisionnement(instance.produit, instance.quantite, utilisateur=user)
