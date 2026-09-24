from django.urls import path
from . import views

app_name = 'stockapp'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('finances/', views.finances_view, name='finances'),
    path('finances/depenses/<int:pk>/supprimer/', views.depense_supprimer, name='depense-supprimer'),
    path('finances/rapport-pdf/', views.finance_report_pdf, name='finance-report-pdf'),

    # Produits
    path('produits/', views.produits, name='produits-list'),
    path('produits/ajouter/', views.produit_ajouter, name='produit-ajouter'),
    path('produits/<int:pk>/modifier/', views.produit_modifier, name='produit-modifier'),
    path('produits/<int:pk>/supprimer/', views.produit_supprimer, name='produit-supprimer'),

    # Stock & Inventaire
    path('stock/', views.stock_inventaire, name='stock-inventaire'),
    path('stock/ajuster/', views.ajuster_stock_view, name='ajuster-stock'),
    path('mouvements/', views.mouvements_list_view, name='mouvements-list'),


    # Catégories
    path('categories/', views.categories, name='categories-list'),
    path('categories/<int:pk>/modifier/', views.categorie_modifier, name='categorie-modifier'),
    path('categories/<int:pk>/supprimer/', views.categorie_supprimer, name='categorie-supprimer'),

    # Ventes & Caisse POS
    path('caisse/', views.caisse_pos, name='caisse-pos'),
    path('ventes/', views.ventes, name='ventes-list'),
    path('ventes/<int:pk>/supprimer/', views.vente_supprimer, name='vente-supprimer'),
    path('ventes/<int:pk>/recu/', views.telecharger_recu_pdf, name='vente-recu-pdf'),
    path('ventes/<int:pk>/facture/', views.telecharger_facture_pdf, name='vente-facture-pdf'),

    # Prévisions IA & Aide à la Décision (Phase 8)
    path('previsions-decision/', views.previsions_decision_view, name='previsions-decision'),
    path('previsions-decision/api/produit/<int:pk>/', views.produit_prevision_chart_api, name='previsions-decision-chart-api'),
    path('previsions-decision/pdf/', views.previsions_decision_pdf, name='previsions-decision-pdf'),

    # Clients & Fournisseurs
    path('clients/', views.clients_list_view, name='clients-list'),
    path('fournisseurs/', views.fournisseurs_list_view, name='fournisseurs-list'),
    path('fournisseurs/<int:pk>/', views.fournisseur_detail_view, name='fournisseur-detail'),
    path('fournisseurs/<int:pk>/regler-dette/', views.fournisseur_regler_dette_view, name='fournisseur-regler-dette'),

    # Approvisionnements & Bon de commande IA
    path('approvisionnements/', views.approvisionnements, name='approvisionnements-list'),
    path('approvisionnements/<int:pk>/supprimer/', views.approvisionnement_supprimer, name='approvisionnement-supprimer'),
    path('approvisionnements/bon-de-commande/', views.bon_de_commande, name='bon-de-commande'),
    path('approvisionnements/bon-de-commande/pdf/', views.bon_de_commande_pdf, name='bon-de-commande-pdf'),
    path('approvisionnements/bon-de-commande/valider/', views.bon_de_commande_valider, name='bon-de-commande-valider'),

    # Notifications & Résumé (Phase 12)
    path('notifications/', views.notifications_hub_view, name='notifications-hub'),
    path('notifications/<int:pk>/lire/', views.marquer_notification_lue_view, name='notification-lire'),
    path('notifications/tout-lire/', views.marquer_toutes_notifications_lues_view, name='notification-tout-lire'),
    path('notifications/<int:pk>/archiver/', views.archiver_notification_view, name='notification-archiver'),
    path('notifications/rafraichir/', views.rafraichir_alertes_view, name='notifications-rafraichir'),
    path('notifications/api/unread/', views.api_unread_notifications_view, name='notifications-api-unread'),
    path('notifications/envoyer-resume/', views.envoyer_resume_journalier_view, name='envoyer-resume-journalier'),

    # PWA Routes
    path('service-worker.js', views.service_worker, name='service-worker'),
    path('manifest.json', views.pwa_manifest, name='manifest'),
    path('offline/', views.offline_view, name='offline'),

    # Journal d'Audit Exécutif (Phase 9)
    path('audit/', views.journal_audit_view, name='journal-audit'),
    path('audit/export/csv/', views.journal_audit_export_csv, name='journal-audit-export-csv'),

    # Clôtures de Caisse & Sessions (Phase 11)
    path('caisse/clotures/', views.clotures_caisse_list_view, name='clotures-caisse-list'),
    path('caisse/cloturer/', views.cloture_caisse_view, name='cloture-caisse'),
    path('caisse/clotures/<int:pk>/', views.cloture_caisse_detail_view, name='cloture-caisse-detail'),
    path('caisse/clotures/<int:pk>/pdf/', views.cloture_caisse_pdf_view, name='cloture-caisse-pdf'),

    # Hub Central des Rapports & Exports Comptables (Phase 11)
    path('rapports/', views.rapports_hub_view, name='rapports-hub'),
    path('rapports/export/stock-valorise/csv/', views.export_stock_valorise_csv, name='export-stock-valorise-csv'),
    path('rapports/export/ventes-detaillees/csv/', views.export_ventes_detaillees_csv, name='export-ventes-detaillees-csv'),
    path('rapports/export/compte-resultat/csv/', views.export_compte_resultat_csv, name='export-compte-resultat-csv'),

    # Sauvegardes & Sécurité des Données (Phase 13)
    path('securite/sauvegardes/', views.sauvegardes_view, name='sauvegardes'),
    path('securite/sauvegardes/creer/', views.creer_sauvegarde_view, name='sauvegarde-creer'),
    path('securite/sauvegardes/<str:filename>/telecharger/', views.telecharger_sauvegarde_view, name='sauvegarde-telecharger'),
    path('securite/sauvegardes/<str:filename>/restaurer/', views.restaurer_sauvegarde_view, name='sauvegarde-restaurer'),
    path('securite/sauvegardes/<str:filename>/supprimer/', views.supprimer_sauvegarde_view, name='sauvegarde-supprimer'),
    path('securite/audit/purger/', views.purger_logs_audit_view, name='audit-logs-purger'),

    # Export Legacy
    path('export/pdf/', views.export_report_pdf, name='export-report-pdf'),
]

