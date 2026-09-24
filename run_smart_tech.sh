#!/usr/bin/env bash
# ==============================================================================
#                 SMART-TECH : GESTION COMMERCIALE & IA
#                 Script de lancement rapide (Linux & macOS)
# ==============================================================================

set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

echo "=============================================================================="
echo "                SMART-TECH : GESTION COMMERCIALE & IA                        "
echo "                Lancement Rapide Unix (Linux / macOS)                        "
echo "=============================================================================="
echo ""

# 1. Détection de l'environnement virtuel
if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
    echo "[INFO] Environnement virtuel détecté : .venv"
elif [ -f "venv/bin/python" ]; then
    PYTHON_EXEC="venv/bin/python"
    echo "[INFO] Environnement virtuel détecté : venv"
else
    PYTHON_EXEC="python3"
    echo "[ATTENTION] Aucun venv local trouvé. Utilisation de python3 système."
fi

# 2. Création des répertoires de stockage
mkdir -p backups media

# 3. Application des migrations
echo "[INFO] Application des migrations..."
"$PYTHON_EXEC" manage.py migrate --noinput

# 4. Initialisation des rôles
echo "[INFO] Initialisation des rôles métier..."
"$PYTHON_EXEC" manage.py init_roles

# 5. Diagnostic d'intégrité
echo "[INFO] Diagnostic de santé système..."
"$PYTHON_EXEC" manage.py check_system_integrity

# 6. Démarrage du serveur web
echo ""
echo "=============================================================================="
echo " Serveur actif sur : http://127.0.0.1:8000/"
echo " Appuyez sur CTRL+C pour arrêter le serveur."
echo "=============================================================================="
echo ""

"$PYTHON_EXEC" manage.py runserver 0.0.0.0:8000
