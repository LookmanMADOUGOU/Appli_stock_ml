import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .api.serializers import AlerteRuptureSerializer, ProduitSerializer
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente
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
        self.assertIn('Stock IA', response.content.decode('utf-8'))
