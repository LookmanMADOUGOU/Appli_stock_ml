from django.core.management.base import BaseCommand
from stockapp.services.backup_service import verifier_integrite_base


class Command(BaseCommand):
    help = "Execute un audit d'integrite physique et logique de la base de donnees SMART-TECH."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[INFO] Verification de l'integrite de la base de donnees SMART-TECH..."))
        res = verifier_integrite_base()

        self.stdout.write(f"Fichier base : {res['chemin_db']} ({res['taille_db_mo']} Mo)")
        for msg in res['messages']:
            if "OK" in msg:
                self.stdout.write(self.style.SUCCESS(f"  [OK] {msg}"))
            else:
                self.stdout.write(self.style.ERROR(f"  [ERREUR] {msg}"))

        self.stdout.write(self.style.NOTICE("\nVolumes de donnees repertories :"))
        for entity, count in res['stats'].items():
            self.stdout.write(f"  - {entity.replace('_', ' ').capitalize()} : {count}")

        if res['est_integre']:
            self.stdout.write(self.style.SUCCESS("\n[OK] Base de donnees parfaitement saine et integre."))
        else:
            self.stdout.write(self.style.ERROR("\n[ERREUR] Des anomalies d'integrite ont ete constatees."))
