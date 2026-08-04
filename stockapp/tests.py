from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
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


class VentePrixUnitaireTests(TestCase):
    def setUp(self):
        self.categorie = Categorie.objects.create(nom='Boissons')
        self.produit = Produit.objects.create(
            categorie=self.categorie,
            nom='Jus d Orange',
            reference='JUS-001',
            stock_actuel=50,
            seuil_alerte=5,
            prix_unitaire=500.00,
        )

    def test_vente_copies_produit_prix_unitaire_when_blank(self):
        vente = Vente.objects.create(produit=self.produit, quantite=4)
        self.assertEqual(vente.prix_unitaire, 500.00)
        self.assertEqual(vente.prix_total, 2000.00)

    def test_vente_calculates_prix_total(self):
        vente = Vente.objects.create(produit=self.produit, quantite=3, prix_unitaire=450.00)
        self.assertEqual(vente.prix_unitaire, 450.00)
        self.assertEqual(vente.prix_total, 1350.00)

    def test_ventes_view_returns_journal_aggregation(self):
        user = User.objects.create_user(username='testuser', password='password')
        self.client.force_login(user)

        Vente.objects.create(produit=self.produit, quantite=4, prix_unitaire=500.00)
        Vente.objects.create(produit=self.produit, quantite=2, prix_unitaire=500.00)

        url = reverse('stockapp:ventes-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('journal_ventes', response.context)
        
        journal = response.context['journal_ventes']
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]['produit_nom'], 'Jus d Orange')
        self.assertEqual(journal[0]['total_quantite'], 6)
        self.assertEqual(journal[0]['decomposition'], '4 + 2')
        self.assertEqual(journal[0]['montant_total'], 3000.00)
        self.assertEqual(response.context['chiffre_affaires_jour'], 3000.00)

    def test_vente_calculates_benefice_and_margin(self):
        self.produit.prix_achat = 300.00
        self.produit.save()

        vente = Vente.objects.create(produit=self.produit, quantite=5, prix_unitaire=500.00)
        self.assertEqual(vente.prix_achat, 300.00)
        self.assertEqual(vente.marge_unitaire, 200.00)
        self.assertEqual(vente.benefice_total, 1000.00)

    def test_telecharger_recu_pdf_view(self):
        user = User.objects.create_user(username='pdfuser', password='password')
        self.client.force_login(user)
        vente = Vente.objects.create(produit=self.produit, quantite=2, prix_unitaire=500.00)

        url = reverse('stockapp:vente-recu-pdf', args=[vente.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(len(response.content) > 0)

    def test_ventes_view_periode_filtering(self):
        user = User.objects.create_user(username='periodeuser', password='password')
        self.client.force_login(user)

        Vente.objects.create(produit=self.produit, quantite=2, prix_unitaire=500.00)

        for p in ['jour', 'semaine', 'mois', 'annee']:
            url = reverse('stockapp:ventes-list') + f'?periode={p}'
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['periode'], p)
            self.assertIn('chiffre_affaires_periode', response.context)


class PurchaseOrderAndNotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='iauser', password='password')
        self.client.force_login(self.user)

        self.categorie = Categorie.objects.create(nom='High Tech')
        self.produit_rupture = Produit.objects.create(
            categorie=self.categorie,
            nom='Ordinateur Portable',
            reference='ORD-001',
            stock_actuel=1,
            seuil_alerte=5,
            prix_unitaire=500000.00,
            prix_achat=350000.00,
        )

    def test_purchase_order_data_generation(self):
        from stockapp.services.purchase_order_service import generate_purchase_order_data
        data = generate_purchase_order_data()
        self.assertGreaterEqual(data['nb_produits'], 1)
        self.assertEqual(data['items'][0]['produit_id'], self.produit_rupture.id)
        self.assertGreater(data['total_articles'], 0)

    def test_purchase_order_pdf_generation(self):
        from stockapp.services.purchase_order_service import generate_purchase_order_data, generate_purchase_order_pdf
        data = generate_purchase_order_data()
        pdf_bytes = generate_purchase_order_pdf(data)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 0)

    def test_purchase_order_views_and_validation(self):
        url = reverse('stockapp:bon-de-commande')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)

        pdf_url = reverse('stockapp:bon-de-commande-pdf')
        res_pdf = self.client.get(pdf_url)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

        valider_url = reverse('stockapp:bon-de-commande-valider')
        res_val = self.client.post(valider_url)
        self.assertEqual(res_val.status_code, 302)
        self.assertTrue(Approvisionnement.objects.filter(produit=self.produit_rupture).exists())

    def test_daily_summary_generation_and_view(self):
        from stockapp.services.alert_service import generer_et_envoyer_resume_journalier
        Vente.objects.create(produit=self.produit_rupture, quantite=2, prix_unitaire=500000.00, prix_achat=350000.00)

        res = generer_et_envoyer_resume_journalier()
        self.assertEqual(res['chiffre_affaires'], 1000000.00)
        self.assertEqual(res['benefice_net'], 300000.00)
        self.assertEqual(res['total_articles'], 2)

        view_url = reverse('stockapp:envoyer-resume-journalier')
        response = self.client.post(view_url)
        self.assertEqual(response.status_code, 302)

    def test_ml_seasonality_prediction(self):
        from stockapp.services.prediction_service import get_demand_forecast, predict_sales
        # Seed 7 sales on 7 distinct days to trigger RandomForest
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
        self.assertIn('Look-Tech', response.content.decode('utf-8'))




