# Guide de Déploiement & d'Exploitation en Production — SMART-TECH

**SMART-TECH : Gestion Commerciale Intelligente, Stock & Intelligence Artificielle**  
*Document Technique pour Administrateurs Systèmes & DevOps*

---

## 1. Prérequis & Architecture Système

- **Système d'exploitation recommandé** : Ubuntu 22.04 LTS+ / Debian 12+ ou Windows Server 2022+
- **Environnement d'exécution** : Python 3.11 ou Python 3.12
- **Ressources matérielles minimales** :
  - CPU : 2 vCPU
  - RAM : 2 Go (4 Go recommandés pour les modèles de prédiction Scikit-Learn)
  - Disque : 20 Go SSD avec plan de rétention des sauvegardes

---

## 2. Checklist Obligatoire avant Mise en Production

| Paramètre | Fichier | Valeur Requise |
|---|---|---|
| `DEBUG` | `.env` | `False` |
| `SECRET_KEY` | `.env` | Chaîne aléatoire de 50+ caractères |
| `ALLOWED_HOSTS` | `.env` | FQDN ou IP réelle du serveur (ex: `gestion.mon-entreprise.com`) |
| `CSRF_TRUSTED_ORIGINS` | `.env` | URL HTTPS complète (ex: `https://gestion.mon-entreprise.com`) |
| `SECURE_SSL_REDIRECT` | `settings.py` | `True` (en environnement HTTPS avec reverse proxy) |

---

## 3. Option A : Déploiement Conteneurisé avec Docker Compose (Recommandé)

### 3.1 Installation & Démarrage
1. Cloner le projet ou copier l'archive sur le serveur hôte :
   ```bash
   git clone <repo-url> /opt/smart-tech
   cd /opt/smart-tech
   ```
2. Créer le fichier de variables d'environnement de production :
   ```bash
   cp .env.example .env
   nano .env
   ```
   Renseignez une clé secrète forte et vos noms de domaine.

3. Démarrer le conteneur en arrière-plan :
   ```bash
   docker compose up -d --build
   ```

4. Vérifier l'état de fonctionnement :
   ```bash
   docker compose ps
   docker compose logs -f smart-tech
   ```

5. Créer le compte super-administrateur initial :
   ```bash
   docker compose exec smart-tech python manage.py createsuperuser
   ```

---

## 4. Option B : Déploiement Natif Linux (Systemd + Nginx + Gunicorn)

### 4.1 Préparation de l'environnement virtuel
```bash
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip nginx sqlite3 libfreetype6-dev
cd /var/www/smart-tech
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt gunicorn
cp .env.example .env
python manage.py migrate --noinput
python manage.py init_roles
python manage.py collectstatic --noinput
```

### 4.2 Configuration du service Systemd (`/etc/systemd/system/smart-tech.service`)
```ini
[Unit]
Description=SMART-TECH WSGI Application (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/smart-tech
ExecStart=/var/www/smart-tech/.venv/bin/gunicorn config.wsgi:application \
          --workers 3 \
          --bind 127.0.0.1:8000 \
          --timeout 120 \
          --access-logfile /var/log/smart-tech-access.log \
          --error-logfile /var/log/smart-tech-error.log

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activez et démarrez le service :
```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-tech
sudo systemctl start smart-tech
```

### 4.3 Configuration Nginx en Reverse Proxy (`/etc/nginx/sites-available/smart-tech`)
```nginx
server {
    listen 80;
    server_name gestion.mon-entreprise.com;

    client_max_body_size 50M;

    location /static/ {
        alias /var/www/smart-tech/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    location /media/ {
        alias /var/www/smart-tech/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Activez le site et rechargez Nginx :
```bash
sudo ln -s /etc/nginx/sites-available/smart-tech /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Option C : Déploiement Local / Réseau Local Windows

Pour les boutiques opérant sous Windows en réseau local :
1. Exécutez le script d'initialisation en un clic :
   - Double-cliquez sur `run_smart_tech.bat`
   - Le script vérifie `.venv`, applique les migrations, initialise les rôles de sécurité, diagnostique la base et ouvre le navigateur web par défaut.
2. Pour rendre l'application accessible aux autres caisses et postes du réseau local :
   - Autorisez le port 8000 dans le Pare-feu Windows Defender.
   - Les autres ordinateurs de la boutique peuvent se connecter via `http://<IP_DU_SERVEUR_LOCAL>:8000/`.

---

## 6. Automatisation des Sauvegardes & Maintenance

### Automatisation Linux (Crontab)
Ajoutez une sauvegarde quotidienne nocturne à 02h00 du matin avec nettoyage des archives de plus de 30 jours :
```bash
0 2 * * * cd /var/www/smart-tech && .venv/bin/python manage.py backup_system --retention 30 --max 15 >> /var/log/smart-tech-backup.log 2>&1
```

### Automatisation Windows (Planificateur de tâches)
Créez une tâche planifiée quotidienne exécutant l'action suivante :
- **Programme/script** : `C:\SMART-TECH\.venv\Scripts\python.exe`
- **Arguments** : `manage.py backup_system --retention 30 --max 15`
- **Démarrer dans** : `C:\SMART-TECH\`

---

## 7. Procédure de Reprise après Sinistre (Disaster Recovery)

En cas de défaillance matérielle ou de corruption de base de données :

1. Identifiez la sauvegarde la plus récente dans `backups/` :
   ```bash
   python manage.py check_system_integrity
   ```
2. Restaurez l'archive choisie :
   ```bash
   python manage.py restore_system backup_smart_tech_20260924_120000.zip
   ```
   *Remarque : Un snapshot pré-restauration de sécurité est automatiquement généré avant toute modification.*
3. Redémarrez le service web. L'application est immédiatement opérationnelle et intègre.
