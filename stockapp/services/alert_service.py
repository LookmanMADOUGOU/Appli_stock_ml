"""
Service de gestion des alertes de rupture.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from stockapp.models import AlerteRupture, Produit


def creer_alerte_si_necessaire(produit: Produit) -> None:
    """
    Créer une alerte de rupture si le stock atteint le seuil.
    
    Args:
        produit: Instance du modèle Produit
    """
    # Vérifier s'il y a déjà une alerte active
    alerte_active = AlerteRupture.objects.filter(
        produit=produit,
        est_resolue=False
    ).exists()

    if alerte_active:
        return

    # Si le stock est en rupture, créer une alerte
    if produit.rupture:
        alerte = AlerteRupture.objects.create(
            produit=produit,
            niveau='critique' if produit.stock_actuel == 0 else 'alerte',
            message=f"Stock critique: {produit.stock_actuel} unités restantes (seuil: {produit.seuil_alerte})",
            est_resolue=False
        )
        envoyer_alerte_email(alerte)


def envoyer_alerte_email(alerte: AlerteRupture) -> bool:
    """Envoyer une notification email lors de la création d'une alerte."""
    admin_email = getattr(settings, 'ADMIN_EMAIL', None)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@stock.local')

    if not admin_email:
        return False

    subject = f"Alerte stock : {alerte.produit.nom}"
    message = (
        f"Produit : {alerte.produit.nom}\n"
        f"Stock restant : {alerte.produit.stock_actuel}\n"
        f"Message : {alerte.message}"
    )

    send_mail(subject, message, from_email, [admin_email], fail_silently=True)
    return True


def resoudre_alerte_si_necessaire(produit: Produit) -> None:
    """
    Marquer les alertes comme résolues si le stock est suffisant.
    
    Args:
        produit: Instance du modèle Produit
    """
    if not produit.rupture:
        # Marquer toutes les alertes comme résolues
        AlerteRupture.objects.filter(
            produit=produit,
            est_resolue=False
        ).update(
            est_resolue=True,
            date_resolution=timezone.now()
        )


def verifier_alertes_produit(produit: Produit) -> dict:
    """
    Vérifier l'état des alertes d'un produit.
    
    Args:
        produit: Instance du modèle Produit
        
    Returns:
        dict: Informations sur les alertes
    """
    alertes_actives = AlerteRupture.objects.filter(
        produit=produit,
        est_resolue=False
    )
    
    return {
        'a_alerte': alertes_actives.exists(),
        'nombre_alertes': alertes_actives.count(),
        'en_rupture': produit.rupture,
        'alertes': list(alertes_actives.values('niveau', 'message', 'date_creation'))
    }
