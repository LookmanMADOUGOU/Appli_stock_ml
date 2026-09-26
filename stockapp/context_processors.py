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


def user_role_context(request):
    """
    Context processor injectant les données de rôle, de profil et de permissions
    dans l'ensemble des templates SMART-TECH.
    Permet à la barre latérale et au topbar de s'adapter dynamiquement
    au profil précis de l'utilisateur connecté.
    """
    from stockapp.permissions import (
        get_user_primary_role,
        get_user_role_code,
        get_user_home_url,
        ROLES_CONFIG,
        ROLE_ADMIN,
        ROLE_MANAGER,
        ROLE_MAGASINIER,
        ROLE_CAISSIER,
    )

    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        role_code = get_user_role_code(user)
        role_label = get_user_primary_role(user)
        config = ROLES_CONFIG.get(role_code, {})
        is_admin = (role_code == ROLE_ADMIN)

        return {
            'user_role_code': role_code,
            'user_role_label': role_label,
            'user_role_config': config,
            'user_home_url': get_user_home_url(user),

            # Drapeaux d'autorisation pour les modules
            'is_role_admin': is_admin,
            'is_role_manager': is_admin or (role_code == ROLE_MANAGER),
            'is_role_magasinier': is_admin or (role_code == ROLE_MAGASINIER),
            'is_role_caissier': is_admin or (role_code == ROLE_CAISSIER),

            # Drapeaux stricts de profil
            'strictly_admin': is_admin,
            'strictly_manager': (role_code == ROLE_MANAGER),
            'strictly_magasinier': (role_code == ROLE_MAGASINIER),
            'strictly_caissier': (role_code == ROLE_CAISSIER),
        }

    return {
        'user_role_code': 'Guest',
        'user_role_label': 'Invité',
        'user_role_config': {},
        'user_home_url': '/login/',
        'is_role_admin': False,
        'is_role_manager': False,
        'is_role_magasinier': False,
        'is_role_caissier': False,
        'strictly_admin': False,
        'strictly_manager': False,
        'strictly_magasinier': False,
        'strictly_caissier': False,
    }

