"""
Context Processors pour SMART-TECH (Phase 12).
Injecte les alertes en temps réel et le compteur de notifications
dans l'ensemble des templates du dashboard.
"""

from stockapp.services.notification_service import (
    get_notifications_pour_utilisateur,
)


def notifications_context(request):
    """
    Context processor injectant les notifications non lues et récentes
    pour l'utilisateur connecté dans la barre supérieure et les panneaux.
    """
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        unread_qs = get_notifications_pour_utilisateur(
            user=user,
            include_read=False,
            include_archived=False
        )
        unread_count = unread_qs.count()
        critical_count = unread_qs.filter(niveau='CRITICAL').count()
        recent_notifications = list(
            get_notifications_pour_utilisateur(
                user=user,
                include_read=True,
                include_archived=False,
                limit=5
            )
        )
        return {
            'unread_notifications_count': unread_count,
            'critical_notifications_count': critical_count,
            'recent_notifications': recent_notifications,
        }

    return {
        'unread_notifications_count': 0,
        'critical_notifications_count': 0,
        'recent_notifications': [],
    }
