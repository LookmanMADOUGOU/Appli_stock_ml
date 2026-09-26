"""
Permissions et gestion des rôles pour SMART-TECH :
- Administrateur : Sécurité, Rôles, Sauvegardes & Accès Absolu à toutes les pages
- Manager : Pilotage, Finances, Trésorerie, Analytics & Intelligence ML
- Magasinier : Gestion du Stock, Inventaires, Produits & Approvisionnements
- Caissier : Point de Vente & Caisse POS, Enregistrement des Ventes, Clôtures & Reçus
"""

from functools import wraps
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import permissions


# ==================== CONSTANTES ET CONFIGURATION DES RÔLES ====================

ROLE_ADMIN = 'Admin'
ROLE_MANAGER = 'Manager'
ROLE_MAGASINIER = 'Magasinier'
ROLE_CAISSIER = 'Caissier'

ROLES_CHOICES = [
    (ROLE_ADMIN, 'Administrateur : Sécurité, Rôles & Sauvegardes'),
    (ROLE_MANAGER, 'Manager : Pilotage, Finances & Intelligence ML'),
    (ROLE_MAGASINIER, 'Magasinier : Gestion du Stock & Approvisionnements'),
    (ROLE_CAISSIER, 'Caissier : Point de Vente & Caisse POS'),
]

ROLES_CONFIG = {
    ROLE_ADMIN: {
        'code': ROLE_ADMIN,
        'label': 'Administrateur',
        'badge_class': 'bg-purple-100 text-purple-800 border-purple-300',
        'badge_dark_class': 'bg-purple-950/40 text-purple-300 border-purple-500/40',
        'icon': 'fa-user-shield',
        'color': 'purple',
        'scope': 'Accès total à l’ensemble des pages, sécurité, utilisateurs et sauvegardes',
        'home_url_name': 'stockapp:dashboard',
    },
    ROLE_MANAGER: {
        'code': ROLE_MANAGER,
        'label': 'Manager',
        'badge_class': 'bg-cyan-100 text-cyan-800 border-cyan-300',
        'badge_dark_class': 'bg-cyan-950/40 text-cyan-300 border-cyan-500/40',
        'icon': 'fa-user-tie',
        'color': 'cyan',
        'scope': 'Pilotage stratégique, Finances, Trésorerie, Analytics, Prévisions IA & Rapports',
        'home_url_name': 'stockapp:dashboard',
    },
    ROLE_MAGASINIER: {
        'code': ROLE_MAGASINIER,
        'label': 'Magasinier',
        'badge_class': 'bg-amber-100 text-amber-800 border-amber-300',
        'badge_dark_class': 'bg-amber-950/40 text-amber-300 border-amber-500/40',
        'icon': 'fa-boxes',
        'color': 'amber',
        'scope': 'Stock, Inventaire, Mouvements, Produits, Catégories, Approvisionnements & Fournisseurs',
        'home_url_name': 'stockapp:stock-inventaire',
    },
    ROLE_CAISSIER: {
        'code': ROLE_CAISSIER,
        'label': 'Caissier',
        'badge_class': 'bg-emerald-100 text-emerald-800 border-emerald-300',
        'badge_dark_class': 'bg-emerald-950/40 text-emerald-300 border-emerald-500/40',
        'icon': 'fa-cash-register',
        'color': 'emerald',
        'scope': 'Caisse POS tactile, Ventes, Reçus & Factures, Clôtures journalières & Clients',
        'home_url_name': 'stockapp:caisse-pos',
    },
}


# ==================== HELPERS ET DÉTERMINATION DU RÔLE ====================

def get_user_role_code(user) -> str:
    """
    Détermine le code technique du rôle d'un utilisateur ('Admin', 'Manager', 'Magasinier', 'Caissier').
    """
    if not user or not user.is_authenticated:
        return 'Guest'

    if user.is_superuser:
        return ROLE_ADMIN

    user_groups = set(user.groups.values_list('name', flat=True))
    if ROLE_ADMIN in user_groups:
        return ROLE_ADMIN
    if ROLE_MANAGER in user_groups:
        return ROLE_MANAGER
    if ROLE_MAGASINIER in user_groups:
        return ROLE_MAGASINIER
    if ROLE_CAISSIER in user_groups:
        return ROLE_CAISSIER

    # Fallback pour compatibilité staff
    if user.is_staff:
        return ROLE_MANAGER

    return 'Utilisateur'


def get_user_primary_role(user) -> str:
    """
    Détermine l'intitulé lisible du rôle principal de l'utilisateur :
    'Administrateur', 'Manager', 'Magasinier', 'Caissier' ou 'Invité'.
    """
    if not user or not user.is_authenticated:
        return "Invité"

    code = get_user_role_code(user)
    if code in ROLES_CONFIG:
        return ROLES_CONFIG[code]['label']
    return "Utilisateur"


def get_user_home_url(user) -> str:
    """
    Détermine l'URL de l'espace de travail correspondant au profil de l'utilisateur.
    """
    if not user or not user.is_authenticated:
        return '/login/'

    code = get_user_role_code(user)
    if code == ROLE_CAISSIER:
        return reverse('stockapp:caisse-pos')
    elif code == ROLE_MAGASINIER:
        return reverse('stockapp:stock-inventaire')
    else:
        return reverse('stockapp:dashboard')


def assign_user_role(user, role_code: str):
    """
    Attribue un rôle de façon atomique et propre à un utilisateur Django :
    - Réinitialise les anciens groupes de rôles
    - Ajoute le groupe correspondant ('Admin', 'Manager', 'Magasinier', 'Caissier')
    - Ajuste les flags is_staff et is_superuser
    """
    from django.contrib.auth.models import Group

    # S'assurer de l'existence des groupes
    for r in [ROLE_ADMIN, ROLE_MANAGER, ROLE_MAGASINIER, ROLE_CAISSIER]:
        Group.objects.get_or_create(name=r)

    # Retrait des groupes de rôles existants
    user.groups.remove(*Group.objects.filter(name__in=[ROLE_ADMIN, ROLE_MANAGER, ROLE_MAGASINIER, ROLE_CAISSIER]))

    group = Group.objects.get(name=role_code)
    user.groups.add(group)

    if role_code == ROLE_ADMIN:
        user.is_staff = True
        user.is_superuser = True
    elif role_code == ROLE_MANAGER:
        user.is_staff = True
        user.is_superuser = False
    else:
        # Caissier et Magasinier sont restreints à leur portail métier SMART-TECH
        user.is_staff = False
        user.is_superuser = False

    user.save(update_fields=['is_staff', 'is_superuser'])


def user_has_role(user, *role_names) -> bool:
    """
    Vérifie si l'utilisateur possède l'un des rôles spécifiés.
    RÈGLE MAÎTRESSE : L'Administrateur a TOUS les droits d'accès sur TOUTES les pages.
    """
    if not user or not user.is_authenticated:
        return False

    # L'administrateur a un accès absolu à l'ensemble du système
    if user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists():
        return True

    user_code = get_user_role_code(user)

    # Conversion des variantes autorisées ('Admin', 'Administrateur', etc.)
    normalized_allowed = set()
    for r in role_names:
        if r in [ROLE_ADMIN, 'Administrateur']:
            normalized_allowed.add(ROLE_ADMIN)
        elif r == ROLE_MANAGER:
            normalized_allowed.add(ROLE_MANAGER)
        elif r == ROLE_MAGASINIER:
            normalized_allowed.add(ROLE_MAGASINIER)
        elif r == ROLE_CAISSIER:
            normalized_allowed.add(ROLE_CAISSIER)
        else:
            normalized_allowed.add(r)

    return user_code in normalized_allowed


# ==================== DÉCORATEURS ET RESTRICTION D'ACCÈS ====================

def role_required(*allowed_roles):
    """
    Décorateur strict de vue Django pour restreindre l'accès à un ou plusieurs rôles.
    L'Administrateur a toujours un accès absolu et complet.
    En cas d'accès non autorisé :
    - Enregistrement immédiat dans le JournalAudit
    - Message d'alerte explicite
    - Redirection vers l'espace naturel du profil de l'utilisateur
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if user_has_role(request.user, *allowed_roles):
                return view_func(request, *args, **kwargs)

            user_role = get_user_primary_role(request.user)
            allowed_labels = []
            for r in allowed_roles:
                if r in ROLES_CONFIG:
                    allowed_labels.append(ROLES_CONFIG[r]['label'])
                else:
                    allowed_labels.append(r)

            # Traçabilité dans le journal d'audit
            try:
                from stockapp.models import JournalAudit
                JournalAudit.log_action(
                    utilisateur=request.user,
                    action='CONNEXION',
                    module='SECURITE',
                    objet_concerne=request.path[:255],
                    description=(
                        f"Accès refusé : L'utilisateur '{request.user.username}' (Profil: {user_role}) "
                        f"a tenté d'accéder à la page '{request.path}'. Rôles requis: {', '.join(allowed_labels)}."
                    ),
                    request=request
                )
            except Exception:
                pass

            # Requête API / Ajax
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'api' in request.path:
                return JsonResponse({
                    'error': 'Accès non autorisé',
                    'detail': f"Votre profil ({user_role}) ne vous autorise pas à accéder à cette ressource. Rôles requis : {', '.join(allowed_labels)}."
                }, status=403)

            # Requête Web standard avec redirection propre
            messages.error(
                request,
                f"Accès refusé : Votre profil ({user_role}) ne vous autorise pas à accéder à cette page ({request.path})."
            )
            return redirect(get_user_home_url(request.user))

        return _wrapped_view
    return decorator


# ==================== PERMISSIONS REST FRAMEWORK (API) ====================

class IsAdminUserRole(permissions.BasePermission):
    """
    Permission API accordée uniquement aux administrateurs.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_superuser or
                request.user.groups.filter(name=ROLE_ADMIN).exists()
            )
        )


class IsManagerUserRole(permissions.BasePermission):
    """
    Permission API pour les Managers et Administrateurs.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_superuser or
                request.user.groups.filter(name__in=[ROLE_ADMIN, ROLE_MANAGER]).exists()
            )
        )


class IsCashierUserRole(permissions.BasePermission):
    """
    Permission API pour les Caissiers et Administrateurs.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_superuser or
                request.user.groups.filter(name__in=[ROLE_ADMIN, ROLE_CAISSIER, ROLE_MANAGER]).exists()
            )
        )


class IsStockManagerUserRole(permissions.BasePermission):
    """
    Permission API pour les Magasiniers et Administrateurs.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_superuser or
                request.user.groups.filter(name__in=[ROLE_ADMIN, ROLE_MAGASINIER, ROLE_MANAGER]).exists()
            )
        )

