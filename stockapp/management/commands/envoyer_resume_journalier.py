"""
Commande Management Django pour envoyer automatiquement le résumé quotidien du Chiffre d'Affaires
et du Bénéfice Net à l'administrateur / gérant.

Utilisation :
    python manage.py envoyer_resume_journalier
    python manage.py envoyer_resume_journalier --date 2026-08-04
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime
from stockapp.services.alert_service import generer_et_envoyer_resume_journalier


class Command(BaseCommand):
    help = "Envoie le résumé quotidien du CA et du Bénéfice Net par email/notification."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Date au format YYYY-MM-DD (par défaut: aujourd\'hui)',
        )

    def handle(self, *args, **options):
        date_str = options.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR("Format de date invalide. Utilisez YYYY-MM-DD."))
                return
        else:
            target_date = timezone.now().date()

        self.stdout.write(f"Génération du résumé quotidien pour le {target_date}...")
        res = generer_et_envoyer_resume_journalier(target_date)

        self.stdout.write(self.style.SUCCESS(
            f"✅ Résumé envoyé avec succès ! CA: {res['chiffre_affaires']} FCFA/€ | Bénéfice: {res['benefice_net']} FCFA/€"
        ))
