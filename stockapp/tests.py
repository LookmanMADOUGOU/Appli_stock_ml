from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from .api.serializers import AlerteRuptureSerializer, ProduitSerializer
from .models import AlerteRupture, Approvisionnement, Categorie, Produit, Vente
from .services.alert_service import creer_alerte_si_necessaire
from .services.prediction_service import predict_sales, predict_stockout
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
        self.categorie = Categorie.objects.create(nom='Maison')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Lampe',
            reference='LAM-001',
            stock_actuel=2,
            seuil_alerte=2,
        )

    def test_serializer_includes_prediction_fields(self):
        serializer = ProduitSerializer(self.produit)
        self.assertIn('prediction_ml', serializer.data)
        self.assertIn('prediction_rupture', serializer.data)
        self.assertEqual(serializer.data['prediction_ml'], 'Pas assez de données')


class AlerteRuptureSerializerTests(TestCase):
    def test_serializer_exposes_alert_fields(self):
        categorie = Categorie.objects.create(nom='Maison')
        produit = Produit.objects.create(
            categorie=categorie,
            nom='Télévision',
            reference='TV-001',
            stock_actuel=1,
            seuil_alerte=2,
        )
        alerte = AlerteRupture.objects.create(
            produit=produit,
            niveau='critique',
            message='Stock bas',
            est_resolue=False,
        )

        serializer = AlerteRuptureSerializer(alerte)
        self.assertEqual(serializer.data['produit_nom'], produit.nom)
        self.assertEqual(serializer.data['niveau'], 'critique')


class ApiEndpointsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testapiuser', password='testpassword')
        self.client.force_authenticate(user=self.user)
        self.categorie = Categorie.objects.create(nom='Maison')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Bureau',
            reference='BR-001',
            stock_actuel=5,
            seuil_alerte=2,
        )
        self.produit_second = Produit.objects.create(
            categorie=self.categorie,
            nom='Chaise',
            reference='CH-001',
            stock_actuel=1,
            seuil_alerte=1,
        )
        self.alerte = AlerteRupture.objects.create(
            produit=self.produit,
            niveau='alerte',
            message='Seuil atteint',
            est_resolue=False,
        )
        self.vente = Vente.objects.create(produit=self.produit, quantite=1)
        self.approvisionnement = Approvisionnement.objects.create(
            produit=self.produit,
            quantite=10,
            fournisseur='Fournisseur SA',
        )

    def test_stats_summary_endpoint(self):
        url = reverse('stats-summary')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_products', response.json())
        self.assertIn('active_alerts', response.json())

    def test_approvisionnement_api_endpoint(self):
        url = reverse('approvisionnement-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()), 1)

    def test_product_forecast_endpoint(self):
        url = reverse('produit-forecast', args=[self.produit.pk])
        response = self.client.get(url, {'days': 7})
        self.assertEqual(response.status_code, 200)
        self.assertIn('prediction_ml', response.json())
        self.assertIn('prediction_rupture', response.json())

    def test_product_trend_endpoint(self):
        url = reverse('produit-trend', args=[self.produit.pk])
        response = self.client.get(url, {'days': 30})
        self.assertEqual(response.status_code, 200)
        self.assertIn('trend', response.json())

    def test_products_export_endpoint_returns_csv(self):
        url = reverse('exports-products')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('nom,reference', response.content.decode())

    def test_product_list_supports_search_and_pagination(self):
        url = reverse('produit-list')
        response = self.client.get(url, {'search': 'Bureau', 'page_size': 1})
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.json())
        self.assertEqual(len(response.json()['results']), 1)

    def test_export_report_pdf_authenticated(self):
        self.client.force_login(self.user)
        url = reverse('stockapp:export-report-pdf')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_import_csv_approvisionnement_no_double_increment(self):
        self.produit.stock_actuel = 5
        self.produit.save()
        
        import io
        csv_data = "reference,quantite,fournisseur\nBR-001,10,Fournisseur Test\n"
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        csv_file.name = 'approvisionnements.csv'
        
        url = reverse('approvisionnement-import-csv')
        response = self.client.post(url, {'file': csv_file}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['imported'], 1)
        
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.stock_actuel, 15)

    def test_import_csv_produit_checks_alerts(self):
        import io
        csv_data = "reference,nom,stock_actuel,seuil_alerte,categorie\nTEST-ALERT,Test Alert Product,2,5,Maison\n"
        csv_file = io.BytesIO(csv_data.encode('utf-8'))
        csv_file.name = 'produits.csv'
        
        url = reverse('produit-import-csv')
        response = self.client.post(url, {'file': csv_file}, format='multipart')
        self.assertEqual(response.status_code, 200)
        
        produit = Produit.objects.get(reference='TEST-ALERT')
        self.assertTrue(produit.rupture)
        self.assertTrue(AlerteRupture.objects.filter(produit=produit, est_resolue=False).exists())
