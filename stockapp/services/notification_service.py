"""
Service de gestion proactive des alertes et notifications internes SMART-TECH (Phase 12).
Surveille en continu :
- Ruptures de stock et seuils critiques
- Dettes fournisseurs
- Créances clients
- Anomalies de caisse (Rapports Z)
- Événements système
"""

import logging
from decimal import Decimal
from django.utils import timezone
from django.db.models import F, Q
from django.contrib.auth import get_user_model

from stockapp.models import (
    Notification,
    Produit,
    Client,
    Fournisseur,
    ClotureCaisse,
    JournalAudit,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def creer_notification(
    titre: str,
    message: str,
    type_notification: str = 'SYSTEME',
    niveau: str = 'INFO',
    lien: str = None,
    cle_unicite: str = None,
    destinataire=None,
) -> Notification:
    """
    Crée une notification ou met à jour une notification active existante avec la même clé d'unicité.
    """
    if cle_unicite:
        existante = Notification.objects.filter(cle_unicite=cle_unicite, est_archivee=False).first()
        if existante:
            existante.titre = titre
            existante.message = message
            existante.niveau = niveau
            if lien:
                existante.lien = lien
            existante.save()
            return existante

    notification = Notification.objects.create(
        titre=titre,
        message=message,
        type_notification=type_notification,
        niveau=niveau,
        lien=lien,
        cle_unicite=cle_unicite,
        destinataire=destinataire,
    )
    return notification


def generer_alertes_proactives() -> dict:
    """
    Scanne les données métier pour identifier les situations à risque
    et génère automatiquement les notifications proactives correspondantes.
    """
    creations_count = 0

    # 1. Ruptures de stock et seuils d'alerte
    produits_en_alerte = Produit.objects.filter(
        statut='ACTIF',
        stock_actuel__lte=F('seuil_alerte')
    )

    for p in produits_en_alerte:
        if p.stock_actuel <= 0:
            cle = f"stock_rupture_{p.id}"
            titre = f"Rupture totale : {p.nom}"
            message = (
                f"Le produit {p.nom} (Réf: {p.reference}) est en rupture totale (0 unité en stock). "
                f"Réapprovisionnement immédiat conseillé."
            )
            niveau = 'CRITICAL'
            type_notif = 'STOCK_RUPTURE'
            lien = "/dashboard/approvisionnements/bon-de-commande/"
        else:
            cle = f"stock_faible_{p.id}"
            titre = f"Stock faible : {p.nom}"
            message = (
                f"Stock critique : il ne reste que {p.stock_actuel} unité(s) pour {p.nom} "
                f"(seuil d'alerte fixé à {p.seuil_alerte})."
            )
            niveau = 'WARNING'
            type_notif = 'STOCK_FAIBLE'
            lien = "/dashboard/stock/"

        if not Notification.objects.filter(cle_unicite=cle, est_archivee=False).exists():
            creer_notification(
                titre=titre,
                message=message,
                type_notification=type_notif,
                niveau=niveau,
                lien=lien,
                cle_unicite=cle,
            )
            creations_count += 1

    # Auto-archivage des alertes de stock pour les produits redevenus normaux
    produits_ok_ids = list(
        Produit.objects.filter(stock_actuel__gt=F('seuil_alerte')).values_list('id', flat=True)
    )
    if produits_ok_ids:
        cles_a_archiver = [f"stock_rupture_{pid}" for pid in produits_ok_ids] + [
            f"stock_faible_{pid}" for pid in produits_ok_ids
        ]
        Notification.objects.filter(
            cle_unicite__in=cles_a_archiver,
            est_archivee=False
        ).update(est_archivee=True, est_lue=True)

    # 2. Dettes fournisseurs
    fournisseurs_endettes = Fournisseur.objects.filter(dette_fournisseur__gt=Decimal('0.00'))
    for f in fournisseurs_endettes:
        cle = f"dette_fournisseur_{f.id}"
        niveau = 'CRITICAL' if f.dette_fournisseur >= Decimal('50000.00') else 'WARNING'
        titre = f"Dette fournisseur : {f.nom}"
        message = (
            f"Solde impayé de {f.dette_fournisseur:,.0f} FCFA auprès de {f.nom}. "
            f"Vérifiez les échéances de règlement."
        )
        if not Notification.objects.filter(cle_unicite=cle, est_archivee=False).exists():
            creer_notification(
                titre=titre,
                message=message,
                type_notification='DETTE_FOURNISSEUR',
                niveau=niveau,
                lien=f"/dashboard/fournisseurs/{f.id}/",
                cle_unicite=cle,
            )
            creations_count += 1

    # 3. Créances clients
    clients_debiteurs = Client.objects.filter(solde_credit__gt=Decimal('0.00'))
    for c in clients_debiteurs:
        cle = f"creance_client_{c.id}"
        niveau = 'CRITICAL' if c.solde_credit >= Decimal('50000.00') else 'WARNING'
        titre = f"Créance client : {c.nom}"
        message = (
            f"Le client {c.nom} dispose d'un découvert / solde à recouvrer de {c.solde_credit:,.0f} FCFA."
        )
        if not Notification.objects.filter(cle_unicite=cle, est_archivee=False).exists():
            creer_notification(
                titre=titre,
                message=message,
                type_notification='CREANCE_CLIENT',
                niveau=niveau,
                lien=f"/dashboard/clients/{c.id}/",
                cle_unicite=cle,
            )
            creations_count += 1

    # 4. Anomalies de caisse (Rapports Z déficitaires ou excédentaires non résolus)
    clotures_anormales = ClotureCaisse.objects.filter(
        statut_conformite__in=['DEFICIT', 'EXCEDENT']
    ).order_by('-date_cloture')[:10]

    for cl in clotures_anormales:
        cle = f"anomalie_caisse_{cl.id}"
        niveau = 'CRITICAL' if cl.statut_conformite == 'DEFICIT' else 'WARNING'
        titre = f"Écart de caisse : {cl.reference}"
        message = (
            f"Session de caisse #{cl.reference} ({cl.caissier.username}) clôturée avec un "
            f"{cl.get_statut_conformite_display().lower()} de {abs(cl.ecart_total):,.0f} FCFA. Audit recommandé."
        )
        if not Notification.objects.filter(cle_unicite=cle, est_archivee=False).exists():
            creer_notification(
                titre=titre,
                message=message,
                type_notification='ANOMALIE_CAISSE',
                niveau=niveau,
                lien=f"/caisse/clotures/{cl.id}/",
                cle_unicite=cle,
            )
            creations_count += 1

    total_actives = Notification.objects.filter(est_archivee=False).count()
    return {
        'creations_count': creations_count,
        'total_actives': total_actives,
    }


def get_notifications_pour_utilisateur(
    user=None,
    include_read: bool = True,
    include_archived: bool = False,
    type_filtre: str = None,
    niveau_filtre: str = None,
    limit: int = None,
):
    """
    Récupère les notifications visibles pour un utilisateur donné ou pour toute l'équipe.
    """
    qs = Notification.objects.all()

    if user and user.is_authenticated:
        qs = qs.filter(Q(destinataire=user) | Q(destinataire__isnull=True))
    else:
        qs = qs.filter(destinataire__isnull=True)

    if not include_archived:
        qs = qs.filter(est_archivee=False)

    if not include_read:
        qs = qs.filter(est_lue=False)

    if type_filtre:
        qs = qs.filter(type_notification=type_filtre)

    if niveau_filtre:
        qs = qs.filter(niveau=niveau_filtre)

    if limit:
        qs = qs[:limit]

    return qs


def marquer_notification_comme_lue(notification_id: int, user=None) -> bool:
    """
    Marque une notification spécifique comme lue.
    """
    try:
        notif = Notification.objects.get(pk=notification_id)
        notif.marquer_comme_lue()
        return True
    except Notification.DoesNotExist:
        return False


def marquer_toutes_comme_lues(user=None) -> int:
    """
    Marque toutes les notifications non lues comme lues pour un utilisateur.
    """
    qs = Notification.objects.filter(est_lue=False)
    if user and user.is_authenticated:
        qs = qs.filter(Q(destinataire=user) | Q(destinataire__isnull=True))
    else:
        qs = qs.filter(destinataire__isnull=True)

    now = timezone.now()
    count = qs.update(est_lue=True, date_lecture=now)
    return count


def archiver_notification(notification_id: int, user=None) -> bool:
    """
    Archive une notification.
    """
    try:
        notif = Notification.objects.get(pk=notification_id)
        notif.archiver()
        return True
    except Notification.DoesNotExist:
        return False


def get_statistiques_notifications(user=None) -> dict:
    """
    Calcule les métriques globales du centre de notifications.
    """
    qs = Notification.objects.all()
    if user and user.is_authenticated:
        qs = qs.filter(Q(destinataire=user) | Q(destinataire__isnull=True))
    else:
        qs = qs.filter(destinataire__isnull=True)

    total_actives = qs.filter(est_archivee=False).count()
    non_lues = qs.filter(est_archivee=False, est_lue=False).count()
    critiques = qs.filter(est_archivee=False, niveau='CRITICAL').count()
    archivees = qs.filter(est_archivee=True).count()

    par_type = {
        'stock': qs.filter(est_archivee=False, type_notification__in=['STOCK_RUPTURE', 'STOCK_FAIBLE']).count(),
        'dettes': qs.filter(est_archivee=False, type_notification='DETTE_FOURNISSEUR').count(),
        'creances': qs.filter(est_archivee=False, type_notification='CREANCE_CLIENT').count(),
        'caisse': qs.filter(est_archivee=False, type_notification='ANOMALIE_CAISSE').count(),
        'systeme': qs.filter(est_archivee=False, type_notification='SYSTEME').count(),
    }

    return {
        'total_actives': total_actives,
        'non_lues': non_lues,
        'critiques': critiques,
        'archivees': archivees,
        'par_type': par_type,
    }
