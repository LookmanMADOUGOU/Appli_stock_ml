"""
Service de gestion des alertes, notifications instantanées et résumés journaliers.
"""

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from stockapp.models import AlerteRupture, Produit, Vente

logger = logging.getLogger(__name__)


def creer_alerte_si_necessaire(produit: Produit) -> None:
    """
    Créer une alerte de rupture si le stock atteint le seuil.
    """
    alerte_active = AlerteRupture.objects.filter(
        produit=produit,
        est_resolue=False
    ).exists()

    if alerte_active:
        return

    if produit.rupture:
        alerte = AlerteRupture.objects.create(
            produit=produit,
            niveau='critique' if produit.stock_actuel == 0 else 'alerte',
            message=f"Stock critique: {produit.stock_actuel} unités restantes (seuil: {produit.seuil_alerte})",
            est_resolue=False
        )
        envoyer_notification_instantanee_critique(produit, alerte)


def envoyer_notification_instantanee_critique(produit: Produit, alerte: AlerteRupture = None) -> dict:
    """
    Envoie une notification instantanée multi-canal (Email + WhatsApp/SMS simulation)
    lorsqu'un produit franchit son seuil critique.
    """
    admin_email = getattr(settings, 'ADMIN_EMAIL', None) or 'admin@stockapp.local'
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@stockapp.local')
    whatsapp_number = getattr(settings, 'WHATSAPP_ADMIN_NUMBER', '+229 00 00 00 00')

    subject = f"🚨 ALERTE CRITIQUE STOCK : {produit.nom}"
    body = (
        f"🚨 ALERTE STOCK EN TEMPS RÉEL\n"
        f"----------------------------------------\n"
        f"Produit : {produit.nom} (Réf: {produit.reference})\n"
        f"Stock Actuel : {produit.stock_actuel} unités\n"
        f"Seuil d'Alerte : {produit.seuil_alerte} unités\n"
        f"Statut : {'RUPTURE TOTALE' if produit.stock_actuel == 0 else 'SEUIL FRANCHI'}\n\n"
        f"Action conseillée : Veuillez effectuer un réapprovisionnement."
    )

    # 1. Email
    email_sent = False
    try:
        send_mail(subject, body, from_email, [admin_email], fail_silently=True)
        email_sent = True
    except Exception as e:
        logger.error(f"Erreur envoi email alerte: {e}")

    # 2. Simulation Push / WhatsApp / SMS (Console / Webhook)
    logger.info(f"[NOTIFICATION WHATSAPP/SMS -> {whatsapp_number}] {body}")

    return {
        'email_sent': email_sent,
        'whatsapp_simulated': True,
        'produit_nom': produit.nom,
    }


def generer_et_envoyer_resume_journalier(target_date=None) -> dict:
    """
    Génère et envoie le résumé quotidien du Chiffre d'Affaires et du Bénéfice Net
    à l'administration/gérant (Email + WhatsApp/SMS simulation).
    """
    if target_date is None:
        target_date = timezone.now().date()

    ventes_jour = Vente.objects.filter(date_vente__date=target_date).select_related('produit')

    chiffre_affaires = sum(v.prix_total for v in ventes_jour)
    benefice_net = sum(v.benefice_total for v in ventes_jour)
    total_articles = sum(v.quantite for v in ventes_jour)
    nb_transactions = ventes_jour.count()

    # Top Produit du jour
    top_produit_name = "Aucune vente"
    top_qte = 0
    if ventes_jour.exists():
        produits_summary = {}
        for v in ventes_jour:
            p_nom = v.produit.nom
            produits_summary[p_nom] = produits_summary.get(p_nom, 0) + v.quantite
        top_produit_name = max(produits_summary, key=produits_summary.get)
        top_qte = produits_summary[top_produit_name]

    alertes_actives_count = AlerteRupture.objects.filter(est_resolue=False).count()

    subject = f"📊 Bilan Journalier {target_date.strftime('%d/%m/%Y')} — Stock App"
    body = (
        f"📊 RÉSUMÉ JOURNALIER DE CA & BÉNÉFICE ({target_date.strftime('%d/%m/%Y')})\n"
        f"--------------------------------------------------\n"
        f"💰 Chiffre d'Affaires : {chiffre_affaires:,.2f} FCFA/€\n"
        f"📈 Bénéfice Net Total : {benefice_net:,.2f} FCFA/€\n"
        f"📦 Volume Vendu : {total_articles} articles ({nb_transactions} transactions)\n"
        f"🏆 Top Vente du Jour : {top_produit_name} ({top_qte} unités)\n"
        f"🚨 Alertes Stock Actives : {alertes_actives_count} produit(s)\n"
        f"--------------------------------------------------\n"
        f"Rapport généré automatiquement par Gestion Stock IA."
    )

    admin_email = getattr(settings, 'ADMIN_EMAIL', None) or 'admin@stockapp.local'
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@stockapp.local')
    whatsapp_number = getattr(settings, 'WHATSAPP_ADMIN_NUMBER', '+229 00 00 00 00')

    email_sent = False
    try:
        send_mail(subject, body, from_email, [admin_email], fail_silently=True)
        email_sent = True
    except Exception as e:
        logger.error(f"Erreur envoi email résumé: {e}")

    logger.info(f"[RÉSUMÉ WHATSAPP/SMS -> {whatsapp_number}]\n{body}")

    return {
        'date': target_date.strftime('%Y-%m-%d'),
        'chiffre_affaires': chiffre_affaires,
        'benefice_net': benefice_net,
        'total_articles': total_articles,
        'nb_transactions': nb_transactions,
        'top_produit': top_produit_name,
        'alertes_actives': alertes_actives_count,
        'email_sent': email_sent,
        'body': body
    }


def resoudre_alerte_si_necessaire(produit: Produit) -> None:
    """
    Marquer les alertes comme résolues si le stock est suffisant.
    """
    if not produit.rupture:
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
