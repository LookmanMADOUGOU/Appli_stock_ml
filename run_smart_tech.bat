@echo off
chcp 65001 > nul
title SMART-TECH - Gestion Commerciale & Intelligence Artificielle

echo ==============================================================================
echo                 SMART-TECH : GESTION COMMERCIALE & IA
echo                 Lancement Rapide de l'Application (Windows)
echo ==============================================================================
echo.

set BASE_DIR=%~dp0
cd /d "%BASE_DIR%"

:: 1. Verification de l'environnement virtuel
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXEC=.venv\Scripts\python.exe
    echo [INFO] Environnement virtuel detecte : .venv
) else if exist "venv\Scripts\python.exe" (
    set PYTHON_EXEC=venv\Scripts\python.exe
    echo [INFO] Environnement virtuel detecte : venv
) else (
    set PYTHON_EXEC=python
    echo [ATTENTION] Aucun environnement virtuel local trouve. Utilisation du Python systeme.
)

:: 2. Creation des repertoires critiques
if not exist "backups" (
    mkdir backups
    echo [INFO] Repertoire backups/ cree.
)
if not exist "media" (
    mkdir media
    echo [INFO] Repertoire media/ cree.
)

:: 3. Application des migrations de base de donnees
echo [INFO] Verification et application des migrations...
"%PYTHON_EXEC%" manage.py migrate --noinput
if errorlevel 1 (
    echo [ERREUR] Echec lors de l'application des migrations.
    pause
    exit /b 1
)

:: 4. Initialisation des roles et groupes de securite
echo [INFO] Initialisation des roles SMART-TECH (Admin, Manager, Caissier, Magasinier)...
"%PYTHON_EXEC%" manage.py init_roles > nul 2>&1

:: 5. Verification de l'integrite de la base de donnees
echo [INFO] Diagnostic d'integrite...
"%PYTHON_EXEC%" manage.py check_system_integrity

:: 6. Ouverture du navigateur par defaut apres un court delai
start "" "http://127.0.0.1:8000/"

:: 7. Demarrage du serveur web Django
echo.
echo ==============================================================================
echo  Le serveur SMART-TECH est actif sur : http://127.0.0.1:8000/
echo  Pour arreter l'application, appuyez sur CTRL+C ou fermez cette fenetre.
echo ==============================================================================
echo.

"%PYTHON_EXEC%" manage.py runserver 127.0.0.1:8000
pause
