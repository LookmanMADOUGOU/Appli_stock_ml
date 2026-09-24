import io
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .api.serializers import AlerteRuptureSerializer, ProduitSerializer
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente, Client, Fournisseur, MouvementStock, Depense, JournalAudit
from .services.alert_service import creer_alerte_si_necessaire, generer_et_envoyer_resume_journalier
from .services.prediction_service import predict_sales, predict_stockout, get_demand_forecast
from .services.purchase_order_service import (
    generate_purchase_order_data,
    generate_purchase_order_pdf,
    convert_order_data_to_approvisionnements,
)
from .services.stock_service import increase_stock, reduce_stock


class PredictionServiceTests(TestCase):
    def setUp(self):
        self.categorie = Categorie.objects.create(nom='Électronique')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Écran',
            reference='ABC-001',
            stock_actuel=2,
            seuil_alerte=3,
            prix_unitaire=100.0,
            prix_achat=70.0,
        )

    def test_prediction_returns_message_when_not_enough_sales(self):
        self.assertEqual(predict_sales(self.produit), 'Pas assez de données')
        self.assertEqual(predict_stockout(self.produit), 'Pas assez de données')

    def test_alert_is_created_when_stock_is_at_threshold(self):
        self.produit.stock_actuel = 2
        self.produit.seuil_alerte = 2
        self.produit.save(update_fields=['stock_actuel', 'seuil_alerte'])

        creer_alerte_si_necessaire(self.produit)
        self.assertTrue(AlerteRupture.objects.filter(produit=self.produit).exists())

    @override_settings(DEFAULT_FROM_EMAIL='noreply@example.com', ADMIN_EMAIL='admin@example.com')
    def test_email_notification_is_sent_when_alert_is_created(self):
        self.produit.stock_actuel = 1
        self.produit.seuil_alerte = 1
        self.produit.save(update_fields=['stock_actuel', 'seuil_alerte'])

        with patch('stockapp.services.alert_service.send_mail') as mocked_send_mail:
            creer_alerte_si_necessaire(self.produit)

        mocked_send_mail.assert_called_once()

    def test_reduce_stock_does_not_go_negative(self):
        self.produit.stock_actuel = 1
        self.produit.save(update_fields=['stock_actuel'])

        remaining = reduce_stock(self.produit, 5)
        self.assertEqual(remaining, 0)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 0)

    def test_increase_stock_adds_quantity(self):
        remaining = increase_stock(self.produit, 5)
        self.assertEqual(remaining, 7)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 7)


class ProduitSerializerTests(TestCase):
    def setUp(self):
        self.categorie = Categorie.objects.create(nom='Informatique')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Clavier',
            reference='KB-99',
            stock_actuel=5,
            seuil_alerte=2,
            prix_unitaire=25.0,
            prix_achat=15.0,
        )

    def test_serializer_includes_prediction_fields(self):
        serializer = ProduitSerializer(self.produit)
        data = serializer.data
        self.assertIn('rupture', data)
        self.assertIn('prediction_ml', data)
        self.assertIn('prediction_rupture', data)
        self.assertIn('prix_unitaire', data)
        self.assertIn('prix_achat', data)
        self.assertIn('marge_unitaire', data)


class AlerteRuptureSerializerTests(TestCase):
    def setUp(self):
        self.produit = Produit.objects.create(
            nom='Souris',
            reference='MS-01',
            stock_actuel=0,
            seuil_alerte=5,
        )
        self.alerte = AlerteRupture.objects.create(
            produit=self.produit,
            niveau='critique',
            message='Rupture imminente',
        )

    def test_serializer_exposes_alert_fields(self):
        serializer = AlerteRuptureSerializer(self.alerte)
        data = serializer.data
        self.assertEqual(data['produit_nom'], 'Souris')
        self.assertEqual(data['niveau'], 'critique')


class ApiEndpointsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username='admin', email='admin@test.com', password='password')
        self.user = User.objects.create_user(username='user', password='password')
        self.client = APIClient()

        self.categorie = Categorie.objects.create(nom='Réseau')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Switch',
            reference='SW-8P',
            stock_actuel=10,
            seuil_alerte=2,
            prix_unitaire=50.0,
            prix_achat=30.0,
        )

    def test_stats_summary_endpoint(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('stats-summary'))
        self.assertEqual(response.status_code, 200)

    def test_product_trend_endpoint(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('produit-trend', kwargs={'pk': self.produit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_product_forecast_endpoint(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('produit-forecast', kwargs={'pk': self.produit.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_products_export_endpoint_returns_csv(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('produit-export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_import_csv_produit_checks_alerts(self):
        self.client.force_authenticate(user=self.admin)
        csv_content = "nom,reference,stock_actuel,seuil_alerte,categorie\nDisque Dur,HDD-01,1,3,Réseau\n"
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        csv_file.name = 'produits.csv'

        response = self.client.post(
            reverse('produit-import-csv'),
            {'file': csv_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AlerteRupture.objects.filter(produit__reference='HDD-01').exists())

    def test_approvisionnement_api_endpoint(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('approvisionnement-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_import_csv_approvisionnement_no_double_increment(self):
        self.client.force_authenticate(user=self.admin)
        csv_content = f"produit_reference,quantite,fournisseur\nSW-8P,5,Fournisseur Test\n"
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        csv_file.name = 'appro.csv'

        response = self.client.post(
            reverse('approvisionnement-import-csv'),
            {'file': csv_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, 200)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 15)

    def test_product_list_supports_search_and_pagination(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse('produit-list'), {'search': 'Switch', 'page_size': 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

    def test_export_report_pdf_authenticated(self):
        self.client.login(username='user', password='password')
        response = self.client.get(reverse('stockapp:export-report-pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class VentePrixUnitaireTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='password')
        self.produit = Produit.objects.create(
            nom='Bouteille d\'eau',
            reference='H2O-001',
            stock_actuel=50,
            seuil_alerte=10,
            prix_unitaire=500.0,
            prix_achat=300.0,
        )

    def test_vente_calculates_prix_total(self):
        vente = Vente.objects.create(produit=self.produit, quantite=4, prix_unitaire=500.0, prix_achat=300.0)
        self.assertEqual(vente.prix_total, 2000.0)

    def test_vente_calculates_benefice_and_margin(self):
        vente = Vente.objects.create(produit=self.produit, quantite=4, prix_unitaire=500.0, prix_achat=300.0)
        self.assertEqual(vente.marge_unitaire, 200.0)
        self.assertEqual(vente.benefice_total, 800.0)

    def test_vente_copies_produit_prix_unitaire_when_blank(self):
        vente = Vente.objects.create(produit=self.produit, quantite=2)
        self.assertEqual(vente.prix_unitaire, 500.0)
        self.assertEqual(vente.prix_achat, 300.0)
        self.assertEqual(vente.prix_total, 1000.0)
        self.assertEqual(vente.benefice_total, 400.0)

    def test_ventes_view_returns_journal_aggregation(self):
        self.client.login(username='tester', password='password')
        Vente.objects.create(produit=self.produit, quantite=4)
        Vente.objects.create(produit=self.produit, quantite=4)
        Vente.objects.create(produit=self.produit, quantite=1)

        response = self.client.get(reverse('stockapp:ventes-list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('journal_ventes', response.context)
        journal = response.context['journal_ventes']
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]['decomposition'], '4 + 4 + 1')
        self.assertEqual(journal[0]['total_quantite'], 9)
        self.assertEqual(journal[0]['montant_total'], 4500.0)
        self.assertEqual(journal[0]['benefice'], 1800.0)

    def test_ventes_view_periode_filtering(self):
        self.client.login(username='tester', password='password')
        response = self.client.get(reverse('stockapp:ventes-list'), {'periode': 'mois'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['periode'], 'mois')

    def test_telecharger_recu_pdf_view(self):
        self.client.login(username='tester', password='password')
        vente = Vente.objects.create(produit=self.produit, quantite=2)
        url = reverse('stockapp:vente-recu-pdf', kwargs={'pk': vente.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class PurchaseOrderAndNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='manager', password='password')
        self.produit_rupture = Produit.objects.create(
            nom='Jus d\'Orange',
            reference='JU-001',
            stock_actuel=2,
            seuil_alerte=5,
            prix_unitaire=1000.0,
            prix_achat=600.0,
        )

    def test_purchase_order_data_generation(self):
        data = generate_purchase_order_data()
        self.assertEqual(data['nb_produits'], 1)
        self.assertEqual(data['items'][0]['produit_id'], self.produit_rupture.id)
        self.assertGreater(data['total_articles'], 0)
        self.assertGreater(data['total_estime'], 0)

    def test_purchase_order_pdf_generation(self):
        data = generate_purchase_order_data()
        pdf_bytes = generate_purchase_order_pdf(data)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 100)

    def test_purchase_order_views_and_validation(self):
        self.client.login(username='manager', password='password')
        res_list = self.client.get(reverse('stockapp:bon-de-commande'))
        self.assertEqual(res_list.status_code, 200)

        res_pdf = self.client.get(reverse('stockapp:bon-de-commande-pdf'))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

        res_val = self.client.post(reverse('stockapp:bon-de-commande-valider'))
        self.assertEqual(res_val.status_code, 302)
        self.assertTrue(Approvisionnement.objects.filter(produit=self.produit_rupture).exists())

    def test_daily_summary_generation_and_view(self):
        self.client.login(username='manager', password='password')
        Vente.objects.create(produit=self.produit_rupture, quantite=3)

        with patch('stockapp.services.alert_service.send_mail') as mock_mail:
            res = generer_et_envoyer_resume_journalier()
            self.assertEqual(res['total_articles'], 3)
            self.assertEqual(res['chiffre_affaires'], 3000.0)
            self.assertEqual(res['benefice_net'], 1200.0)
            mock_mail.assert_called_once()

        res_view = self.client.post(reverse('stockapp:envoyer-resume-journalier'))
        self.assertEqual(res_view.status_code, 302)

    def test_ml_seasonality_prediction(self):
        now = timezone.now()
        for i in range(7):
            v = Vente.objects.create(produit=self.produit_rupture, quantite=3)
            Vente.objects.filter(pk=v.pk).update(date_vente=now - timedelta(days=i))

        forecast = get_demand_forecast(self.produit_rupture, days_ahead=7)
        self.assertIsInstance(forecast, dict)
        self.assertIn('predictions', forecast)
        self.assertEqual(len(forecast['predictions']), 7)

        pred_sales = predict_sales(self.produit_rupture)
        self.assertIsInstance(pred_sales, float)


class PWATests(TestCase):
    def test_service_worker_endpoint(self):
        url = reverse('stockapp:service-worker')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertEqual(response['Service-Worker-Allowed'], '/')

    def test_pwa_manifest_endpoint(self):
        url = reverse('stockapp:manifest')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')
        self.assertIn('SMART-TECH', response.content.decode('utf-8'))


class MouvementStockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='stock_mgr', password='password')
        self.produit = Produit.objects.create(
            nom='Tablette 10"',
            reference='TAB-010',
            stock_actuel=20,
            seuil_alerte=5,
            stock_maximum=50,
            prix_unitaire=200.0,
            prix_achat=140.0,
        )

    def test_centralized_statut_stock_logic(self):
        self.produit.stock_actuel = 0
        self.assertEqual(self.produit.statut_stock, 'RUPTURE')

        self.produit.stock_actuel = 4
        self.assertEqual(self.produit.statut_stock, 'STOCK FAIBLE')

        self.produit.stock_actuel = 20
        self.assertEqual(self.produit.statut_stock, 'STOCK NORMAL')

        self.produit.stock_actuel = 55
        self.assertEqual(self.produit.statut_stock, 'SURSTOCK')

    def test_mouvement_stock_created_on_sale_and_supply(self):
        from stockapp.models import MouvementStock
        from stockapp.services.stock_service import reduce_stock, increase_stock

        reduce_stock(self.produit, 5, type_mouvement='VENTE', utilisateur=self.user)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 15)
        mvt = MouvementStock.objects.filter(produit=self.produit, type_mouvement='VENTE').first()
        self.assertIsNotNone(mvt)
        self.assertEqual(mvt.stock_avant, 20)
        self.assertEqual(mvt.stock_apres, 15)

        increase_stock(self.produit, 10, type_mouvement='ACHAT', utilisateur=self.user)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 25)
        mvt_buy = MouvementStock.objects.filter(produit=self.produit, type_mouvement='ACHAT').first()
        self.assertIsNotNone(mvt_buy)
        self.assertEqual(mvt_buy.stock_avant, 15)
        self.assertEqual(mvt_buy.stock_apres, 25)

    def test_ajuster_stock_manuel_audit_trail(self):
        from stockapp.models import MouvementStock
        from stockapp.services.stock_service import ajuster_stock_manuel

        ajuster_stock_manuel(self.produit, nouveau_stock=40, utilisateur=self.user, motif="Inventaire mensuel")
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 40)
        mvt_adj = MouvementStock.objects.filter(produit=self.produit, type_mouvement='AJUSTEMENT').first()
        self.assertIsNotNone(mvt_adj)
        self.assertEqual(mvt_adj.stock_avant, 20)
        self.assertEqual(mvt_adj.stock_apres, 40)

    def test_mouvements_api_endpoint(self):
        from stockapp.services.stock_service import reduce_stock
        reduce_stock(self.produit, 2, type_mouvement='VENTE', utilisateur=self.user)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse('mouvement-stock-list')
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['count'], 1)


class SecurityAndRolePermissionsTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import Group, User
        from django.core.management import call_command
        
        call_command('init_roles')

        self.superuser = User.objects.create_superuser(username='admin_boss', password='password')
        
        self.caissier = User.objects.create_user(username='caissier_user', password='password')
        self.caissier.groups.add(Group.objects.get(name='Caissier'))

        self.magasinier = User.objects.create_user(username='magasinier_user', password='password')
        self.magasinier.groups.add(Group.objects.get(name='Magasinier'))

    def test_roles_groups_created_by_init_roles_command(self):
        from django.contrib.auth.models import Group
        self.assertTrue(Group.objects.filter(name='Admin').exists())
        self.assertTrue(Group.objects.filter(name='Manager').exists())
        self.assertTrue(Group.objects.filter(name='Caissier').exists())
        self.assertTrue(Group.objects.filter(name='Magasinier').exists())

    def test_role_permission_classes(self):
        from stockapp.permissions import IsAdminUserRole, IsCashierUserRole, IsStockManagerUserRole
        from unittest.mock import MagicMock

        req_superuser = MagicMock()
        req_superuser.user = self.superuser
        
        req_caissier = MagicMock()
        req_caissier.user = self.caissier

        req_magasinier = MagicMock()
        req_magasinier.user = self.magasinier

        perm_admin = IsAdminUserRole()
        perm_cashier = IsCashierUserRole()
        perm_stock = IsStockManagerUserRole()

        self.assertTrue(perm_admin.has_permission(req_superuser, None))
        self.assertFalse(perm_admin.has_permission(req_caissier, None))

        self.assertTrue(perm_cashier.has_permission(req_caissier, None))
        self.assertTrue(perm_stock.has_permission(req_magasinier, None))


class StockAndInventoryModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='stock_user', password='password', is_staff=True)
        self.categorie = Categorie.objects.create(nom='High Tech')
        self.produit = Produit.objects.create(
            nom='Ecran 4K',
            reference='MON-4K',
            sku='SKU-MON-4K',
            code_barres='1234567890123',
            stock_actuel=15,
            seuil_alerte=5,
            stock_maximum=40,
            prix_unitaire=300.0,
            prix_achat=200.0,
            categorie=self.categorie,
        )

    def test_produit_enhanced_properties(self):
        self.assertEqual(self.produit.marge_unitaire, 100.0)
        self.assertEqual(self.produit.taux_marge, 33.33)
        self.assertEqual(self.produit.valeur_stock_achat, 3000.0)
        self.assertEqual(self.produit.valeur_stock_vente, 4500.0)

    def test_stock_inventaire_view_renders_correctly(self):
        self.client.login(username='stock_user', password='password')
        response = self.client.get(reverse('stockapp:stock-inventaire'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('produits', response.context)
        self.assertIn('valeur_stock_achat', response.context)

    def test_ajuster_stock_view_updates_inventory(self):
        self.client.login(username='stock_user', password='password')
        url = reverse('stockapp:ajuster-stock')
        response = self.client.post(url, {
            'produit': self.produit.id,
            'nouveau_stock': 25,
            'motif': 'Inventaire annuel'
        })
        self.assertEqual(response.status_code, 302)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 25)

    def test_mouvements_list_view_renders(self):
        self.client.login(username='stock_user', password='password')
        response = self.client.get(reverse('stockapp:mouvements-list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('mouvements', response.context)


class CaissePosAndClientFournisseurTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pos_cashier', password='password')
        self.client_entity = Client.objects.create(nom='Client VIP', telephone='90000000', email='vip@client.com')
        self.fournisseur = Fournisseur.objects.create(nom='Distrib SARL', telephone='21000000', email='contact@distrib.com')
        self.produit = Produit.objects.create(
            nom='Clavier Sans Fil',
            reference='KB-WIRELESS',
            stock_actuel=20,
            seuil_alerte=5,
            prix_unitaire=50.0,
            prix_achat=30.0,
        )

    def test_clients_list_view_get_and_post(self):
        self.client.login(username='pos_cashier', password='password')
        url = reverse('stockapp:clients-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {'nom': 'Nouveau Client Test', 'telephone': '99887766', 'email': 'new@test.com', 'solde_credit': '0.00'}
        res = self.client.post(url, post_data)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Client.objects.filter(nom='Nouveau Client Test').exists())

    def test_fournisseurs_list_view_get_and_post(self):
        self.client.login(username='pos_cashier', password='password')
        url = reverse('stockapp:fournisseurs-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {'nom': 'Nouveau Fournisseur Test', 'telephone': '22334455', 'email': 'fournisseur@test.com', 'dette_fournisseur': '0.00'}
        res = self.client.post(url, post_data)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Fournisseur.objects.filter(nom='Nouveau Fournisseur Test').exists())

    def test_caisse_pos_checkout_creates_sales_and_reduces_stock(self):
        self.client.login(username='pos_cashier', password='password')
        url = reverse('stockapp:caisse-pos')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        cart_data = [
            {'produit_id': self.produit.id, 'quantite': 3, 'prix_unitaire': 50.0}
        ]
        import json
        post_data = {
            'cart_data': json.dumps(cart_data),
            'client_id': self.client_entity.id,
            'mode_paiement': 'ESPECES',
            'remise_globale': '5.00'
        }

        res = self.client.post(url, post_data)
        self.assertEqual(res.status_code, 302)

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 17)

        vente = Vente.objects.filter(produit=self.produit).first()
        self.assertIsNotNone(vente)
        self.assertEqual(vente.client, self.client_entity)
        self.assertEqual(vente.quantite, 3)

    def test_telecharger_recu_pdf_view(self):
        self.client.login(username='pos_cashier', password='password')
        vente = Vente.objects.create(
            produit=self.produit,
            client=self.client_entity,
            quantite=2,
            prix_unitaire=50.0,
            prix_achat=30.0,
            reference_ticket='TCK-TEST-12345'
        )
        url = reverse('stockapp:vente-recu-pdf', kwargs={'pk': vente.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')

    def test_dashboard_view_renders(self):
        self.client.login(username='pos_cashier', password='password')
        response = self.client.get(reverse('stockapp:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('stats', response.context)

    def test_analytics_view_renders(self):
        self.client.login(username='pos_cashier', password='password')
        response = self.client.get(reverse('stockapp:analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('ca_global', response.context)

    def test_telecharger_facture_pdf_view(self):
        self.client.login(username='pos_cashier', password='password')
        vente = Vente.objects.create(
            produit=self.produit,
            client=self.client_entity,
            quantite=2,
            prix_unitaire=50.0,
            prix_achat=30.0,
            reference_ticket='FAC-TEST-12345'
        )
        url = reverse('stockapp:vente-facture-pdf', kwargs={'pk': vente.pk})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')

    def test_previsions_decision_view_renders(self):
        self.client.login(username='pos_cashier', password='password')
        response = self.client.get(reverse('stockapp:previsions-decision'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('items', response.context)
        self.assertIn('nb_critique', response.context)


class Phase2StockReliabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='phase2_user', password='password')
        self.produit = Produit.objects.create(
            nom='Disque SSD 1To',
            reference='SSD-1TO',
            stock_actuel=30,
            seuil_alerte=5,
            stock_maximum=100,
            prix_unitaire=80.0,
            prix_achat=50.0,
        )

    def test_vente_creation_reduces_stock_and_tracks_user(self):
        vente = Vente(
            produit=self.produit,
            quantite=10,
            prix_unitaire=80.0,
            prix_achat=50.0,
        )
        vente._current_user = self.user
        vente.save()

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 20)

        mouvement = MouvementStock.objects.filter(produit=self.produit, type_mouvement='VENTE').first()
        self.assertIsNotNone(mouvement)
        self.assertEqual(mouvement.quantite, 10)
        self.assertEqual(mouvement.stock_avant, 30)
        self.assertEqual(mouvement.stock_apres, 20)
        self.assertEqual(mouvement.utilisateur, self.user)

    def test_vente_modification_delta_increases_stock_when_quantite_reduced(self):
        vente = Vente.objects.create(
            produit=self.produit,
            quantite=10,
            prix_unitaire=80.0,
            prix_achat=50.0,
        )
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 20)

        # Réduction de la quantité vendue de 10 à 6 -> delta = -4 -> le stock doit remonter à 24
        vente.quantite = 6
        vente._current_user = self.user
        vente.save()

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 24)

        retour_mvt = MouvementStock.objects.filter(produit=self.produit, type_mouvement='RETOUR').first()
        self.assertIsNotNone(retour_mvt)
        self.assertEqual(retour_mvt.quantite, 4)
        self.assertEqual(retour_mvt.stock_avant, 20)
        self.assertEqual(retour_mvt.stock_apres, 24)

    def test_vente_modification_delta_reduces_stock_when_quantite_increased(self):
        vente = Vente.objects.create(
            produit=self.produit,
            quantite=5,
            prix_unitaire=80.0,
            prix_achat=50.0,
        )
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 25)

        # Augmentation de la quantité vendue de 5 à 9 -> delta = +4 -> le stock doit baisser à 21
        vente.quantite = 9
        vente.save()

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 21)

    def test_approvisionnement_modification_delta(self):
        appro = Approvisionnement.objects.create(
            produit=self.produit,
            quantite=20,
            fournisseur='Fournisseur Alpha'
        )
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 50)

        # Augmentation de l'appro de 20 à 30 -> delta = +10 -> stock = 60
        appro.quantite = 30
        appro.save()
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 60)

        # Réduction de l'appro de 30 à 15 -> delta = -15 -> stock = 45
        appro.quantite = 15
        appro.save()
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 45)

    def test_vente_form_validation_rejects_overselling(self):
        from stockapp.forms import VenteForm

        # Stock disponible = 30, tentative de vente de 40
        form_invalid = VenteForm(data={
            'produit': self.produit.id,
            'quantite': 40,
            'prix_unitaire': 80.0,
            'mode_paiement': 'ESPECES',
        })
        self.assertFalse(form_invalid.is_valid())
        self.assertIn('quantite', form_invalid.errors)

        # Vente de 25 <= 30 -> valide
        form_valid = VenteForm(data={
            'produit': self.produit.id,
            'quantite': 25,
            'prix_unitaire': 80.0,
            'mode_paiement': 'ESPECES',
        })
        self.assertTrue(form_valid.is_valid())


class Phase3PurchasesAndSuppliersTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        self.user = User.objects.create_user(username='phase3_manager', password='password', is_staff=True)
        self.produit = Produit.objects.create(
            nom='Souris Sans Fil Ergonomique',
            reference='MOU-001',
            stock_actuel=10,
            seuil_alerte=5,
            stock_maximum=100,
            prix_unitaire=25.0,
            prix_achat=12.0,
        )
        self.fournisseur = Fournisseur.objects.create(
            nom='Global Tech Supplies',
            telephone='+229 97 00 11 22',
            email='contact@globaltech.com',
            dette_fournisseur=Decimal('500.00'),
        )

    def test_approvisionnement_auto_syncs_fournisseur_model(self):
        from decimal import Decimal
        # 1. Enregistrement avec fournisseur textuel seul -> auto-crée ou retrouve Fournisseur FK
        appro1 = Approvisionnement.objects.create(
            produit=self.produit,
            quantite=15,
            fournisseur="Nouveau Fournisseur Auto",
            cout_unitaire=Decimal('14.50')
        )
        self.assertIsNotNone(appro1.fournisseur_fk)
        self.assertEqual(appro1.fournisseur_fk.nom, "Nouveau Fournisseur Auto")
        self.assertEqual(appro1.nom_fournisseur, "Nouveau Fournisseur Auto")

        # 2. Enregistrement avec fournisseur_fk seul -> auto-remplit le champ texte
        appro2 = Approvisionnement.objects.create(
            produit=self.produit,
            quantite=20,
            fournisseur_fk=self.fournisseur,
            cout_unitaire=Decimal('13.00')
        )
        self.assertEqual(appro2.fournisseur, self.fournisseur.nom)
        self.assertEqual(appro2.nom_fournisseur, self.fournisseur.nom)

    def test_approvisionnement_updates_prix_achat_and_creates_mouvement(self):
        from decimal import Decimal
        appro = Approvisionnement(
            produit=self.produit,
            quantite=25,
            fournisseur_fk=self.fournisseur,
            cout_unitaire=Decimal('15.50')
        )
        appro._current_user = self.user
        appro.save()

        # Vérifier que le stock a augmenté de 25 (10 -> 35)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 35)

        # Vérifier que le prix d'achat du produit a été actualisé
        self.assertEqual(self.produit.prix_achat, Decimal('15.50'))

        # Vérifier le mouvement de stock
        mvt = MouvementStock.objects.filter(produit=self.produit, type_mouvement='ACHAT').latest('date_mouvement')
        self.assertEqual(mvt.quantite, 25)
        self.assertEqual(mvt.utilisateur, self.user)
        self.assertIn("Global Tech Supplies", mvt.commentaire)

    def test_fournisseur_properties_and_debt_payment(self):
        from decimal import Decimal
        Approvisionnement.objects.create(
            produit=self.produit,
            quantite=10,
            fournisseur_fk=self.fournisseur,
            cout_unitaire=Decimal('20.00')
        )
        self.assertEqual(self.fournisseur.total_approvisionnements_count, 1)
        self.assertEqual(self.fournisseur.total_achats_montant, Decimal('200.00'))

        # Test règlement de dette
        self.client.login(username='phase3_manager', password='password')
        res = self.client.post(reverse('stockapp:fournisseur-regler-dette', kwargs={'pk': self.fournisseur.pk}), data={
            'montant': '200.00',
            'moyen_reglement': 'VIREMENT',
            'notes': 'Virement bancaire partiel'
        })
        self.assertEqual(res.status_code, 302)
        self.fournisseur.refresh_from_db()
        self.assertEqual(self.fournisseur.dette_fournisseur, Decimal('300.00'))

    def test_approvisionnement_views_and_deletion_reverts_stock(self):
        from decimal import Decimal
        self.client.login(username='phase3_manager', password='password')

        # Test vue liste approvisionnements
        res_list = self.client.get(reverse('stockapp:approvisionnements-list'))
        self.assertEqual(res_list.status_code, 200)

        # Test création via POST avec imputation dette
        res_create = self.client.post(reverse('stockapp:approvisionnements-list'), data={
            'produit': self.produit.pk,
            'fournisseur_fk': self.fournisseur.pk,
            'quantite': 10,
            'cout_unitaire': '15.00',
            'imputer_dette': 'on',
            'notes': 'Livraison test',
        })
        self.assertEqual(res_create.status_code, 302)

        appro = Approvisionnement.objects.filter(produit=self.produit).latest('id')
        self.assertEqual(appro.quantite, 10)
        self.fournisseur.refresh_from_db()
        # Dette initiale 500 + 150 = 650
        self.assertEqual(self.fournisseur.dette_fournisseur, Decimal('650.00'))

        # Suppression de l'approvisionnement -> stock réduit
        self.produit.refresh_from_db()
        stock_avant_suppr = self.produit.stock_actuel
        res_del = self.client.post(reverse('stockapp:approvisionnement-supprimer', kwargs={'pk': appro.pk}))
        self.assertEqual(res_del.status_code, 302)
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, stock_avant_suppr - 10)


class Phase4SalesAndPosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pos_cashier', password='password')
        self.client_entity = Client.objects.create(
            nom='Entreprise ABC Sarl',
            telephone='+229 95 11 22 33',
            email='contact@abc.bj',
            solde_credit=Decimal('100.00'),
        )
        self.produit1 = Produit.objects.create(
            nom='Clavier Mécanique RGB',
            reference='KB-001',
            stock_actuel=15,
            seuil_alerte=3,
            stock_maximum=50,
            prix_unitaire=50.0,
            prix_achat=30.0,
        )
        self.produit2 = Produit.objects.create(
            nom='Tapis de Souris XXL',
            reference='PAD-001',
            stock_actuel=20,
            seuil_alerte=5,
            stock_maximum=100,
            prix_unitaire=15.0,
            prix_achat=8.0,
        )

    def test_caisse_pos_multi_items_atomic_and_stock_decrement(self):
        import json
        self.client.login(username='pos_cashier', password='password')

        cart_payload = json.dumps([
            {'produit_id': self.produit1.id, 'quantite': 2, 'prix_unitaire': 50.0},
            {'produit_id': self.produit2.id, 'quantite': 3, 'prix_unitaire': 15.0},
        ])

        res = self.client.post(reverse('stockapp:caisse-pos'), data={
            'cart_data': cart_payload,
            'client_id': self.client_entity.id,
            'mode_paiement': 'ESPECES',
            'remise_globale': '5.00',
            'notes': 'Vente caisse multi-produits',
        })
        self.assertEqual(res.status_code, 302)

        self.produit1.refresh_from_db()
        self.produit2.refresh_from_db()
        self.assertEqual(self.produit1.stock_actuel, 13)
        self.assertEqual(self.produit2.stock_actuel, 17)

        ventes = Vente.objects.filter(client=self.client_entity)
        self.assertEqual(ventes.count(), 2)
        ticket_ref = ventes.first().reference_ticket
        self.assertTrue(ticket_ref.startswith('TCK-'))
        self.assertEqual(ventes.last().reference_ticket, ticket_ref)

    def test_caisse_pos_credit_sale_updates_client_solde_credit(self):
        import json
        self.client.login(username='pos_cashier', password='password')

        initial_credit = self.client_entity.solde_credit
        cart_payload = json.dumps([
            {'produit_id': self.produit1.id, 'quantite': 2, 'prix_unitaire': 50.0},
        ])

        res = self.client.post(reverse('stockapp:caisse-pos'), data={
            'cart_data': cart_payload,
            'client_id': self.client_entity.id,
            'mode_paiement': 'CREDIT',
            'remise_globale': '0.00',
            'notes': 'Vente à crédit accordée',
        })
        self.assertEqual(res.status_code, 302)

        self.client_entity.refresh_from_db()
        self.assertEqual(self.client_entity.solde_credit, initial_credit + Decimal('100.00'))

    def test_caisse_pos_credit_sale_requires_client(self):
        import json
        self.client.login(username='pos_cashier', password='password')

        cart_payload = json.dumps([
            {'produit_id': self.produit1.id, 'quantite': 1, 'prix_unitaire': 50.0},
        ])

        res = self.client.post(reverse('stockapp:caisse-pos'), data={
            'cart_data': cart_payload,
            'client_id': '',
            'mode_paiement': 'CREDIT',
            'remise_globale': '0.00',
        })
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Vente.objects.filter(mode_paiement='CREDIT').exists())

    def test_caisse_pos_rejects_insufficient_stock(self):
        import json
        self.client.login(username='pos_cashier', password='password')

        cart_payload = json.dumps([
            {'produit_id': self.produit1.id, 'quantite': 999, 'prix_unitaire': 50.0},
        ])

        res = self.client.post(reverse('stockapp:caisse-pos'), data={
            'cart_data': cart_payload,
            'mode_paiement': 'ESPECES',
        })
        self.assertEqual(res.status_code, 302)
        self.produit1.refresh_from_db()
        self.assertEqual(self.produit1.stock_actuel, 15)

    def test_pdf_ticket_and_facture_generation(self):
        self.client.login(username='pos_cashier', password='password')
        vente = Vente.objects.create(
            produit=self.produit1,
            client=self.client_entity,
            quantite=1,
            prix_unitaire=50.0,
            mode_paiement='CREDIT',
            reference_ticket='TCK-TEST-PDF'
        )

        res_ticket = self.client.get(reverse('stockapp:vente-recu-pdf', kwargs={'pk': vente.pk}))
        self.assertEqual(res_ticket.status_code, 200)
        self.assertEqual(res_ticket['Content-Type'], 'application/pdf')

        res_facture = self.client.get(reverse('stockapp:vente-facture-pdf', kwargs={'pk': vente.pk}))
        self.assertEqual(res_facture.status_code, 200)
        self.assertEqual(res_facture['Content-Type'], 'application/pdf')


class Phase5DashboardExecutiveTests(TestCase):
    """
    Suite de tests de validation pour la Phase 5 : Dashboard Exécutif & Centre de Pilotage Commercial.
    Vérifie les agrégations SQL pures, les métriques périodiques (J vs J-1, M vs M-1),
    le baromètre de santé du stock et le rendu du dashboard.
    """
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='exec_director', password='password')
        self.cat = Categorie.objects.create(nom='Informatique')
        self.client_entity = Client.objects.create(nom='Cabinet Alpha', solde_credit=Decimal('150.00'))
        self.fournisseur = Fournisseur.objects.create(nom='Tech Import', dette_fournisseur=Decimal('500.00'))

        # 4 produits pour tester les 4 statuts de stock
        # 1. Rupture stricte (stock = 0)
        self.p_rupture = Produit.objects.create(
            nom='Souris Sans Fil', reference='MOU-01', sku='SKU-MOU-01',
            prix_achat=10.0, prix_unitaire=20.0,
            stock_actuel=0, seuil_alerte=5, stock_maximum=50,
            categorie=self.cat
        )
        # 2. Stock faible (0 < stock <= seuil)
        self.p_faible = Produit.objects.create(
            nom='Clavier RGB', reference='KEY-01', sku='SKU-KEY-01',
            prix_achat=25.0, prix_unitaire=50.0,
            stock_actuel=3, seuil_alerte=5, stock_maximum=50,
            categorie=self.cat
        )
        # 3. Stock optimal (seuil < stock < max)
        self.p_optimal = Produit.objects.create(
            nom='Ecran 27 pouces', reference='SCR-01', sku='SKU-SCR-01',
            prix_achat=100.0, prix_unitaire=180.0,
            stock_actuel=20, seuil_alerte=5, stock_maximum=50,
            categorie=self.cat
        )
        # 4. Surstock (stock >= max)
        self.p_surstock = Produit.objects.create(
            nom='Câble HDMI 2m', reference='CAB-01', sku='SKU-CAB-01',
            prix_achat=2.0, prix_unitaire=10.0,
            stock_actuel=60, seuil_alerte=10, stock_maximum=50,
            categorie=self.cat
        )

    def test_stock_health_and_aggregations_sql(self):
        """Vérifie le calcul SQL pur des stocks, valeurs et statuts de santé."""
        from stockapp.selectors import get_dashboard_metrics

        metrics = get_dashboard_metrics()

        # Total produits & stocks : 0 + 3 + 20 + 60 = 83 unités sur 4 produits
        self.assertEqual(metrics['total_produits'], 4)
        self.assertEqual(metrics['stock_total'], 83)

        # Valeur achat : (0*10) + (3*25) + (20*100) + (60*2) = 0 + 75 + 2000 + 120 = 2195.00
        self.assertEqual(metrics['valeur_stock_achat'], Decimal('2195.00'))

        # Valeur vente : (0*20) + (3*50) + (20*180) + (60*10) = 0 + 150 + 3600 + 600 = 4350.00
        self.assertEqual(metrics['valeur_stock_vente'], Decimal('4350.00'))

        # Marge estimée : 4350 - 2195 = 2155.00
        self.assertEqual(metrics['marge_estimee_stock'], Decimal('2155.00'))

        # Statuts de santé
        self.assertEqual(metrics['nb_rupture_stricte'], 1)
        self.assertEqual(metrics['nb_stock_faible'], 1)
        self.assertEqual(metrics['nb_stock_normal'], 1)
        self.assertEqual(metrics['nb_surstock'], 1)
        self.assertEqual(metrics['produits_en_rupture'], 2)  # rupture + faible
        self.assertEqual(metrics['rupture_rate'], 50.0)      # 2/4 = 50%

        # Dettes et créances
        self.assertEqual(metrics['creances_clients'], Decimal('150.00'))
        self.assertEqual(metrics['dettes_fournisseurs'], Decimal('500.00'))

    def test_periodic_sales_metrics_and_growth(self):
        """Vérifie le calcul des ventes du jour vs hier et du mois en cours."""
        from stockapp.selectors import get_dashboard_metrics
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        yesterday = now - timedelta(days=1)

        # Vente d'hier : 1 x 50.00 (achat 25.00), prix net = 50.00
        v_hier = Vente.objects.create(
            produit=self.p_faible,
            quantite=1,
            prix_unitaire=50.0,
            prix_achat=25.0,
            remise=Decimal('0.00'),
            mode_paiement='ESPECES'
        )
        # Forcer la date de vente à hier
        Vente.objects.filter(pk=v_hier.pk).update(date_vente=yesterday)

        # Vente d'aujourd'hui : 2 x 180.00 = 360.00 avec 10.00 de remise = 350.00 net (achat 2x100 = 200.00, benef = 150.00)
        Vente.objects.create(
            produit=self.p_optimal,
            quantite=2,
            prix_unitaire=180.0,
            prix_achat=100.0,
            remise=Decimal('10.00'),
            mode_paiement='CARTE'
        )

        metrics = get_dashboard_metrics()

        # Ventes du jour
        self.assertEqual(metrics['ca_jour'], Decimal('350.00'))
        self.assertEqual(metrics['benef_jour'], Decimal('150.00'))

        # Ventes d'hier
        self.assertEqual(metrics['ca_hier'], Decimal('50.00'))

        # Évolution du jour : (350 - 50) / 50 * 100 = +600.0%
        self.assertEqual(metrics['evolution_jour_pct'], 600.0)

        # Mois en cours : contient hier et aujourd'hui = 50 + 350 = 400.00
        self.assertEqual(metrics['ca_mois'], Decimal('400.00'))
        self.assertEqual(metrics['benef_mois'], Decimal('175.00'))

        # 14 jours chart dates
        self.assertEqual(len(metrics['chart_dates']), 14)
        self.assertEqual(len(metrics['chart_sales_values']), 14)
        self.assertEqual(metrics['chart_sales_values'][-1], 350.0) # aujourd'hui
        self.assertEqual(metrics['chart_sales_values'][-2], 50.0)  # hier

    def test_empty_database_metrics_does_not_crash(self):
        """Vérifie que get_dashboard_metrics ne lève aucune exception sur une base vide."""
        from stockapp.selectors import get_dashboard_metrics

        # Supprimer toutes les données
        Produit.objects.all().delete()
        Vente.objects.all().delete()
        Client.objects.all().delete()
        Fournisseur.objects.all().delete()

        metrics = get_dashboard_metrics()
        self.assertEqual(metrics['total_produits'], 0)
        self.assertEqual(metrics['stock_total'], 0)
        self.assertEqual(metrics['valeur_stock_achat'], Decimal('0.00'))
        self.assertEqual(metrics['valeur_stock_vente'], Decimal('0.00'))
        self.assertEqual(metrics['chiffre_affaires_total'], Decimal('0.00'))
        self.assertEqual(metrics['benefice_net_total'], Decimal('0.00'))
        self.assertEqual(metrics['evolution_jour_pct'], 0.0)
        self.assertEqual(metrics['evolution_mois_pct'], 0.0)

    def test_dashboard_view_renders_successfully(self):
        """Vérifie que la vue dashboard retourne 200 OK et contient les indicateurs enrichis."""
        self.client.login(username='exec_director', password='password')
        response = self.client.get(reverse('stockapp:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stockapp/dashboard.html')
        self.assertIn('stats', response.context)
        self.assertIn('chart_dates_json', response.context)
        self.assertIn('chart_sales_values_json', response.context)
        self.assertIn('top_produits_ventes', response.context)

        # Vérifier la présence des éléments de la phase 5 dans le HTML
        content = response.content.decode('utf-8')
        self.assertIn("État de Santé du Catalogue Stock", content)
        self.assertIn("Rupture stricte", content)
        self.assertIn("Surstockage", content)
        self.assertIn("Aujourd'hui :", content)


class Phase6AnalyticsTests(TestCase):
    """
    Suite de tests de validation pour la Phase 6 : Analytics Avancé & Performance Financière.
    Vérifie le sélecteur get_advanced_analytics_metrics, la segmentation matricielle (BCG),
    le calcul du panier moyen, les marges par catégorie et le rendu web.
    """
    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='analytics_director', password='password')

        self.cat_info = Categorie.objects.create(nom='Informatique')
        self.cat_bur = Categorie.objects.create(nom='Bureautique')
        self.client_corp = Client.objects.create(nom='Entreprise Beta')

        # 4 produits vendus configurés pour couvrir les 4 quadrants de la matrice SMART-TECH
        # Produit 1 : Star (Fort volume, Forte marge)
        self.p_star = Produit.objects.create(
            nom='Laptop Pro', reference='LAP-PRO', sku='SKU-LAP-PRO',
            prix_achat=50.0, prix_unitaire=200.0,
            stock_actuel=30, seuil_alerte=5, stock_maximum=100,
            categorie=self.cat_info
        )
        # Produit 2 : Vache à Lait (Fort volume, Marge modérée)
        self.p_cow = Produit.objects.create(
            nom='Papier Ramette A4', reference='PAP-A4', sku='SKU-PAP-A4',
            prix_achat=85.0, prix_unitaire=100.0,
            stock_actuel=50, seuil_alerte=10, stock_maximum=150,
            categorie=self.cat_bur
        )
        # Produit 3 : Fort Potentiel (Faible volume, Forte marge)
        self.p_pot = Produit.objects.create(
            nom='Serveur NAS', reference='NAS-01', sku='SKU-NAS-01',
            prix_achat=100.0, prix_unitaire=500.0,
            stock_actuel=10, seuil_alerte=2, stock_maximum=20,
            categorie=self.cat_info
        )
        # Produit 4 : Dormant (Faible volume, Faible marge)
        self.p_dorm = Produit.objects.create(
            nom='Stylos Paquet', reference='STY-01', sku='SKU-STY-01',
            prix_achat=18.0, prix_unitaire=20.0,
            stock_actuel=40, seuil_alerte=5, stock_maximum=80,
            categorie=self.cat_bur
        )
        # Produit 5 : Jamais vendu
        self.p_unsold = Produit.objects.create(
            nom='Tapis de Souris', reference='TAP-01', sku='SKU-TAP-01',
            prix_achat=3.0, prix_unitaire=8.0,
            stock_actuel=20, seuil_alerte=5, stock_maximum=50,
            categorie=self.cat_info
        )

        # Enregistrement de ventes avec des tickets distincts et des modes de paiement variés
        # Vente Star : 20 unités à 200 = 4000 CA, 1000 COGS, 3000 Benef (marge = 75%)
        Vente.objects.create(
            produit=self.p_star, client=self.client_corp, quantite=20,
            prix_unitaire=200.0, prix_achat=50.0, remise=Decimal('0.00'),
            mode_paiement='CARTE', reference_ticket='TCK-AN-001'
        )
        # Vente Cow : 20 unités à 100 = 2000 CA, 1700 COGS, 300 Benef (marge = 15%)
        Vente.objects.create(
            produit=self.p_cow, client=self.client_corp, quantite=20,
            prix_unitaire=100.0, prix_achat=85.0, remise=Decimal('0.00'),
            mode_paiement='ESPECES', reference_ticket='TCK-AN-002'
        )
        # Vente Potentiel : 2 unités à 500 = 1000 CA, 200 COGS, 800 Benef (marge = 80%)
        Vente.objects.create(
            produit=self.p_pot, client=self.client_corp, quantite=2,
            prix_unitaire=500.0, prix_achat=100.0, remise=Decimal('0.00'),
            mode_paiement='MOBILE_MONEY', reference_ticket='TCK-AN-003'
        )
        # Vente Dormant : 2 unités à 20 = 40 CA, 36 COGS, 4 Benef (marge = 10%)
        Vente.objects.create(
            produit=self.p_dorm, client=self.client_corp, quantite=2,
            prix_unitaire=20.0, prix_achat=18.0, remise=Decimal('0.00'),
            mode_paiement='CREDIT', reference_ticket='TCK-AN-004'
        )

    def test_advanced_analytics_metrics_calculation(self):
        """Vérifie le calcul global du CA, COGS, marge brute et panier moyen."""
        from stockapp.selectors import get_advanced_analytics_metrics

        metrics = get_advanced_analytics_metrics()

        # CA Global : 4000 + 2000 + 1000 + 40 = 7040.00
        self.assertEqual(metrics['ca_global'], Decimal('7040.00'))

        # COGS Global : 1000 + 1700 + 200 + 36 = 2936.00
        self.assertEqual(metrics['cogs_global'], Decimal('2936.00'))

        # Marge Brute Globale : 7040 - 2936 = 4104.00
        self.assertEqual(metrics['benefice_global'], Decimal('4104.00'))

        # Taux de marge moyen : 4104 / 7040 * 100 = 58.3%
        self.assertAlmostEqual(metrics['taux_marge_global'], 58.3, places=1)

        # Volume total vendu : 20 + 20 + 2 + 2 = 44
        self.assertEqual(metrics['volume_global'], 44)

        # Nombre de tickets : 4 tickets distincts
        self.assertEqual(metrics['nb_tickets'], 4)

        # Panier moyen : 7040 / 4 = 1760.00
        self.assertEqual(metrics['panier_moyen'], 1760.00)

        # Articles non vendus
        self.assertEqual(metrics['articles_jamais_vendus'], 1)

    def test_bcg_product_matrix_segmentation(self):
        """Vérifie la classification matricielle SMART-TECH des 4 catégories de produits."""
        from stockapp.selectors import get_advanced_analytics_metrics

        metrics = get_advanced_analytics_metrics()
        counts = metrics['counts_matrice']

        # Chaque produit doit correspondre exactement à son quadrant
        self.assertEqual(counts['stars'], 1)
        self.assertEqual(counts['cash_cows'], 1)
        self.assertEqual(counts['potentials'], 1)
        self.assertEqual(counts['dormants'], 1)

        prod_map = {p['produit_id']: p for p in metrics['prod_summary']}

        self.assertEqual(prod_map[self.p_star.id]['matrice_cat'], 'STAR')
        self.assertEqual(prod_map[self.p_cow.id]['matrice_cat'], 'CASH_COW')
        self.assertEqual(prod_map[self.p_pot.id]['matrice_cat'], 'POTENTIAL')
        self.assertEqual(prod_map[self.p_dorm.id]['matrice_cat'], 'DORMANT')

    def test_category_and_payment_breakdown(self):
        """Vérifie l'agrégation par catégorie et par mode de paiement."""
        from stockapp.selectors import get_advanced_analytics_metrics

        metrics = get_advanced_analytics_metrics()

        # Catégories
        cats = {c['nom']: c for c in metrics['cat_summary']}
        self.assertIn('Informatique', cats)
        self.assertIn('Bureautique', cats)
        # Informatique : Laptop (4000) + NAS (1000) = 5000 CA
        self.assertEqual(cats['Informatique']['chiffre_affaires'], Decimal('5000.00'))
        # Bureautique : Papier (2000) + Stylos (40) = 2040 CA
        self.assertEqual(cats['Bureautique']['chiffre_affaires'], Decimal('2040.00'))

        # Modes de paiement
        modes = {m['mode_code']: m for m in metrics['modes_summary']}
        self.assertIn('CARTE', modes)
        self.assertIn('ESPECES', modes)
        self.assertIn('MOBILE_MONEY', modes)
        self.assertIn('CREDIT', modes)
        self.assertEqual(modes['CARTE']['total_ca'], Decimal('4000.00'))
        self.assertEqual(modes['ESPECES']['total_ca'], Decimal('2000.00'))

    def test_empty_sales_database_returns_safe_defaults(self):
        """Vérifie que get_advanced_analytics_metrics ne crash pas sur une base sans ventes."""
        from stockapp.selectors import get_advanced_analytics_metrics

        Vente.objects.all().delete()
        Produit.objects.all().delete()

        metrics = get_advanced_analytics_metrics()
        self.assertEqual(metrics['ca_global'], Decimal('0.00'))
        self.assertEqual(metrics['cogs_global'], Decimal('0.00'))
        self.assertEqual(metrics['benefice_global'], Decimal('0.00'))
        self.assertEqual(metrics['panier_moyen'], 0.0)
        self.assertEqual(metrics['taux_marge_global'], 0.0)
        self.assertEqual(len(metrics['cat_summary']), 0)
        self.assertEqual(len(metrics['prod_summary']), 0)

    def test_analytics_view_renders_200_and_contains_kpi(self):
        """Vérifie que la vue analytics_view répond avec succès (200 OK) et affiche les indicateurs."""
        self.client.login(username='analytics_director', password='password')
        response = self.client.get(reverse('stockapp:analytics'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stockapp/analytics.html')
        self.assertIn('ca_global', response.context)
        self.assertIn('panier_moyen', response.context)
        self.assertIn('cat_summary', response.context)
        self.assertIn('prod_summary', response.context)
        self.assertIn('chart_cat_labels_json', response.context)
        self.assertIn('chart_modes_labels_json', response.context)

        content = response.content.decode('utf-8')
        self.assertIn("Performance Commerciale & Marges", content)
        self.assertIn("Matrice de Segmentation Commerciale des Produits", content)
        self.assertIn("Produits Stars", content)
        self.assertIn("Vaches à Lait", content)
        self.assertIn("Rentabilité & Marges par Catégorie de Produits", content)


class Phase7FinanceTests(TestCase):
    """
    Tests de validation du Module Financier & Trésorerie (Phase 7).
    Couvre :
    - Calcul du P&L (CA Net, COGS, Marge Brute, Charges OPEX, Résultat Net)
    - Trésorerie & Solvabilité (Cash encaissé, Créances clients, Dettes fournisseurs, Achats réglés, Flux net, Position nette)
    - Cas limites / Base vierge (safe defaults)
    - Vue finances_view (affichage 200 OK, création de dépense POST)
    - Vue depense_supprimer
    - Export du Rapport Financier Exécutif en PDF
    """
    def setUp(self):
        self.user = User.objects.create_user(username='finance_officer', password='password', is_staff=True)
        self.cat = Categorie.objects.create(nom='Fournitures')

        # Produit A : PA=100, PV=150
        self.p1 = Produit.objects.create(
            nom='Imprimante Laser',
            reference='IMP-001',
            categorie=self.cat,
            stock_actuel=20,
            prix_achat=100.0,
            prix_unitaire=150.0
        )

        # Client avec solde crédit
        self.client_vip = Client.objects.create(
            nom='Entreprise Alpha',
            telephone='97000000',
            solde_credit=500.0
        )

        # Fournisseur avec dette
        self.fournisseur_hp = Fournisseur.objects.create(
            nom='HP Distribution',
            telephone='21000000',
            dette_fournisseur=400.0
        )

        # Approvisionnement reçu : 10 unités à 100 = 1000. Dette fournisseur = 400 => Achats réglés = 600.
        self.appro = Approvisionnement.objects.create(
            produit=self.p1,
            fournisseur_fk=self.fournisseur_hp,
            quantite=10,
            cout_unitaire=Decimal('100.00'),
            statut='RECU'
        )

        # Vente 1 : 4 unités au comptant (ESPECES) à 150 = 600 CA. COGS = 4 * 100 = 400. Marge = 200.
        Vente.objects.create(
            produit=self.p1,
            quantite=4,
            prix_unitaire=Decimal('150.00'),
            prix_achat=Decimal('100.00'),
            remise=Decimal('0.00'),
            mode_paiement='ESPECES'
        )

        # Vente 2 : 2 unités à CRÉDIT à 150 = 300 CA. COGS = 2 * 100 = 200. Marge = 100.
        Vente.objects.create(
            produit=self.p1,
            client=self.client_vip,
            quantite=2,
            prix_unitaire=Decimal('150.00'),
            prix_achat=Decimal('100.00'),
            remise=Decimal('0.00'),
            mode_paiement='CREDIT'
        )

        # Total CA Net = 900. Total COGS = 600. Total Marge Brute = 300.
        # Cash Encaissé = 600. Ventes Crédit = 300.

        # Dépenses (OPEX) : Loyer (150) + Énergie (50) = 200
        self.dep1 = Depense.objects.create(
            titre='Loyer Commercial',
            categorie='LOYER',
            montant=Decimal('150.00'),
            date_depense=timezone.now().date(),
            beneficiaire='Bailleur Immo',
            utilisateur=self.user
        )
        self.dep2 = Depense.objects.create(
            titre='Facture Électricité',
            categorie='ELECTRICITE',
            montant=Decimal('50.00'),
            date_depense=timezone.now().date(),
            beneficiaire='Compagnie Énergie',
            utilisateur=self.user
        )

    def test_financial_metrics_calculation(self):
        """Vérifie l'exactitude des calculs P&L, trésorerie et liquidités de get_financial_metrics."""
        from stockapp.selectors import get_financial_metrics

        metrics = get_financial_metrics()

        self.assertEqual(metrics['ca_total_net'], Decimal('900.00'))
        self.assertEqual(metrics['cogs_total'], Decimal('600.00'))
        self.assertEqual(metrics['marge_brute'], Decimal('300.00'))
        self.assertEqual(metrics['cash_encaisse'], Decimal('600.00'))
        self.assertEqual(metrics['ventes_credit'], Decimal('300.00'))
        self.assertEqual(metrics['creances_clients'], Decimal('500.00'))
        self.assertEqual(metrics['taux_recouvrement'], 66.7)

        # Achats & Fournisseurs
        self.assertEqual(metrics['total_achats'], Decimal('1000.00'))
        self.assertEqual(metrics['dettes_fournisseurs'], Decimal('400.00'))
        self.assertEqual(metrics['achats_regles'], Decimal('600.00'))

        # Dépenses & P&L
        self.assertEqual(metrics['total_depenses'], Decimal('200.00'))
        self.assertEqual(metrics['resultat_net'], Decimal('100.00'))
        self.assertEqual(metrics['taux_rentabilite_nette'], 11.1)

        # Trésorerie
        self.assertEqual(metrics['total_cash_in'], Decimal('600.00'))
        self.assertEqual(metrics['total_cash_out'], Decimal('800.00'))
        self.assertEqual(metrics['flux_net_cash'], Decimal('-200.00'))
        self.assertEqual(metrics['position_nette_globale'], Decimal('500.00'))

        # Catégories de dépenses
        dep_names = [d['nom'] for d in metrics['depenses_par_categorie']]
        self.assertIn('Loyer & Charges locatives', dep_names)
        self.assertIn('Électricité & Eau', dep_names)

    def test_empty_financial_database_safe_defaults(self):
        """Vérifie que get_financial_metrics gère les bases vides sans exception."""
        from stockapp.selectors import get_financial_metrics

        Vente.objects.all().delete()
        Depense.objects.all().delete()
        Approvisionnement.objects.all().delete()
        Client.objects.all().delete()
        Fournisseur.objects.all().delete()
        Produit.objects.all().delete()

        metrics = get_financial_metrics()
        self.assertEqual(metrics['ca_total_net'], Decimal('0.00'))
        self.assertEqual(metrics['marge_brute'], Decimal('0.00'))
        self.assertEqual(metrics['total_depenses'], Decimal('0.00'))
        self.assertEqual(metrics['resultat_net'], Decimal('0.00'))
        self.assertEqual(metrics['taux_recouvrement'], 0.0)
        self.assertEqual(metrics['taux_rentabilite_nette'], 0.0)
        self.assertEqual(metrics['position_nette_globale'], Decimal('0.00'))
        self.assertEqual(len(metrics['depenses_par_categorie']), 0)

    def test_finances_view_get(self):
        """Vérifie l'accès GET à la vue finances avec contexte complet."""
        self.client.login(username='finance_officer', password='password')
        response = self.client.get(reverse('stockapp:finances'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stockapp/finances.html')
        self.assertIn('metrics', response.context)
        self.assertIn('form', response.context)
        self.assertIn('chart_cashflow_labels_json', response.context)
        self.assertIn('chart_depenses_labels_json', response.context)

        content = response.content.decode('utf-8')
        self.assertIn("Centre Financier & Rentabilité Nette", content)
        self.assertIn("Compte de Résultat d'Exploitation (P&L)", content)
        self.assertIn("Bilan de Trésorerie & Solvabilité", content)
        self.assertIn("Loyer Commercial", content)

    def test_finances_view_post_creates_depense(self):
        """Vérifie la création d'une dépense via POST dans finances_view."""
        self.client.login(username='finance_officer', password='password')
        post_data = {
            'titre': 'Abonnement Internet Fibre',
            'categorie': 'INTERNET',
            'montant': '45.00',
            'date_depense': timezone.now().date().isoformat(),
            'beneficiaire': 'Fournisseur Telecom',
            'notes': 'Facture mensuelle',
        }
        response = self.client.post(reverse('stockapp:finances'), post_data)
        self.assertRedirects(response, reverse('stockapp:finances'))

        created = Depense.objects.filter(titre='Abonnement Internet Fibre').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.montant, Decimal('45.00'))
        self.assertEqual(created.utilisateur, self.user)

    def test_depense_supprimer(self):
        """Vérifie la suppression d'une dépense."""
        self.client.login(username='finance_officer', password='password')
        url = reverse('stockapp:depense-supprimer', kwargs={'pk': self.dep1.pk})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('stockapp:finances'))
        self.assertFalse(Depense.objects.filter(pk=self.dep1.pk).exists())

    def test_finance_report_pdf(self):
        """Vérifie la génération du rapport financier PDF officiel."""
        self.client.login(username='finance_officer', password='password')
        response = self.client.get(reverse('stockapp:finance-report-pdf'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))


class Phase8PredictiveAiAndDecisionTests(TestCase):
    """
    Suite de tests de validation pour la Phase 8 :
    Intelligence Commerciale & Aide à la Décision Opérationnelle.
    Couvre :
    - Calcul mathématique du Point de Commande (ROP) et Stock de Sécurité dynamique (SS)
    - Détection des produits dormants (Dead stock / capital immobilisé)
    - Gestion des cas de rupture critique
    - Séries temporelles passées vs futures pour le simulateur Chart.js
    - Vue previsions_decision_view avec KPIs exécutifs et budget global
    - API JSON du simulateur prédictif (produit_prevision_chart_api)
    - Rapport PDF du plan décisionnel de réapprovisionnement (previsions_decision_pdf)
    """
    def setUp(self):
        self.user = User.objects.create_user(username='ai_planner', password='password')
        self.cat = Categorie.objects.create(nom='High-Tech')

        # Produit A : Actif avec ventes régulières
        self.p_active = Produit.objects.create(
            nom='Souris Gamer Pro',
            reference='MOU-001',
            categorie=self.cat,
            stock_actuel=8,
            seuil_alerte=5,
            stock_maximum=40,
            prix_achat=25.0,
            prix_unitaire=50.0
        )

        # Produit B : En rupture totale
        self.p_rupture = Produit.objects.create(
            nom='Clavier Mécanique',
            reference='KEY-002',
            categorie=self.cat,
            stock_actuel=0,
            seuil_alerte=4,
            stock_maximum=30,
            prix_achat=45.0,
            prix_unitaire=90.0
        )

        # Produit C : Dormant (stock > 0 mais 0 vente sur 30j)
        self.p_dormant = Produit.objects.create(
            nom='Tapis de Souris Vintage',
            reference='PAD-003',
            categorie=self.cat,
            stock_actuel=25,
            seuil_alerte=3,
            stock_maximum=50,
            prix_achat=10.0,
            prix_unitaire=20.0
        )

        # Générer des ventes pour p_active sur les 10 derniers jours
        today = timezone.now()
        for i in range(1, 8):
            sale_date = today - timedelta(days=i)
            v = Vente.objects.create(
                produit=self.p_active,
                quantite=3,
                prix_unitaire=Decimal('50.00'),
                prix_achat=Decimal('25.00'),
                remise=Decimal('0.00'),
                mode_paiement='ESPECES'
            )
            # Mettre à jour la date_vente pour refléter l'historique
            Vente.objects.filter(pk=v.pk).update(date_vente=sale_date)

    def test_calculate_reorder_point_and_safety_stock_active_product(self):
        """Vérifie le calcul du stock de sécurité, point de commande (ROP) et budget pour un produit actif."""
        from stockapp.services.prediction_service import calculate_reorder_point_and_safety_stock

        intel = calculate_reorder_point_and_safety_stock(self.p_active, lead_time_days=5, service_level_z=1.65, lookback_days=30)

        self.assertGreater(intel['conso_moyenne'], 0.0)
        self.assertGreaterEqual(intel['safety_stock'], self.p_active.seuil_alerte)
        self.assertGreater(intel['rop'], intel['safety_stock'])
        self.assertIn(intel['statut_code'], ['CRITIQUE', 'ELEVE', 'MODERE', 'FAIBLE'])
        self.assertIn('Pourquoi commander ?', intel['explication']) if 'Pourquoi' in intel['explication'] else self.assertTrue(len(intel['explication']) > 10)
        self.assertFalse(intel['is_dormant'])
        self.assertGreater(intel['budget_estime'], 0.0)

    def test_calculate_reorder_point_and_safety_stock_dormant_product(self):
        """Vérifie la qualification en produit dormant quand aucune vente n'est survenue en 30 jours."""
        from stockapp.services.prediction_service import calculate_reorder_point_and_safety_stock

        intel = calculate_reorder_point_and_safety_stock(self.p_dormant, lead_time_days=5, lookback_days=30)

        self.assertTrue(intel['is_dormant'])
        self.assertEqual(intel['statut_code'], 'DORMANT')
        self.assertEqual(intel['qte_recommandee'], 0)
        self.assertIn('Capital immobilisé', intel['explication'])

    def test_calculate_reorder_point_and_safety_stock_critical_stockout(self):
        """Vérifie que la rupture effective génère un niveau critique et une commande recommandée urgente."""
        from stockapp.services.prediction_service import calculate_reorder_point_and_safety_stock

        intel = calculate_reorder_point_and_safety_stock(self.p_rupture, lead_time_days=5, lookback_days=30)

        self.assertEqual(intel['statut_code'], 'CRITIQUE')
        self.assertTrue(intel['action_requise'])
        self.assertGreaterEqual(intel['qte_recommandee'], 10)
        self.assertIn("Rupture totale", intel['explication'])

    def test_get_product_time_series_data_format(self):
        """Vérifie la structure des séries temporelles (passé + projections) pour Chart.js."""
        from stockapp.services.prediction_service import get_product_time_series_data

        data = get_product_time_series_data(self.p_active, days_lookback=14, days_ahead=14)

        self.assertIn('labels', data)
        self.assertIn('historical', data)
        self.assertIn('forecast', data)
        self.assertEqual(len(data['labels']), 29) # 14 passé + 1 aujourd'hui + 14 futur
        self.assertEqual(len(data['historical']), 29)
        self.assertEqual(len(data['forecast']), 29)
        self.assertEqual(data['stock_actuel'], self.p_active.stock_actuel)
        self.assertGreater(data['rop'], 0)

    def test_previsions_decision_view_renders_200(self):
        """Vérifie le chargement de la vue previsions_decision avec les indicateurs Phase 8."""
        self.client.login(username='ai_planner', password='password')
        response = self.client.get(reverse('stockapp:previsions-decision'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stockapp/previsions_decision.html')
        self.assertIn('items', response.context)
        self.assertIn('nb_critique', response.context)
        self.assertIn('nb_dormant', response.context)
        self.assertIn('budget_total_reappro', response.context)
        self.assertIn('simulator_data', response.context)

        content = response.content.decode('utf-8')
        self.assertIn("Tableau Stratégique d'Aide à la Décision", content)
        self.assertIn("Simulateur Prédictif", content)
        self.assertIn("Point Commande (ROP)", content)
        self.assertIn("Souris Gamer Pro", content)

    def test_produit_prevision_chart_api(self):
        """Vérifie que l'endpoint JSON renvoie bien les séries temporelles du produit."""
        self.client.login(username='ai_planner', password='password')
        url = reverse('stockapp:previsions-decision-chart-api', kwargs={'pk': self.p_active.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['produit_id'], self.p_active.pk)
        self.assertEqual(data['produit_nom'], self.p_active.nom)
        self.assertIn('labels', data)
        self.assertIn('forecast', data)

    def test_previsions_decision_pdf(self):
        """Vérifie la génération du rapport PDF d'aide à la décision."""
        self.client.login(username='ai_planner', password='password')
        response = self.client.get(reverse('stockapp:previsions-decision-pdf'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))


class Phase9RolesAndAuditTests(TestCase):
    """
    Suite de tests de validation pour la Phase 9 :
    Rôles, Permissions & Journal d'Audit Exécutif.
    Couvre :
    - Helpers de rôles (user_has_role, get_user_primary_role)
    - Décorateur @role_required pour le contrôle d'accès web et AJAX
    - Enregistrement immuable des événements sensibles via JournalAudit.log_action
    - Traçabilité des créations de produits et des modifications tarifaires
    - Traçabilité des ajustements manuels de stock
    - Traçabilité des suppressions critiques (produits, ventes, dépenses)
    - Traçabilité des règlements de dettes fournisseurs
    - Tableau de bord exécutif du Journal d'Audit (vue, filtres par action/module/utilisateur)
    - Exportation sécurisée en CSV avec métadonnées d'audit
    """
    def setUp(self):
        from django.contrib.auth.models import Group
        self.grp_admin = Group.objects.create(name='Admin')
        self.grp_manager = Group.objects.create(name='Manager')
        self.grp_caissier = Group.objects.create(name='Caissier')
        self.grp_magasinier = Group.objects.create(name='Magasinier')

        self.admin_user = User.objects.create_superuser(username='p9_admin', password='password', email='admin@test.com')
        self.manager_user = User.objects.create_user(username='p9_manager', password='password', is_staff=True)
        self.manager_user.groups.add(self.grp_manager)

        self.caissier_user = User.objects.create_user(username='p9_caissier', password='password')
        self.caissier_user.groups.add(self.grp_caissier)

        self.magasinier_user = User.objects.create_user(username='p9_magasinier', password='password')
        self.magasinier_user.groups.add(self.grp_magasinier)

        self.standard_user = User.objects.create_user(username='p9_standard', password='password')

        self.cat = Categorie.objects.create(nom='Audit Cat')
        self.produit = Produit.objects.create(
            nom='Souris Optique Audit',
            reference='AUDIT-MSE-01',
            categorie=self.cat,
            stock_actuel=40,
            seuil_alerte=5,
            stock_maximum=100,
            prix_achat=15.0,
            prix_unitaire=35.0
        )
        self.fournisseur = Fournisseur.objects.create(
            nom='Fournisseur Audit',
            telephone='22334455',
            email='audit@fournisseur.com',
            dette_fournisseur=Decimal('25000.00')
        )

    def test_role_helpers(self):
        from stockapp.permissions import user_has_role, get_user_primary_role
        self.assertTrue(user_has_role(self.admin_user, 'Admin'))
        self.assertTrue(user_has_role(self.admin_user, 'Manager'))
        self.assertTrue(user_has_role(self.admin_user, 'Caissier'))

        self.assertTrue(user_has_role(self.manager_user, 'Manager'))
        self.assertFalse(user_has_role(self.manager_user, 'Admin'))

        self.assertTrue(user_has_role(self.caissier_user, 'Caissier'))
        self.assertFalse(user_has_role(self.caissier_user, 'Manager'))

        self.assertTrue(user_has_role(self.magasinier_user, 'Magasinier'))
        self.assertFalse(user_has_role(self.magasinier_user, 'Admin'))

        self.assertFalse(user_has_role(self.standard_user, 'Admin'))
        self.assertFalse(user_has_role(self.standard_user, 'Manager'))

        self.assertEqual(get_user_primary_role(self.admin_user), "Administrateur")
        self.assertEqual(get_user_primary_role(self.manager_user), "Manager")
        self.assertEqual(get_user_primary_role(self.caissier_user), "Caissier")
        self.assertEqual(get_user_primary_role(self.magasinier_user), "Magasinier")
        self.assertEqual(get_user_primary_role(self.standard_user), "Utilisateur")

    def test_role_required_access_control(self):
        # Admin a accès au journal d'audit
        self.client.login(username='p9_admin', password='password')
        res_admin = self.client.get(reverse('stockapp:journal-audit'))
        self.assertEqual(res_admin.status_code, 200)

        # Standard user est redirigé vers le dashboard (302)
        self.client.login(username='p9_standard', password='password')
        res_std = self.client.get(reverse('stockapp:journal-audit'))
        self.assertEqual(res_std.status_code, 302)

        # Requête AJAX par standard user retourne 403 Forbidden
        res_ajax = self.client.get(reverse('stockapp:journal-audit'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_ajax.status_code, 403)
        self.assertIn('error', res_ajax.json())

    def test_produit_creation_and_price_change_audit_logging(self):
        self.client.login(username='p9_manager', password='password')

        # 1. Création d'un produit
        add_url = reverse('stockapp:produit-ajouter')
        res_add = self.client.post(add_url, {
            'nom': 'Clavier Audit Pro',
            'reference': 'AUDIT-KB-01',
            'categorie': self.cat.id,
            'stock_actuel': 20,
            'seuil_alerte': 5,
            'stock_maximum': 50,
            'prix_achat': '25.00',
            'prix_unitaire': '60.00',
            'statut': 'ACTIF',
            'unite': 'piece'
        })
        self.assertEqual(res_add.status_code, 302)

        p_created = Produit.objects.get(reference='AUDIT-KB-01')
        log_create = JournalAudit.objects.filter(action='CREATION', module='PRODUIT').first()
        self.assertIsNotNone(log_create)
        self.assertEqual(log_create.utilisateur, self.manager_user)
        self.assertIn('Clavier Audit Pro', log_create.description)

        # 2. Modification du prix de vente (déclenche MODIFICATION_PRIX)
        mod_url = reverse('stockapp:produit-modifier', kwargs={'pk': p_created.pk})
        res_mod = self.client.post(mod_url, {
            'nom': 'Clavier Audit Pro',
            'reference': 'AUDIT-KB-01',
            'categorie': self.cat.id,
            'stock_actuel': 20,
            'seuil_alerte': 5,
            'stock_maximum': 50,
            'prix_achat': '25.00',
            'prix_unitaire': '75.00',  # Prix augmenté de 60 à 75
            'statut': 'ACTIF',
            'unite': 'piece'
        })
        self.assertEqual(res_mod.status_code, 302)

        log_prix = JournalAudit.objects.filter(action='MODIFICATION_PRIX', module='PRODUIT').first()
        self.assertIsNotNone(log_prix)
        self.assertIn('75', log_prix.description)

    def test_stock_ajustement_audit_logging(self):
        self.client.login(username='p9_magasinier', password='password')
        url = reverse('stockapp:ajuster-stock')
        res = self.client.post(url, {
            'produit': self.produit.pk,
            'nouveau_stock': 35,
            'motif': 'Inventaire tournant'
        })
        self.assertEqual(res.status_code, 302)

        log = JournalAudit.objects.filter(action='AJUSTEMENT_STOCK', module='STOCK').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.utilisateur, self.magasinier_user)
        self.assertIn('Inventaire tournant', log.description)

    def test_produit_and_vente_suppression_audit_logging(self):
        self.client.login(username='p9_admin', password='password')

        # Créer une vente à supprimer
        vente = Vente.objects.create(
            produit=self.produit,
            quantite=2,
            prix_unitaire=Decimal('35.00'),
            prix_achat=Decimal('15.00'),
            remise=Decimal('0.00'),
            mode_paiement='ESPECES'
        )

        # Supprimer la vente
        del_v_url = reverse('stockapp:vente-supprimer', kwargs={'pk': vente.pk})
        res_del_v = self.client.post(del_v_url)
        self.assertEqual(res_del_v.status_code, 302)

        log_v = JournalAudit.objects.filter(action='SUPPRESSION', module='VENTE').first()
        self.assertIsNotNone(log_v)
        self.assertEqual(log_v.utilisateur, self.admin_user)

        # Supprimer le produit
        del_p_url = reverse('stockapp:produit-supprimer', kwargs={'pk': self.produit.pk})
        res_del_p = self.client.post(del_p_url)
        self.assertEqual(res_del_p.status_code, 302)

        log_p = JournalAudit.objects.filter(action='SUPPRESSION', module='PRODUIT').first()
        self.assertIsNotNone(log_p)
        self.assertIn(self.produit.nom, log_p.description)

    def test_fournisseur_regler_dette_audit_logging(self):
        self.client.login(username='p9_manager', password='password')
        url = reverse('stockapp:fournisseur-regler-dette', kwargs={'pk': self.fournisseur.pk})
        res = self.client.post(url, {
            'montant': '10000.00',
            'moyen_reglement': 'VIREMENT',
            'notes': 'Acompte facture 2026-09'
        }, HTTP_REFERER='/dashboard/fournisseurs/')
        self.assertEqual(res.status_code, 302)

        log = JournalAudit.objects.filter(action='REGLEMENT_DETTE', module='FOURNISSEUR').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.utilisateur, self.manager_user)
        self.assertIn('10,000.00', log.description)

    def test_depense_creation_and_suppression_audit_logging(self):
        self.client.login(username='p9_manager', password='password')

        # 1. Création d'une dépense
        url_fin = reverse('stockapp:finances')
        res = self.client.post(url_fin, {
            'titre': 'Facture Électricité Audit',
            'montant': '15000.00',
            'categorie': 'ELECTRICITE',
            'date_depense': timezone.now().date().strftime('%Y-%m-%d'),
            'notes': 'Test OPEX'
        })
        self.assertEqual(res.status_code, 302)

        depense = Depense.objects.filter(titre='Facture Électricité Audit').first()
        self.assertIsNotNone(depense)

        log_dep = JournalAudit.objects.filter(action='DEPENSE', module='FINANCES').first()
        self.assertIsNotNone(log_dep)
        self.assertEqual(log_dep.utilisateur, self.manager_user)

        # 2. Suppression de la dépense
        url_del = reverse('stockapp:depense-supprimer', kwargs={'pk': depense.pk})
        res_del = self.client.post(url_del)
        self.assertEqual(res_del.status_code, 302)

        log_del = JournalAudit.objects.filter(action='SUPPRESSION', module='FINANCES').first()
        self.assertIsNotNone(log_del)
        self.assertIn('Facture Électricité Audit', log_del.description)

    def test_journal_audit_view_and_filtering(self):
        self.client.login(username='p9_admin', password='password')

        # Créer des logs d'audit
        JournalAudit.log_action(self.admin_user, 'CREATION', 'PRODUIT', 'Prod #1', 'Création test')
        JournalAudit.log_action(self.manager_user, 'MODIFICATION_PRIX', 'PRODUIT', 'Prod #2', 'Changement tarif')
        JournalAudit.log_action(self.magasinier_user, 'AJUSTEMENT_STOCK', 'STOCK', 'Prod #3', 'Ajustement')

        # Test vue complète
        url = reverse('stockapp:journal-audit')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'stockapp/journal_audit.html')
        self.assertGreaterEqual(res.context['total_logs'], 3)
        self.assertGreaterEqual(res.context['nb_prix_changes'], 1)
        self.assertGreaterEqual(res.context['nb_ajustements'], 1)

        # Test filtrage par action
        res_filt = self.client.get(f"{url}?action=MODIFICATION_PRIX")
        self.assertEqual(res_filt.status_code, 200)
        logs = res_filt.context['logs']
        for l in logs:
            self.assertEqual(l.action, 'MODIFICATION_PRIX')

    def test_journal_audit_export_csv(self):
        self.client.login(username='p9_manager', password='password')
        JournalAudit.log_action(self.manager_user, 'CREATION', 'PRODUIT', 'Prod CSV', 'Test Export')

        url = reverse('stockapp:journal-audit-export-csv')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8')
        content = res.content.decode('utf-8')
        self.assertIn('ID;Date & Heure;Utilisateur;Action;Module;Objet Concerné;Description;Adresse IP', content)
        self.assertIn('Prod CSV', content)


class Phase10PwaAndMobileTests(TestCase):
    """
    Suite de tests de validation pour la Phase 10 :
    Optimisation PWA, Mode Hors-Ligne & Expérience Mobile Point de Vente.
    Couvre :
    - Endpoint /manifest.json : validité JSON, shortcuts d'accès rapide, icônes et métadonnées
    - Endpoint /service-worker.js : Content-Type, headers de scope, cache smart-tech-v10 et fallback offline
    - Vue /offline/ : affichage 200 OK, template offline.html et boutons d'action
    - Composants mobiles dans base.html : Bottom Navigation Bar, Offline Toast et PWA Install Banner
    """
    def setUp(self):
        self.user = User.objects.create_user(username='p10_user', password='password', is_staff=True)

    def test_pwa_manifest_endpoint_and_structure(self):
        url = reverse('stockapp:manifest')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')

        import json
        manifest_data = json.loads(response.content.decode('utf-8'))
        self.assertIn('SMART-TECH', manifest_data['name'])
        self.assertEqual(manifest_data['short_name'], 'SMART-TECH')
        self.assertEqual(manifest_data['start_url'], '/dashboard/')
        self.assertEqual(manifest_data['display'], 'standalone')
        self.assertIn('shortcuts', manifest_data)
        self.assertGreaterEqual(len(manifest_data['shortcuts']), 3)

        shortcut_urls = [s['url'] for s in manifest_data['shortcuts']]
        self.assertIn('/dashboard/caisse/', shortcut_urls)
        self.assertIn('/dashboard/', shortcut_urls)

    def test_service_worker_endpoint_and_headers(self):
        url = reverse('stockapp:service-worker')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        self.assertEqual(response.get('Service-Worker-Allowed'), '/')

        content = response.content.decode('utf-8')
        self.assertIn('smart-tech-v10', content)
        self.assertIn('/offline/', content)
        self.assertIn('PRECACHE_ASSETS', content)

    def test_offline_view_renders_correctly(self):
        url = reverse('stockapp:offline')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'stockapp/offline.html')
        content = response.content.decode('utf-8')
        self.assertIn('Mode Hors-Ligne Actif', content)
        self.assertIn('checkConnectionAndReload', content)

    def test_base_html_includes_mobile_and_pwa_components(self):
        self.client.login(username='p10_user', password='password')
        response = self.client.get(reverse('stockapp:dashboard'))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        # Meta manifest
        self.assertIn('<link rel="manifest" href="/manifest.json">', content)
        # Toast hors-ligne
        self.assertIn('id="pwa-offline-toast"', content)
        # Barre de navigation mobile inférieure
        self.assertIn('id="mobile-bottom-nav"', content)
        # Bannière d'installation PWA
        self.assertIn('id="pwa-install-banner"', content)
        self.assertIn('Installer l\'application SMART-TECH', content)
















class Phase11ClotureCaisseAndAdvancedReportsTests(TestCase):
    """
    Suite de tests de validation pour la Phase 11 :
    Clôture de Caisse Journalière (Rapport Z) & Rapports d'Exportation Avancés.
    Couvre :
    - Calcul des encaissements théoriques multi-moyens (get_caisse_session_summary)
    - Création atomique de ClotureCaisse & calcul des écarts (Conforme, Déficit, Excédent)
    - Rattachement des ventes non clôturées à la session Z
    - Génération du document officiel PDF A4 Rapport Z (ReportLab)
    - Hub central des rapports & exports (/rapports/)
    - Exports CSV sécurisés (Inventaire valorisé, Ventes & Marges réelles, Compte de résultat P&L)
    - Journalisation de l'audit trail pour la clôture de caisse
    """
    def setUp(self):
        from stockapp.models import Produit, Client, Vente, ClotureCaisse, JournalAudit, Depense
        self.admin_user = User.objects.create_superuser(username='p11_admin', password='password')
        self.manager_user = User.objects.create_user(username='p11_manager', password='password', is_staff=True)
        self.cashier_user = User.objects.create_user(username='p11_cashier', password='password')

        from django.contrib.auth.models import Group
        cashier_group, _ = Group.objects.get_or_create(name='Caissier')
        self.cashier_user.groups.add(cashier_group)

        self.client_entity = Client.objects.create(
            nom="Client Société Test",
            telephone="+229 97 00 00 00",
            solde_credit=Decimal('5000.00')
        )

        self.prod_souris = Produit.objects.create(
            nom="Souris Sans Fil Pro",
            reference="MS-P11-001",
            stock_actuel=50,
            seuil_alerte=10,
            stock_maximum=100,
            prix_unitaire=Decimal('10000.00'),
            prix_achat=Decimal('6000.00')
        )
        self.prod_clavier = Produit.objects.create(
            nom="Clavier Mécanique RGB",
            reference="KB-P11-002",
            stock_actuel=30,
            seuil_alerte=5,
            stock_maximum=60,
            prix_unitaire=Decimal('25000.00'),
            prix_achat=Decimal('15000.00')
        )

        # Créer quelques ventes
        self.vente1 = Vente.objects.create(
            produit=self.prod_souris,
            quantite=2,
            prix_unitaire=Decimal('10000.00'),
            prix_achat=Decimal('6000.00'),
            remise=Decimal('1000.00'),
            mode_paiement='ESPECES',
            reference_ticket='TCK-P11-001'
        )
        self.vente2 = Vente.objects.create(
            produit=self.prod_clavier,
            quantite=1,
            prix_unitaire=Decimal('25000.00'),
            prix_achat=Decimal('15000.00'),
            remise=Decimal('0.00'),
            mode_paiement='CARTE',
            reference_ticket='TCK-P11-002'
        )
        self.vente3 = Vente.objects.create(
            produit=self.prod_souris,
            quantite=1,
            prix_unitaire=Decimal('10000.00'),
            prix_achat=Decimal('6000.00'),
            remise=Decimal('0.00'),
            mode_paiement='MOBILE_MONEY',
            reference_ticket='TCK-P11-003'
        )

    def test_caisse_session_summary_selector(self):
        from stockapp.selectors import get_caisse_session_summary
        summary = get_caisse_session_summary()
        self.assertEqual(summary['nb_ventes'], 3)
        self.assertEqual(summary['nb_tickets'], 3)
        self.assertEqual(summary['nb_articles'], 4)
        # Vente 1 : 20000 - 1000 = 19000
        self.assertEqual(summary['total_especes'], Decimal('19000.00'))
        # Vente 2 : 25000
        self.assertEqual(summary['total_carte'], Decimal('25000.00'))
        # Vente 3 : 10000
        self.assertEqual(summary['total_mobile_money'], Decimal('10000.00'))
        # Total net : 19000 + 25000 + 10000 = 54000
        self.assertEqual(summary['total_net'], Decimal('54000.00'))

    def test_cloture_caisse_conforme_creation_and_reconciliation(self):
        from stockapp.models import ClotureCaisse, JournalAudit
        self.client.login(username='p11_cashier', password='password')

        # Ventes espèces théoriques = 19000, fond initial = 5000 -> Tiroir attendu = 24000
        res = self.client.post(reverse('stockapp:cloture-caisse'), data={
            'fond_de_caisse_initial': '5000.00',
            'montant_especes_reel': '24000.00',
            'montant_carte_reel': '25000.00',
            'montant_mobile_money_reel': '10000.00',
            'montant_cheque_reel': '0.00',
            'commentaire': 'Session matinale parfaitement équilibrée'
        })
        self.assertEqual(res.status_code, 302)

        cloture = ClotureCaisse.objects.latest('id')
        self.assertEqual(cloture.caissier, self.cashier_user)
        self.assertEqual(cloture.fond_de_caisse_initial, Decimal('5000.00'))
        self.assertEqual(cloture.total_especes_theorique, Decimal('19000.00'))
        self.assertEqual(cloture.total_tiroir_theorique, Decimal('24000.00'))
        self.assertEqual(cloture.montant_especes_reel, Decimal('24000.00'))
        self.assertEqual(cloture.ecart_especes, Decimal('0.00'))
        self.assertEqual(cloture.ecart_total, Decimal('0.00'))
        self.assertEqual(cloture.statut_conformite, 'CONFORME')

        # Vérifier le rattachement des ventes
        self.vente1.refresh_from_db()
        self.vente2.refresh_from_db()
        self.vente3.refresh_from_db()
        self.assertEqual(self.vente1.cloture, cloture)
        self.assertEqual(self.vente2.cloture, cloture)
        self.assertEqual(self.vente3.cloture, cloture)

        # Vérifier la journalisation d'audit
        audit_log = JournalAudit.objects.filter(action='CLOTURE_CAISSE', module='CAISSE').first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.utilisateur, self.cashier_user)
        self.assertIn(cloture.reference, audit_log.description)

    def test_cloture_caisse_deficit_and_excedent_detection(self):
        from stockapp.models import ClotureCaisse, Vente
        self.client.login(username='p11_manager', password='password')

        # Clôturer d'abord les ventes de setUp pour isoler la nouvelle session
        prev_cloture = ClotureCaisse.objects.create(
            reference="Z-PREV-001",
            caissier=self.manager_user,
            total_especes_theorique=Decimal('19000.00'),
            total_carte_theorique=Decimal('25000.00'),
            total_mobile_money_theorique=Decimal('10000.00'),
            total_ventes_net=Decimal('54000.00'),
        )
        Vente.objects.filter(cloture__isnull=True).update(cloture=prev_cloture)

        # Créer une vente pour la nouvelle session : 10000 espèces
        v = Vente.objects.create(
            produit=self.prod_souris,
            quantite=1,
            prix_unitaire=Decimal('10000.00'),
            prix_achat=Decimal('6000.00'),
            mode_paiement='ESPECES',
            reference_ticket='TCK-DEF-001'
        )

        # Test Déficit : attendu 10000 espèces, déclaré 8000
        res_def = self.client.post(reverse('stockapp:cloture-caisse'), data={
            'fond_de_caisse_initial': '0.00',
            'montant_especes_reel': '8000.00',
            'montant_carte_reel': '0.00',
            'montant_mobile_money_reel': '0.00',
            'montant_cheque_reel': '0.00',
            'commentaire': 'Manquant de 2000 en tiroir'
        })
        self.assertEqual(res_def.status_code, 302)
        cloture_def = ClotureCaisse.objects.latest('id')
        self.assertEqual(cloture_def.statut_conformite, 'DEFICIT')
        self.assertEqual(cloture_def.ecart_especes, Decimal('-2000.00'))
        self.assertEqual(cloture_def.ecart_total, Decimal('-2000.00'))

    def test_clotures_views_and_detail(self):
        from stockapp.models import ClotureCaisse
        self.client.login(username='p11_cashier', password='password')

        # 1. Page de formulaire de clôture GET
        res_form = self.client.get(reverse('stockapp:cloture-caisse'))
        self.assertEqual(res_form.status_code, 200)
        self.assertTemplateUsed(res_form, 'stockapp/cloture_caisse.html')

        # 2. Clôturer pour avoir un objet
        self.client.post(reverse('stockapp:cloture-caisse'), data={
            'fond_de_caisse_initial': '0.00',
            'montant_especes_reel': '19000.00',
            'montant_carte_reel': '25000.00',
            'montant_mobile_money_reel': '10000.00',
            'montant_cheque_reel': '0.00',
        })
        cloture = ClotureCaisse.objects.latest('id')

        # 3. Liste des clôtures
        res_list = self.client.get(reverse('stockapp:clotures-caisse-list'))
        self.assertEqual(res_list.status_code, 200)
        self.assertTemplateUsed(res_list, 'stockapp/clotures_list.html')
        self.assertIn(cloture.reference, res_list.content.decode('utf-8'))

        # 4. Détail d'une clôture
        res_detail = self.client.get(reverse('stockapp:cloture-caisse-detail', kwargs={'pk': cloture.pk}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertTemplateUsed(res_detail, 'stockapp/cloture_detail.html')

    def test_cloture_caisse_pdf_rapport_z(self):
        from stockapp.models import ClotureCaisse
        self.client.login(username='p11_manager', password='password')

        self.client.post(reverse('stockapp:cloture-caisse'), data={
            'fond_de_caisse_initial': '5000.00',
            'montant_especes_reel': '24000.00',
            'montant_carte_reel': '25000.00',
            'montant_mobile_money_reel': '10000.00',
            'montant_cheque_reel': '0.00',
        })
        cloture = ClotureCaisse.objects.latest('id')

        res_pdf = self.client.get(reverse('stockapp:cloture-caisse-pdf', kwargs={'pk': cloture.pk}))
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
        self.assertIn('rapport_z_', res_pdf['Content-Disposition'])

    def test_rapports_hub_and_csv_exports(self):
        from stockapp.models import Depense
        self.client.login(username='p11_manager', password='password')

        # Créer une dépense pour alimenter le P&L
        Depense.objects.create(
            titre="Frais télécoms & internet",
            categorie="INTERNET",
            montant=Decimal('15000.00')
        )

        # 1. Hub des rapports
        res_hub = self.client.get(reverse('stockapp:rapports-hub'))
        self.assertEqual(res_hub.status_code, 200)
        self.assertTemplateUsed(res_hub, 'stockapp/rapports_hub.html')
        content_hub = res_hub.content.decode('utf-8')
        self.assertIn('Inventaire Complet Valorisé', content_hub)
        self.assertIn('Journal des Ventes & Marges', content_hub)

        # 2. Export Stock Valorisé CSV
        res_stock_csv = self.client.get(reverse('stockapp:export-stock-valorise-csv'))
        self.assertEqual(res_stock_csv.status_code, 200)
        self.assertEqual(res_stock_csv['Content-Type'], 'text/csv; charset=utf-8')
        csv_stock = res_stock_csv.content.decode('utf-8')
        self.assertIn('Référence;SKU;Nom du Produit', csv_stock)
        self.assertIn('Souris Sans Fil Pro', csv_stock)

        # 3. Export Ventes Détaillées CSV
        res_ventes_csv = self.client.get(reverse('stockapp:export-ventes-detaillees-csv'))
        self.assertEqual(res_ventes_csv.status_code, 200)
        self.assertEqual(res_ventes_csv['Content-Type'], 'text/csv; charset=utf-8')
        csv_ventes = res_ventes_csv.content.decode('utf-8')
        self.assertIn('Date & Heure;Référence Ticket;Client;Produit', csv_ventes)
        self.assertIn('TCK-P11-001', csv_ventes)

        # 4. Export Compte de Résultat CSV
        res_pnl_csv = self.client.get(reverse('stockapp:export-compte-resultat-csv'))
        self.assertEqual(res_pnl_csv.status_code, 200)
        self.assertEqual(res_pnl_csv['Content-Type'], 'text/csv; charset=utf-8')
        csv_pnl = res_pnl_csv.content.decode('utf-8')
        self.assertIn("Chiffre d'Affaires Brut", csv_pnl)
        self.assertIn("Marge Commerciale Brute", csv_pnl)
        self.assertIn("Résultat Net d'Exploitation", csv_pnl)


class Phase12NotificationsAndAlertsTests(TestCase):
    """
    Tests de validation fonctionnelle et d'intégration de la Phase 12 :
    - Surveillance proactive et génération automatique des alertes (Stock, Fournisseurs, Clients, Caisses)
    - Déduplication intelligente et gestion du cycle de vie (Lecture, Archivage)
    - Hub central des alertes et filtrage
    - Injection du context processor des notifications
    - API JSON d'actualisation temps réel
    """
    def setUp(self):
        from django.contrib.auth.models import User, Group
        from stockapp.models import Categorie, Produit, Client, Fournisseur, ClotureCaisse, Notification

        # Groupes et utilisateurs
        self.admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user = User.objects.create_user(
            username='p12_admin',
            email='p12@smarttech.local',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        self.user.groups.add(self.admin_group)

        self.cat = Categorie.objects.create(nom="Périphériques & Réseaux")

        # Produit en rupture
        self.p_rupture = Produit.objects.create(
            nom="Disque SSD 1To",
            reference="SSD-1TB-PRO",
            categorie=self.cat,
            stock_actuel=0,
            seuil_alerte=5,
            prix_achat=Decimal('35000.00'),
            prix_unitaire=Decimal('50000.00'),
            statut='ACTIF'
        )

        # Produit stock faible
        self.p_faible = Produit.objects.create(
            nom="Clé USB 64Go",
            reference="USB-64G",
            categorie=self.cat,
            stock_actuel=3,
            seuil_alerte=10,
            prix_achat=Decimal('3000.00'),
            prix_unitaire=Decimal('6000.00'),
            statut='ACTIF'
        )

        # Fournisseur avec dette
        self.fournisseur = Fournisseur.objects.create(
            nom="Grossiste Informatique Pro",
            telephone="+229 97 00 11 22",
            dette_fournisseur=Decimal('150000.00')
        )

        # Client avec solde débiteur
        self.client_debiteur = Client.objects.create(
            nom="Entreprise Beta SARL",
            telephone="+229 96 11 22 33",
            solde_credit=Decimal('75000.00')
        )

    def test_proactive_alerts_generation_and_deduplication(self):
        from stockapp.services.notification_service import generer_alertes_proactives
        from stockapp.models import Notification

        # Premier scan
        res = generer_alertes_proactives()
        self.assertGreaterEqual(res['creations_count'], 4)

        # Vérifier alerte rupture
        notif_rupture = Notification.objects.filter(type_notification='STOCK_RUPTURE', est_archivee=False).first()
        self.assertIsNotNone(notif_rupture)
        self.assertEqual(notif_rupture.niveau, 'CRITICAL')
        self.assertIn("Disque SSD 1To", notif_rupture.titre)

        # Vérifier alerte stock faible
        notif_faible = Notification.objects.filter(type_notification='STOCK_FAIBLE', est_archivee=False).first()
        self.assertIsNotNone(notif_faible)
        self.assertEqual(notif_faible.niveau, 'WARNING')
        self.assertIn("Clé USB 64Go", notif_faible.titre)

        # Vérifier dette fournisseur
        notif_dette = Notification.objects.filter(type_notification='DETTE_FOURNISSEUR', est_archivee=False).first()
        self.assertIsNotNone(notif_dette)
        self.assertEqual(notif_dette.niveau, 'CRITICAL')
        self.assertIn("Grossiste Informatique Pro", notif_dette.titre)

        # Vérifier créance client
        notif_creance = Notification.objects.filter(type_notification='CREANCE_CLIENT', est_archivee=False).first()
        self.assertIsNotNone(notif_creance)
        self.assertIn("Entreprise Beta SARL", notif_creance.titre)

        # Second scan immédiat : aucune duplication ne doit avoir lieu
        res2 = generer_alertes_proactives()
        self.assertEqual(res2['creations_count'], 0)

    def test_auto_archiving_when_stock_restored(self):
        from stockapp.services.notification_service import generer_alertes_proactives
        from stockapp.models import Notification

        generer_alertes_proactives()
        self.assertTrue(Notification.objects.filter(cle_unicite=f"stock_rupture_{self.p_rupture.id}", est_archivee=False).exists())

        # Réapprovisionnement du produit au-delà du seuil d'alerte
        self.p_rupture.stock_actuel = 25
        self.p_rupture.save()

        generer_alertes_proactives()
        notif = Notification.objects.get(cle_unicite=f"stock_rupture_{self.p_rupture.id}")
        self.assertTrue(notif.est_archivee)
        self.assertTrue(notif.est_lue)

    def test_caisse_anomaly_proactive_alert(self):
        from stockapp.models import ClotureCaisse, Notification
        from stockapp.services.notification_service import generer_alertes_proactives

        # Créer une clôture déficitaire
        cloture = ClotureCaisse.objects.create(
            reference="Z-20260916-TEST-ANOMALIE",
            caissier=self.user,
            fond_de_caisse_initial=Decimal('10000.00'),
            total_especes_theorique=Decimal('50000.00'),
            montant_especes_reel=Decimal('45000.00'),
            total_ventes_brut=Decimal('50000.00'),
            total_ventes_net=Decimal('50000.00'),
            ecart_especes=Decimal('-5000.00'),
            ecart_total=Decimal('-5000.00'),
            statut_conformite='DEFICIT'
        )

        generer_alertes_proactives()
        notif_caisse = Notification.objects.filter(type_notification='ANOMALIE_CAISSE', cle_unicite=f"anomalie_caisse_{cloture.id}").first()
        self.assertIsNotNone(notif_caisse)
        self.assertEqual(notif_caisse.niveau, 'CRITICAL')
        self.assertIn("Z-20260916-TEST-ANOMALIE", notif_caisse.titre)

    def test_mark_as_read_and_mark_all_read(self):
        from stockapp.models import Notification
        from stockapp.services.notification_service import generer_alertes_proactives
        self.client.login(username='p12_admin', password='password')

        generer_alertes_proactives()
        notif = Notification.objects.filter(est_lue=False).first()
        self.assertIsNotNone(notif)

        # 1. Marquer une notification comme lue via AJAX
        res_ajax = self.client.post(
            reverse('stockapp:notification-lire', kwargs={'pk': notif.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_ajax.status_code, 200)
        data = res_ajax.json()
        self.assertTrue(data['success'])

        notif.refresh_from_db()
        self.assertTrue(notif.est_lue)
        self.assertIsNotNone(notif.date_lecture)

        # 2. Marquer tout comme lu
        res_all = self.client.post(
            reverse('stockapp:notification-tout-lire'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_all.status_code, 200)
        data_all = res_all.json()
        self.assertTrue(data_all['success'])
        self.assertEqual(Notification.objects.filter(est_lue=False).count(), 0)

    def test_archive_notification(self):
        from stockapp.models import Notification
        from stockapp.services.notification_service import generer_alertes_proactives
        self.client.login(username='p12_admin', password='password')

        generer_alertes_proactives()
        notif = Notification.objects.filter(est_archivee=False).first()

        res = self.client.post(
            reverse('stockapp:notification-archiver', kwargs={'pk': notif.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

        notif.refresh_from_db()
        self.assertTrue(notif.est_archivee)

    def test_notifications_hub_view_and_context_processors(self):
        self.client.login(username='p12_admin', password='password')

        # Requête vers le hub des notifications
        res = self.client.get(reverse('stockapp:notifications-hub'))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'stockapp/notifications_hub.html')

        # Vérifier context processor
        self.assertIn('unread_notifications_count', res.context)
        self.assertIn('recent_notifications', res.context)
        self.assertIn('metrics', res.context)

        # Tester filtrage par type
        res_filtered = self.client.get(reverse('stockapp:notifications-hub') + '?type=STOCK_RUPTURE')
        self.assertEqual(res_filtered.status_code, 200)

    def test_api_unread_notifications_endpoint(self):
        self.client.login(username='p12_admin', password='password')
        res = self.client.get(reverse('stockapp:notifications-api-unread'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('unread_count', data)
        self.assertIn('critical_count', data)
        self.assertIn('recent', data)
        self.assertIsInstance(data['recent'], list)


class Phase13BackupAndDataSecurityTests(TransactionTestCase):
    """
    Tests de validation fonctionnelle et d'intégration de la Phase 13 :
    - Sauvegarde cohérente à chaud (SQLite backup API, dump JSON, médias, métadonnées, SHA-256)
    - Liste, intégrité physique et logique (PRAGMA integrity_check, foreign_key_check)
    - Restauration sécurisée avec snapshot pré-restauration automatique
    - Purge des logs d'audit anciens et rotation de quota
    - Vues d'administration, téléchargement et contrôle d'accès
    - Commandes CLI de gestion
    """
    def setUp(self):
        import shutil
        from pathlib import Path
        from django.contrib.auth.models import User, Group
        from stockapp.models import Categorie, Produit, Vente, JournalAudit
        from stockapp.services.backup_service import get_backup_dir

        self.backup_dir = get_backup_dir()

        # Groupes et utilisateurs
        self.admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.caissier_group, _ = Group.objects.get_or_create(name='Caissier')

        self.admin_user = User.objects.create_user(
            username='p13_admin',
            email='p13_admin@smarttech.local',
            password='password',
            is_staff=True,
            is_superuser=True
        )
        self.admin_user.groups.add(self.admin_group)

        self.caissier_user = User.objects.create_user(
            username='p13_caissier',
            email='p13_caissier@smarttech.local',
            password='password'
        )
        self.caissier_user.groups.add(self.caissier_group)

        # Données de test
        self.cat = Categorie.objects.create(nom="Sécurité & Backup")
        self.produit = Produit.objects.create(
            nom="Serveur NAS Backup 4TB",
            reference="NAS-4TB-PRO",
            categorie=self.cat,
            stock_actuel=5,
            seuil_alerte=2,
            prix_achat=Decimal('120000.00'),
            prix_unitaire=Decimal('180000.00'),
            statut='ACTIF'
        )

    def test_creer_sauvegarde_and_metadata_validation(self):
        import zipfile
        import json
        from pathlib import Path
        from stockapp.services.backup_service import creer_sauvegarde
        from stockapp.models import JournalAudit

        res = creer_sauvegarde(
            nom_personnalise="test_unitaire",
            inclure_medias=False,
            utilisateur=self.admin_user
        )

        self.assertTrue(res['succes'])
        self.assertIn("test_unitaire", res['nom_fichier'])
        self.assertTrue(Path(res['chemin_absolu']).exists())
        self.assertGreater(res['taille_octets'], 1000)
        self.assertIsNotNone(res['sha256'])

        # Vérifier le contenu du ZIP
        with zipfile.ZipFile(res['chemin_absolu'], 'r') as zipf:
            namelist = zipf.namelist()
            self.assertIn('database.sqlite3', namelist)
            self.assertIn('dump_data.json', namelist)
            self.assertIn('metadata.json', namelist)

            meta = json.loads(zipf.read('metadata.json').decode('utf-8'))
            self.assertEqual(meta['cree_par'], 'p13_admin')
            self.assertIn('sha256_database', meta)
            self.assertGreaterEqual(meta['stats']['produits'], 1)

        # Vérifier JournalAudit
        self.assertTrue(JournalAudit.objects.filter(module='SECURITE', action='CREATION').exists())

    def test_lister_sauvegardes_and_integrity_check(self):
        from stockapp.services.backup_service import creer_sauvegarde, lister_sauvegardes, verifier_integrite_base

        creer_sauvegarde(nom_personnalise="test_liste", utilisateur=self.admin_user)

        sauvegardes = lister_sauvegardes()
        self.assertGreaterEqual(len(sauvegardes), 1)

        premiere = sauvegardes[0]
        self.assertTrue(premiere['est_valide'])
        self.assertIn('.zip', premiere['nom_fichier'])

        # Vérification d'intégrité
        integrite = verifier_integrite_base()
        self.assertTrue(integrite['est_integre'])
        self.assertIn("Intégrité physique SQLite : OK", integrite['messages'][0])
        self.assertGreaterEqual(integrite['stats']['produits'], 1)

    def test_supprimer_sauvegarde_and_security(self):
        from pathlib import Path
        from stockapp.services.backup_service import creer_sauvegarde, supprimer_sauvegarde

        res = creer_sauvegarde(nom_personnalise="a_supprimer", utilisateur=self.admin_user)
        filename = res['nom_fichier']
        self.assertTrue(Path(res['chemin_absolu']).exists())

        # Test protection traversal
        with self.assertRaises(ValueError):
            supprimer_sauvegarde("../fake_file.zip")

        # Suppression légitime
        success = supprimer_sauvegarde(filename, utilisateur=self.admin_user)
        self.assertTrue(success)
        self.assertFalse(Path(res['chemin_absolu']).exists())

    def test_nettoyer_anciennes_sauvegardes_retention(self):
        from stockapp.services.backup_service import creer_sauvegarde, nettoyer_anciennes_sauvegardes

        # Créer plusieurs sauvegardes
        for i in range(5):
            creer_sauvegarde(nom_personnalise=f"quota_{i}")

        # Nettoyage avec max_sauvegardes=3
        suppr = nettoyer_anciennes_sauvegardes(jours_retention=30, max_sauvegardes=3)
        self.assertGreaterEqual(suppr, 1)

    def test_purger_anciens_logs_audit(self):
        from stockapp.models import JournalAudit
        from stockapp.services.backup_service import purger_anciens_logs_audit
        from django.utils import timezone
        from datetime import timedelta

        # Créer log ancien
        old_log = JournalAudit.objects.create(
            utilisateur=self.admin_user,
            action='CREATION',
            module='PRODUIT',
            objet_concerne='Test Ancien',
            description='Test log ancien'
        )
        JournalAudit.objects.filter(pk=old_log.pk).update(date_creation=timezone.now() - timedelta(days=120))

        # Créer log récent
        JournalAudit.objects.create(
            utilisateur=self.admin_user,
            action='CREATION',
            module='PRODUIT',
            objet_concerne='Test Recent',
            description='Test log recent'
        )

        nb_purges = purger_anciens_logs_audit(jours_retention=90, utilisateur=self.admin_user)
        self.assertGreaterEqual(nb_purges, 1)
        self.assertFalse(JournalAudit.objects.filter(pk=old_log.pk).exists())

    def test_sauvegardes_views_permissions_and_download(self):
        from stockapp.services.backup_service import creer_sauvegarde

        # 1. Accès refusé pour un utilisateur non Admin (Redirection web 302 et JSON 403)
        self.client.login(username='p13_caissier', password='password')
        res_caissier = self.client.get(reverse('stockapp:sauvegardes'))
        self.assertEqual(res_caissier.status_code, 302)
        res_caissier_ajax = self.client.get(reverse('stockapp:sauvegardes'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_caissier_ajax.status_code, 403)

        # 2. Accès accordé pour l'Admin
        self.client.login(username='p13_admin', password='password')
        res_admin = self.client.get(reverse('stockapp:sauvegardes'))
        self.assertEqual(res_admin.status_code, 200)
        self.assertTemplateUsed(res_admin, 'stockapp/sauvegardes.html')
        self.assertIn('integrite', res_admin.context)
        self.assertIn('sauvegardes', res_admin.context)

        # 3. Création de sauvegarde via POST
        res_creer = self.client.post(reverse('stockapp:sauvegarde-creer'), {'nom_personnalise': 'test_view'})
        self.assertEqual(res_creer.status_code, 302)

        # 4. Téléchargement sécurisé
        sauv = creer_sauvegarde(nom_personnalise="dl_test", utilisateur=self.admin_user)
        res_dl = self.client.get(reverse('stockapp:sauvegarde-telecharger', kwargs={'filename': sauv['nom_fichier']}))
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl['Content-Type'], 'application/zip')
        self.assertIn('attachment;', res_dl['Content-Disposition'])

    def test_management_commands_cli_execution(self):
        from django.core.management import call_command

        # Test backup_system
        call_command('backup_system', name='cli_test', no_media=True, max=5)

        # Test check_system_integrity
        call_command('check_system_integrity')


class Phase14PackagingAndDeploymentTests(TestCase):
    """
    Suite de tests de validation pour la Phase 14 :
    Packaging Final, Scripts de Lancement, Conteneurisation & Documentation.
    Couvre :
    - Présence et cohérence des scripts de lancement (Windows .bat, PowerShell .ps1, Unix .sh)
    - Présence et structure des fichiers Docker (Dockerfile, docker-compose.yml, entrypoint.sh, .dockerignore)
    - Présence et contenu du modèle d'environnement (.env.example)
    - Complétude de la documentation (README.md, MANUEL_UTILISATEUR.md, GUIDE_DEPLOIEMENT.md)
    - Vérification globale de santé système Django (manage.py check)
    """
    def setUp(self):
        from pathlib import Path
        from django.conf import settings
        self.base_dir = Path(settings.BASE_DIR)

    def test_launch_scripts_exist_and_valid(self):
        bat_file = self.base_dir / "run_smart_tech.bat"
        ps1_file = self.base_dir / "run_smart_tech.ps1"
        sh_file = self.base_dir / "run_smart_tech.sh"

        self.assertTrue(bat_file.exists(), "run_smart_tech.bat manquant")
        self.assertTrue(ps1_file.exists(), "run_smart_tech.ps1 manquant")
        self.assertTrue(sh_file.exists(), "run_smart_tech.sh manquant")

        # Vérifier le contenu du script batch
        bat_content = bat_file.read_text(encoding='utf-8')
        self.assertIn("manage.py migrate", bat_content)
        self.assertIn("manage.py init_roles", bat_content)
        self.assertIn("manage.py runserver", bat_content)
        self.assertIn("http://127.0.0.1:8000/", bat_content)

        # Vérifier le script PowerShell
        ps1_content = ps1_file.read_text(encoding='utf-8')
        self.assertIn("manage.py migrate", ps1_content)
        self.assertIn("manage.py init_roles", ps1_content)
        self.assertIn("manage.py runserver", ps1_content)

        # Vérifier le script shell
        sh_content = sh_file.read_text(encoding='utf-8')
        self.assertTrue(sh_content.startswith("#!/usr/bin/env bash") or sh_content.startswith("#!/bin/bash"))
        self.assertIn("manage.py migrate", sh_content)
        self.assertIn("manage.py runserver", sh_content)

    def test_docker_packaging_and_configuration(self):
        dockerfile = self.base_dir / "Dockerfile"
        compose_file = self.base_dir / "docker-compose.yml"
        entrypoint_file = self.base_dir / "entrypoint.sh"
        dockerignore_file = self.base_dir / ".dockerignore"

        self.assertTrue(dockerfile.exists(), "Dockerfile manquant")
        self.assertTrue(compose_file.exists(), "docker-compose.yml manquant")
        self.assertTrue(entrypoint_file.exists(), "entrypoint.sh manquant")
        self.assertTrue(dockerignore_file.exists(), ".dockerignore manquant")

        # Dockerfile checks
        df_content = dockerfile.read_text(encoding='utf-8')
        self.assertIn("FROM python:", df_content)
        self.assertIn("WORKDIR /app", df_content)
        self.assertIn("EXPOSE 8000", df_content)
        self.assertIn("gunicorn", df_content)

        # Compose checks
        dc_content = compose_file.read_text(encoding='utf-8')
        self.assertIn("smart-tech:", dc_content)
        self.assertIn("8000:8000", dc_content)
        self.assertIn("smarttech_backups", dc_content)

        # Entrypoint checks
        ep_content = entrypoint_file.read_text(encoding='utf-8')
        self.assertIn("manage.py migrate", ep_content)
        self.assertIn("manage.py init_roles", ep_content)

        # Dockerignore checks
        di_content = dockerignore_file.read_text(encoding='utf-8')
        self.assertIn(".venv", di_content)
        self.assertIn(".git", di_content)

    def test_env_example_and_configuration(self):
        env_example = self.base_dir / ".env.example"
        self.assertTrue(env_example.exists(), ".env.example manquant")

        content = env_example.read_text(encoding='utf-8')
        self.assertIn("SECRET_KEY=", content)
        self.assertIn("DEBUG=", content)
        self.assertIn("ALLOWED_HOSTS=", content)
        self.assertIn("CSRF_TRUSTED_ORIGINS=", content)
        self.assertIn("BACKUP_RETENTION_DAYS=", content)

    def test_documentation_files_completeness(self):
        readme = self.base_dir / "README.md"
        manuel = self.base_dir / "MANUEL_UTILISATEUR.md"
        deploiement = self.base_dir / "GUIDE_DEPLOIEMENT.md"

        self.assertTrue(readme.exists(), "README.md manquant")
        self.assertTrue(manuel.exists(), "MANUEL_UTILISATEUR.md manquant")
        self.assertTrue(deploiement.exists(), "GUIDE_DEPLOIEMENT.md manquant")

        # README checks
        rm_content = readme.read_text(encoding='utf-8')
        self.assertIn("SMART-TECH", rm_content)
        self.assertIn("run_smart_tech.bat", rm_content)
        self.assertIn("docker compose", rm_content)
        self.assertTrue("Point de Vente" in rm_content or "Caisse" in rm_content)

        # Manuel Utilisateur checks (profils)
        mu_content = manuel.read_text(encoding='utf-8')
        self.assertIn("Caissier", mu_content)
        self.assertIn("Magasinier", mu_content)
        self.assertIn("Manager", mu_content)
        self.assertIn("Administrateur", mu_content)
        self.assertIn("Rapport Z", mu_content)
        self.assertTrue("PWA" in mu_content or "Hors-Ligne" in mu_content)

        # Guide Déploiement checks
        gd_content = deploiement.read_text(encoding='utf-8')
        self.assertIn("Docker Compose", gd_content)
        self.assertTrue("Systemd" in gd_content or "Linux" in gd_content)
        self.assertIn("Windows", gd_content)
        self.assertTrue("Disaster Recovery" in gd_content or "Sinistre" in gd_content)

    def test_django_system_check_passes(self):
        from django.core.management import call_command
        import io
        out = io.StringIO()
        call_command('check', stdout=out)
        self.assertIn("System check identified no issues", out.getvalue())

