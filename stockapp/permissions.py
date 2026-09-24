"""
Permissions et gestion des rôles pour SMART-TECH (Admin, Manager, Caissier, Magasinier).
"""

from rest_framework import permissions


class IsAdminUserRole(permissions.BasePermission):
    """
    Permission accordée uniquement aux administrateurs (is_superuser ou membre du groupe 'Admin').
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_superuser or
                request.user.groups.filter(name='Admin').exists()
            )
        )


class IsManagerUserRole(permissions.BasePermission):
    """
    Permission pour les Managers, Administrateurs et Staff.
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_staff or
                request.user.groups.filter(name__in=['Admin', 'Manager']).exists()
            )
        )


class IsCashierUserRole(permissions.BasePermission):
    """
    Permission pour les Caissiers (Ventes, Consultation produits, Tickets).
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_staff or
                request.user.groups.filter(name__in=['Admin', 'Manager', 'Caissier']).exists()
            )
        )


class IsStockManagerUserRole(permissions.BasePermission):
    """
    Permission pour les Magasiniers (Gestion stock, Approvisionnements, Ajustements).
    """

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_staff or
                request.user.groups.filter(name__in=['Admin', 'Manager', 'Magasinier']).exists()
            )
        )


# ==================== DÉCORATEURS ET HELPERS VUES DJANGO (PHASE 9) ====================

from functools import wraps
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


def user_has_role(user, *role_names) -> bool:
    """
    Vérifie si l'utilisateur possède l'un des rôles spécifiés (ou les privilèges superuser/staff).
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if user.is_staff and any(r in role_names for r in ['Manager', 'Magasinier', 'Caissier']):
        return True

    return user.groups.filter(name__in=role_names).exists()


def get_user_primary_role(user) -> str:
    """
    Détermine l'intitulé lisible du rôle principal de l'utilisateur.
    """
    if not user or not user.is_authenticated:
        return "Invité"
    if user.is_superuser:
        return "Administrateur"

    user_groups = set(user.groups.values_list('name', flat=True))
    if 'Admin' in user_groups:
        return "Administrateur"
    if 'Manager' in user_groups or user.is_staff:
        return "Manager"
    if 'Magasinier' in user_groups:
        return "Magasinier"
    if 'Caissier' in user_groups:
        return "Caissier"

    return "Utilisateur"


def role_required(*allowed_roles):
    """
    Décorateur de vue Django standard pour restreindre l'accès à un ou plusieurs rôles :
    @role_required('Admin')
    @role_required('Admin', 'Manager')
    @role_required('Admin', 'Manager', 'Caissier')
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if user_has_role(request.user, *allowed_roles):
                return view_func(request, *args, **kwargs)

            # Requête API / JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'api' in request.path:
                return JsonResponse({
                    'error': 'Accès non autorisé',
                    'detail': f"Rôles autorisés : {', '.join(allowed_roles)}"
                }, status=403)

            # Requête Web standard
            messages.error(
                request,
                f"Accès refusé : Cette action nécessite l'un des rôles suivants : {', '.join(allowed_roles)}."
            )
            return redirect('stockapp:dashboard')

        return _wrapped_view
    return decorator

