"""
Commande de gestion Django pour initialiser les groupes et rôles utilisateurs SMART-TECH :
- Admin
- Manager
- Caissier
- Magasinier
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from stockapp.models import Produit, Vente, Approvisionnement, MouvementStock, AlerteRupture, Categorie


class Command(BaseCommand):
    help = "Initialise les groupes et permissions par rôles (Admin, Manager, Caissier, Magasinier)"

    def handle(self, *args, **options):
        roles = {
            'Admin': 'Toutes les permissions de gestion commerciale, paramétrage et administration.',
            'Manager': 'Consultation et gestion des produits, ventes, approvisionnements, rapports et alertes.',
            'Caissier': 'Création des ventes, consultation des produits et génération des reçus.',
            'Magasinier': 'Gestion du stock, enregistrement des approvisionnements et ajustements d\'inventaire.'
        }

        created_count = 0
        for role_name, desc in roles.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Groupe '{role_name}' créé avec succès."))

        self.stdout.write(self.style.SUCCESS(f"Initialisation des rôles terminée ({created_count} nouveaux groupes)."))
