"""
Service de Sauvegarde, Restauration & Sécurité des Données pour SMART-TECH (Phase 13).
Gère :
- Les snapshots à chaud cohérents de la base SQLite et des médias
- L'export JSON de sécurité Django dumpdata
- La vérification d'intégrité (PRAGMA integrity_check, foreign_key_check)
- La restauration sécurisée avec snapshot automatique pré-restauration
- La rotation, rétention et purge des journaux d'audit
"""

import os
import sys
import io
import json
import zipfile
import hashlib
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

import django
from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.utils import timezone

from stockapp.models import (
    Produit,
    Vente,
    ClotureCaisse,
    MouvementStock,
    Client,
    Fournisseur,
    Depense,
    JournalAudit,
    Notification,
)

logger = logging.getLogger(__name__)


def get_backup_dir() -> Path:
    """Retourne le dossier des sauvegardes et s'assure de son existence."""
    backup_dir = getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups')
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path


def get_db_file_path() -> Path:
    """Retourne le chemin absolu du fichier SQLite actif."""
    db_name = settings.DATABASES['default']['NAME']
    return Path(db_name).resolve()


def calculer_sha256_fichier(chemin_fichier: Path) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier."""
    sha256_hash = hashlib.sha256()
    with open(chemin_fichier, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verifier_integrite_base() -> dict:
    """
    Exécute les contrôles d'intégrité bas niveau de SQLite
    et valide la cohérence des tables métier principales.
    """
    messages_check = []
    est_integre = True

    try:
        with connection.cursor() as cursor:
            # 1. PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check;")
            rows = cursor.fetchall()
            integrity_result = [r[0] for r in rows]
            if integrity_result != ['ok']:
                est_integre = False
                messages_check.extend([f"Erreur intégrité physique: {r}" for r in integrity_result])
            else:
                messages_check.append("Intégrité physique SQLite : OK")

            # 2. PRAGMA foreign_key_check
            cursor.execute("PRAGMA foreign_key_check;")
            fk_violations = cursor.fetchall()
            if fk_violations:
                est_integre = False
                messages_check.append(f"Violations de clés étrangères détectées: {len(fk_violations)} orphelin(s)")
            else:
                messages_check.append("Clés étrangères et intégrité référentielle : OK")

    except Exception as e:
        est_integre = False
        messages_check.append(f"Erreur lors de la vérification SQL: {str(e)}")

    # Statistiques des données
    stats = {
        'produits': Produit.objects.count(),
        'ventes': Vente.objects.count(),
        'clotures_caisse': ClotureCaisse.objects.count(),
        'mouvements_stock': MouvementStock.objects.count(),
        'clients': Client.objects.count(),
        'fournisseurs': Fournisseur.objects.count(),
        'depenses': Depense.objects.count(),
        'audit_logs': JournalAudit.objects.count(),
        'notifications': Notification.objects.count(),
    }

    db_path = get_db_file_path()
    taille_db_mo = round(db_path.stat().st_size / (1024 * 1024), 2) if db_path.exists() else 0.0

    return {
        'est_integre': est_integre,
        'messages': messages_check,
        'stats': stats,
        'taille_db_mo': taille_db_mo,
        'chemin_db': str(db_path),
        'date_verification': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
    }


def creer_sauvegarde(
    nom_personnalise: str = None,
    inclure_medias: bool = True,
    utilisateur=None,
    request=None
) -> dict:
    """
    Crée une sauvegarde compressée .zip complète et cohérente contenant :
    - La base SQLite clonée à chaud (sqlite3 backup API)
    - Un export de sécurité JSON Django (dumpdata)
    - Les fichiers médias
    - Un manifeste de métadonnées et checksum SHA-256
    """
    backup_dir = get_backup_dir()
    timestamp_str = timezone.now().strftime('%Y%m%d_%H%M%S')
    
    if nom_personnalise and nom_personnalise.strip():
        safe_name = "".join(c for c in nom_personnalise if c.isalnum() or c in ('-', '_')).strip()
        filename = f"backup_{safe_name}_{timestamp_str}.zip"
    else:
        filename = f"backup_smart_tech_{timestamp_str}.zip"

    zip_path = backup_dir / filename
    db_path = get_db_file_path()

    temp_db_copy = backup_dir / f"temp_{timestamp_str}.sqlite3"
    temp_json_dump = backup_dir / f"temp_{timestamp_str}.json"

    try:
        # 1. Snapshot cohérent de la base SQLite via l'API de backup native
        connection.ensure_connection()
        if hasattr(connection, 'connection') and connection.connection:
            dst_conn = sqlite3.connect(str(temp_db_copy))
            with dst_conn:
                connection.connection.backup(dst_conn)
            dst_conn.close()
        elif db_path.exists():
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(temp_db_copy))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
        else:
            raise FileNotFoundError(f"Base de données introuvable à {db_path}")

        # 2. Empreinte SHA256 de la base copiée
        sha256_checksum = calculer_sha256_fichier(temp_db_copy)
        db_size_bytes = temp_db_copy.stat().st_size

        # 3. Export JSON Django pour portabilité maximale
        out = io.StringIO()
        call_command(
            'dumpdata',
            'stockapp',
            'auth.user',
            'auth.group',
            format='json',
            indent=2,
            stdout=out
        )
        with open(temp_json_dump, 'w', encoding='utf-8') as f:
            f.write(out.getvalue())

        # 4. Manifeste de métadonnées
        integrite = verifier_integrite_base()
        user_str = utilisateur.username if (utilisateur and utilisateur.is_authenticated) else 'Système'
        metadata = {
            'application': 'SMART-TECH Gestion Commerciale & IA',
            'version_django': django.get_version(),
            'date_creation': timezone.now().isoformat(),
            'cree_par': user_str,
            'nom_archive': filename,
            'sha256_database': sha256_checksum,
            'taille_database_octets': db_size_bytes,
            'inclut_medias': inclure_medias,
            'stats': integrite['stats'],
        }

        # 5. Création de l'archive ZIP
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            # Base SQLite
            zipf.write(temp_db_copy, arcname='database.sqlite3')
            # Export JSON
            zipf.write(temp_json_dump, arcname='dump_data.json')
            # Manifeste
            zipf.writestr('metadata.json', json.dumps(metadata, indent=2, ensure_ascii=False))

            # Médias (si présents)
            if inclure_medias:
                media_root = Path(settings.MEDIA_ROOT)
                if media_root.exists() and media_root.is_dir():
                    for root, _, files in os.walk(media_root):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = Path('media') / file_path.relative_to(media_root)
                            zipf.write(file_path, arcname=str(arcname))

        zip_size_bytes = zip_path.stat().st_size
        taille_formatee = f"{zip_size_bytes / (1024 * 1024):.2f} Mo" if zip_size_bytes >= 1024 * 1024 else f"{zip_size_bytes / 1024:.1f} Ko"

        # 6. Audit Trail
        JournalAudit.log_action(
            utilisateur=utilisateur if (utilisateur and utilisateur.is_authenticated) else None,
            action='CREATION',
            module='SECURITE',
            objet_concerne=f"Sauvegarde #{filename}",
            description=f"Sauvegarde complète SMART-TECH créée ({taille_formatee}, SHA256: {sha256_checksum[:12]}...).",
            request=request
        )

        return {
            'succes': True,
            'nom_fichier': filename,
            'chemin_absolu': str(zip_path),
            'taille_octets': zip_size_bytes,
            'taille_formatee': taille_formatee,
            'sha256': sha256_checksum,
            'date_creation': metadata['date_creation'],
            'cree_par': user_str,
            'stats': integrite['stats'],
        }

    finally:
        # Nettoyage des fichiers temporaires
        if temp_db_copy.exists():
            try:
                temp_db_copy.unlink()
            except Exception:
                pass
        if temp_json_dump.exists():
            try:
                temp_json_dump.unlink()
            except Exception:
                pass


def lister_sauvegardes() -> list:
    """
    Retourne la liste détaillée de toutes les sauvegardes existantes,
    ordonnées de la plus récente à la plus ancienne.
    """
    backup_dir = get_backup_dir()
    sauvegardes = []

    for file_path in backup_dir.glob("*.zip"):
        try:
            stat = file_path.stat()
            taille_bytes = stat.st_size
            taille_formatee = f"{taille_bytes / (1024 * 1024):.2f} Mo" if taille_bytes >= 1024 * 1024 else f"{taille_bytes / 1024:.1f} Ko"
            date_modif = datetime.fromtimestamp(stat.st_mtime)

            # Lecture du manifeste
            meta = {}
            est_valide = False
            try:
                with zipfile.ZipFile(file_path, 'r') as zipf:
                    if 'metadata.json' in zipf.namelist():
                        meta_data = zipf.read('metadata.json').decode('utf-8')
                        meta = json.loads(meta_data)
                    est_valide = ('database.sqlite3' in zipf.namelist() or 'dump_data.json' in zipf.namelist())
            except Exception:
                est_valide = False

            sauvegardes.append({
                'nom_fichier': file_path.name,
                'chemin': str(file_path),
                'taille_octets': taille_bytes,
                'taille_formatee': taille_formatee,
                'date_modification': date_modif,
                'est_valide': est_valide,
                'sha256': meta.get('sha256_database', '-'),
                'cree_par': meta.get('cree_par', 'Inconnu'),
                'stats': meta.get('stats', {}),
            })
        except Exception as e:
            logger.warning(f"Erreur lecture sauvegarde {file_path.name}: {e}")

    sauvegardes.sort(key=lambda s: s['date_modification'], reverse=True)
    return sauvegardes


def restaurer_sauvegarde(nom_fichier: str, utilisateur=None, request=None) -> dict:
    """
    Restaure une sauvegarde avec protection absolue :
    1. Vérifie l'intégrité de l'archive .zip demandée
    2. Crée automatiquement un backup pré-restauration de sécurité
    3. Ferme les connexions actives et restaure database.sqlite3 et media/
    4. Effectue un check d'intégrité post-restauration
    5. Consigne dans le Journal d'Audit
    """
    backup_dir = get_backup_dir()
    zip_path = backup_dir / nom_fichier

    if not zip_path.exists():
        raise FileNotFoundError(f"L'archive de sauvegarde {nom_fichier} n'existe pas.")

    # 1. Vérification du zip
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        bad_file = zipf.testzip()
        if bad_file:
            raise ValueError(f"L'archive {nom_fichier} est corrompue (erreur sur {bad_file}).")
        namelist = zipf.namelist()
        if 'database.sqlite3' not in namelist and 'dump_data.json' not in namelist:
            raise ValueError("L'archive ne contient aucune donnée de base exploitable.")

    # 2. Snapshot de pré-restauration de sécurité
    pre_restore = creer_sauvegarde(
        nom_personnalise="pre_restauration_securite",
        inclure_medias=True,
        utilisateur=utilisateur,
        request=request
    )

    db_path = get_db_file_path()

    # 3. Restauration de la base SQLite
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        if 'database.sqlite3' in namelist:
            if not str(db_path).startswith('file:') and db_path.name != ':memory:':
                connections.close_all()
                with open(db_path, 'wb') as dst:
                    dst.write(zipf.read('database.sqlite3'))
            else:
                # Mode test / base en mémoire
                temp_restored = backup_dir / f"temp_restored_{timezone.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
                with open(temp_restored, 'wb') as dst:
                    dst.write(zipf.read('database.sqlite3'))
                src_conn = sqlite3.connect(str(temp_restored))
                connection.ensure_connection()
                with connection.connection:
                    src_conn.backup(connection.connection)
                src_conn.close()
                if temp_restored.exists():
                    temp_restored.unlink()

        # Restauration des médias
        media_root = Path(settings.MEDIA_ROOT)
        media_files = [n for n in namelist if n.startswith('media/') and not n.endswith('/')]
        for mfile in media_files:
            rel_name = mfile[len('media/'):]
            target_dest = media_root / rel_name
            target_dest.parent.mkdir(parents=True, exist_ok=True)
            with open(target_dest, 'wb') as dst:
                dst.write(zipf.read(mfile))

    # 4. Check post-restauration
    integrite = verifier_integrite_base()

    JournalAudit.log_action(
        utilisateur=utilisateur if (utilisateur and utilisateur.is_authenticated) else None,
        action='MODIFICATION',
        module='SECURITE',
        objet_concerne=f"Restauration #{nom_fichier}",
        description=f"Base restaurée avec succès depuis {nom_fichier}. Snapshot pré-restauration: {pre_restore['nom_fichier']}.",
        request=request
    )

    return {
        'succes': True,
        'nom_fichier_restaure': nom_fichier,
        'snapshot_pre_restauration': pre_restore['nom_fichier'],
        'integrite_post_restauration': integrite,
    }


def supprimer_sauvegarde(nom_fichier: str, utilisateur=None, request=None) -> bool:
    """Supprime un fichier de sauvegarde dans le dossier sécurisé."""
    backup_dir = get_backup_dir()
    zip_path = backup_dir / nom_fichier

    # Sécurité anti-traversal
    if '..' in nom_fichier or '/' in nom_fichier or '\\\\' in nom_fichier:
        raise ValueError("Nom de fichier de sauvegarde invalide.")

    if zip_path.exists():
        zip_path.unlink()
        JournalAudit.log_action(
            utilisateur=utilisateur if (utilisateur and utilisateur.is_authenticated) else None,
            action='SUPPRESSION',
            module='SECURITE',
            objet_concerne=f"Sauvegarde #{nom_fichier}",
            description=f"Fichier de sauvegarde {nom_fichier} définitivement supprimé.",
            request=request
        )
        return True
    return False


def nettoyer_anciennes_sauvegardes(jours_retention: int = 30, max_sauvegardes: int = 10) -> int:
    """
    Supprime automatiquement les sauvegardes de plus de N jours
    et garantit qu'il ne reste pas plus de max_sauvegardes archives.
    """
    sauvegardes = lister_sauvegardes()
    date_limite = timezone.now() - timedelta(days=jours_retention)
    supprimes_count = 0

    # 1. Règle d'ancienneté (hors les 3 dernières indispensables)
    for s in sauvegardes[3:]:
        if s['date_modification'] < date_limite.replace(tzinfo=None):
            p = Path(s['chemin'])
            if p.exists():
                p.unlink()
                supprimes_count += 1

    # 2. Règle de quota maximum
    sauvegardes_restantes = lister_sauvegardes()
    if len(sauvegardes_restantes) > max_sauvegardes:
        for s in sauvegardes_restantes[max_sauvegardes:]:
            p = Path(s['chemin'])
            if p.exists():
                p.unlink()
                supprimes_count += 1

    return supprimes_count


def purger_anciens_logs_audit(jours_retention: int = 90, utilisateur=None, request=None) -> int:
    """
    Purge les logs d'audit datant de plus de N jours pour préserver
    les performances et la taille de la base de données.
    """
    date_limite = timezone.now() - timedelta(days=jours_retention)
    logs_anciens = JournalAudit.objects.filter(date_creation__lt=date_limite)
    nb_supprimes = logs_anciens.count()
    logs_anciens.delete()

    JournalAudit.log_action(
        utilisateur=utilisateur if (utilisateur and utilisateur.is_authenticated) else None,
        action='SUPPRESSION',
        module='SECURITE',
        objet_concerne="Purge JournalAudit",
        description=f"Purge automatique des logs d'audit de plus de {jours_retention} jours ({nb_supprimes} enregistrements purgés).",
        request=request
    )
    return nb_supprimes
