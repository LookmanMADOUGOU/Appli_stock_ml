"""
Commande de gestion Django pour initialiser les groupes et rôles utilisateurs SMART-TECH :
- Admin
- Manager
- Caissier
- Magasinier
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, User
from stockapp.permissions import (
    assign_user_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_CAISSIER,
    ROLE_MAGASINIER,
)


class Command(BaseCommand):
    help = "Initialise les groupes et permissions par rôles (Admin, Manager, Caissier, Magasinier)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-defaults',
            action='store_true',
            help="Crée ou met à jour les 4 comptes de démonstration pour chaque profil (admin, manager, caissier, magasinier)",
        )

    def handle(self, *args, **options):
        roles = {
            ROLE_ADMIN: 'Toutes les permissions de gestion commerciale, paramétrage et administration.',
            ROLE_MANAGER: 'Consultation et gestion des produits, ventes, approvisionnements, rapports et alertes.',
            ROLE_CAISSIER: 'Création des ventes, consultation des produits et génération des reçus.',
            ROLE_MAGASINIER: 'Gestion du stock, enregistrement des approvisionnements et ajustements d\'inventaire.'
        }

        created_count = 0
        for role_name, desc in roles.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Groupe '{role_name}' créé avec succès."))

        self.stdout.write(self.style.SUCCESS(f"Initialisation des rôles terminée ({created_count} nouveaux groupes)."))

        if options.get('create_defaults'):
            default_accounts = [
                {
                    'username': 'admin',
                    'email': 'admin@smarttech.local',
                    'first_name': 'Super',
                    'last_name': 'Administrateur',
                    'password': 'Admin1234!',
                    'role': ROLE_ADMIN,
                },
                {
                    'username': 'manager',
                    'email': 'manager@smarttech.local',
                    'first_name': 'Marc',
                    'last_name': 'Directeur',
                    'password': 'Manager1234!',
                    'role': ROLE_MANAGER,
                },
                {
                    'username': 'magasinier',
                    'email': 'magasinier@smarttech.local',
                    'first_name': 'Michel',
                    'last_name': 'Logistique',
                    'password': 'Magasinier1234!',
                    'role': ROLE_MAGASINIER,
                },
                {
                    'username': 'caissier',
                    'email': 'caissier@smarttech.local',
                    'first_name': 'Claire',
                    'last_name': 'Caisse POS',
                    'password': 'Caissier1234!',
                    'role': ROLE_CAISSIER,
                },
            ]

            self.stdout.write("\nCréation des comptes de test par défaut...")
            for acc in default_accounts:
                user, u_created = User.objects.get_or_create(
                    username=acc['username'],
                    defaults={
                        'email': acc['email'],
                        'first_name': acc['first_name'],
                        'last_name': acc['last_name'],
                        'is_active': True,
                    }
                )
                user.set_password(acc['password'])
                user.first_name = acc['first_name']
                user.last_name = acc['last_name']
                user.email = acc['email']
                user.is_active = True
                user.save()
                assign_user_role(user, acc['role'])

                stat = "cree" if u_created else "mis a jour"
                self.stdout.write(self.style.SUCCESS(
                    f"  [OK] Compte @{acc['username']} ({acc['role']}) {stat} - Mot de passe: {acc['password']}"
                ))

