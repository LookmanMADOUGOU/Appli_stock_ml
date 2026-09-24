from django.core.management.base import BaseCommand, CommandError
from stockapp.services.backup_service import restaurer_sauvegarde


class Command(BaseCommand):
    help = "Restaure SMART-TECH depuis une archive de sauvegarde .zip avec protection prealable."

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help="Nom du fichier de sauvegarde a restaurer (ex: backup_smart_tech_....zip)")
        parser.add_argument('--no-input', action='store_true', help="Ne pas demander de confirmation interactive")

    def handle(self, *args, **options):
        filename = options['filename']
        no_input = options['no_input']

        if not no_input:
            self.stdout.write(self.style.WARNING(f"[ATTENTION] La restauration ecrasera les donnees actuelles avec {filename}."))
            confirm = input("Etes-vous certain de vouloir continuer ? (oui/non) : ").strip().lower()
            if confirm not in ['oui', 'o', 'yes', 'y']:
                self.stdout.write("Operation annulee par l'utilisateur.")
                return

        self.stdout.write(self.style.NOTICE(f"[INFO] Restauration en cours depuis {filename}..."))
        try:
            res = restaurer_sauvegarde(nom_fichier=filename)
            self.stdout.write(self.style.SUCCESS(f"[OK] Restauration effectuee avec succes depuis {filename}"))
            self.stdout.write(f"   Snapshot de pre-restauration cree : {res['snapshot_pre_restauration']}")
            self.stdout.write(f"   Integrite post-restauration : {'OK' if res['integrite_post_restauration']['est_integre'] else 'ANOMALIE'}")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERREUR] Echec de la restauration : {str(e)}"))
            raise CommandError(str(e))
