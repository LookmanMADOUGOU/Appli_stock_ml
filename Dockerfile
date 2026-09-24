# ==============================================================================
# SMART-TECH : Gestion Commerciale & Intelligence Artificielle
# Dockerfile officiel de production
# ==============================================================================

FROM python:3.12-slim

# Paramètres d'exécution Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Dépendances système requises (polices pour ReportLab, SQLite, curl pour healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    libfreetype6-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn==23.0.0

# Copie de l'ensemble du projet
COPY . /app/

# Création des répertoires de données persistantes
RUN mkdir -p /app/backups /app/media /app/staticfiles

# Droits d'exécution sur les scripts
RUN chmod +x /app/entrypoint.sh /app/run_smart_tech.sh 2>/dev/null || true

# Port exposé
EXPOSE 8000

# Script d'entrée
ENTRYPOINT ["/app/entrypoint.sh"]

# Commande par défaut (Gunicorn WSGI de production)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
