#!/usr/bin/env bash
# ==============================================================================
# SMART-TECH : Script d'initialisation du conteneur Docker
# ==============================================================================

set -e

echo "[DOCKER ENTRYPOINT] Initialisation du conteneur SMART-TECH..."

# 1. Création des répertoires de données si absents
mkdir -p /app/backups /app/media /app/staticfiles

# 2. Application des migrations de base de données
echo "[DOCKER ENTRYPOINT] Application des migrations Django..."
python manage.py migrate --noinput

# 3. Initialisation des rôles et groupes de sécurité
echo "[DOCKER ENTRYPOINT] Initialisation des rôles métier..."
python manage.py init_roles

# 4. Collecte des fichiers statiques
echo "[DOCKER ENTRYPOINT] Collecte des fichiers statiques..."
python manage.py collectstatic --noinput --clear 2>/dev/null || python manage.py collectstatic --noinput

# 5. Diagnostic de santé de la base
echo "[DOCKER ENTRYPOINT] Diagnostic d'intégrité..."
python manage.py check_system_integrity

echo "[DOCKER ENTRYPOINT] Lancement du service..."
exec "$@"
