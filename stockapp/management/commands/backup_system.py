from django.core.management.base import BaseCommand
from stockapp.services.backup_service import creer_sauvegarde, nettoyer_anciennes_sauvegardes


class Command(BaseCommand):
    help = "Cree une sauvegarde complete et securisee de SMART-TECH (Base SQLite, JSON dump, medias et metadonnees)."

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, help="Nom personnalise pour l'archive de sauvegarde")
        parser.add_argument('--no-media', action='store_true', help="Ne pas inclure les fichiers medias dans la sauvegarde")
        parser.add_argument('--retention', type=int, default=30, help="Nombre de jours de retention pour le nettoyage")
        parser.add_argument('--max', type=int, default=10, help="Nombre maximum de sauvegardes a conserver")

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[INFO] Demarrage du processus de sauvegarde SMART-TECH..."))

        inclure_medias = not options['no_media']
        nom = options.get('name')

        try:
            res = creer_sauvegarde(
                nom_personnalise=nom,
                inclure_medias=inclure_medias
            )

            self.stdout.write(self.style.SUCCESS(f"[OK] Sauvegarde reussie : {res['nom_fichier']}"))
            self.stdout.write(f"   Chemin : {res['chemin_absolu']}")
            self.stdout.write(f"   Taille : {res['taille_formatee']}")
            self.stdout.write(f"   SHA-256 : {res['sha256']}")
            self.stdout.write(f"   Stats : Produits={res['stats']['produits']} | Ventes={res['stats']['ventes']} | Clotures={res['stats']['clotures_caisse']}")

            # Nettoyage automatique
            suppr = nettoyer_anciennes_sauvegardes(
                jours_retention=options['retention'],
                max_sauvegardes=options['max']
            )
            if suppr > 0:
                self.stdout.write(self.style.WARNING(f"   [INFO] {suppr} ancienne(s) sauvegarde(s) nettoyee(s)."))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERREUR] Echec de la sauvegarde : {str(e)}"))
            raise e
