<#
.SYNOPSIS
    Script PowerShell de lancement et initialisation rapide de SMART-TECH.
.DESCRIPTION
    Vérifie l'environnement virtuel, crée les dossiers nécessaires,
    applique les migrations, initialise les rôles, diagnostique la base
    et démarre le serveur web local sur le port 8000 avec ouverture du navigateur.
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "                SMART-TECH : GESTION COMMERCIALE & IA                        " -ForegroundColor Cyan
Write-Host "                Lancement Rapide PowerShell (Windows)                        " -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

# 1. Détection de l'exécutable Python
$PythonExec = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    $PythonExec = ".venv\Scripts\python.exe"
    Write-Host "[INFO] Environnement virtuel détecté : .venv" -ForegroundColor Green
} elseif (Test-Path "venv\Scripts\python.exe") {
    $PythonExec = "venv\Scripts\python.exe"
    Write-Host "[INFO] Environnement virtuel détecté : venv" -ForegroundColor Green
} else {
    Write-Host "[ATTENTION] Utilisation de l'exécutable python système." -ForegroundColor Yellow
}

# 2. Création des répertoires de données
foreach ($dir in @("backups", "media")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "[INFO] Répertoire $dir/ créé." -ForegroundColor Green
    }
}

# 3. Application des migrations
Write-Host "[INFO] Application des migrations de schéma..." -ForegroundColor Cyan
& $PythonExec manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Échec lors de l'application des migrations." -ForegroundColor Red
    exit 1
}

# 4. Initialisation des rôles et permissions
Write-Host "[INFO] Initialisation des rôles métier..." -ForegroundColor Cyan
& $PythonExec manage.py init_roles

# 5. Diagnostic d'intégrité de la base de données
Write-Host "[INFO] Diagnostic d'intégrité du système..." -ForegroundColor Cyan
& $PythonExec manage.py check_system_integrity

# 6. Lancement du navigateur par défaut
Start-Process "http://127.0.0.1:8000/"

# 7. Démarrage du serveur Django
Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host " Serveur actif sur : http://127.0.0.1:8000/                                  " -ForegroundColor Green
Write-Host " Appuyez sur CTRL+C pour interrompre le serveur.                              " -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host ""

& $PythonExec manage.py runserver 127.0.0.1:8000
