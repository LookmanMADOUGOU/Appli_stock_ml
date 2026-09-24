from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User
from django.utils import timezone



class Categorie(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Catégorie"
        verbose_name_plural = "Catégories"

    def __str__(self):
        return self.nom


class Client(models.Model):
    nom = models.CharField(max_length=200)
    telephone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    solde_credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return self.nom

    @property
    def total_depense(self):
        return sum(v.prix_total for v in self.ventes.all())

    @property
    def total_achats_count(self):
        return self.ventes.count()


class Fournisseur(models.Model):
    nom = models.CharField(max_length=200)
    telephone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(max_length=254, blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    dette_fournisseur = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"

    def __str__(self):
        return self.nom

    @property
    def total_approvisionnements_count(self):
        return self.approvisionnements.count()

    @property
    def total_achats_montant(self):
        total = Decimal('0.00')
        for appro in self.approvisionnements.all():
            total += appro.cout_total
        return total

    @property
    def dernier_approvisionnement(self):
        return self.approvisionnements.order_by('-date_approvisionnement').first()




class Produit(models.Model):
    STATUT_CHOICES = [
        ('ACTIF', 'Actif'),
        ('INACTIF', 'Inactif'),
        ('ARCHIVE', 'Archivé'),
    ]

    nom = models.CharField(max_length=200)
    reference = models.CharField(max_length=100, unique=True)
    sku = models.CharField(max_length=100, blank=True, null=True, unique=True)
    code_barres = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    unite = models.CharField(max_length=50, default='unité')
    stock_actuel = models.IntegerField(default=0)
    seuil_alerte = models.IntegerField(default=5)
    stock_maximum = models.IntegerField(default=100)
    categorie = models.ForeignKey(Categorie, on_delete=models.SET_NULL, null=True, blank=True)
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='ACTIF')
    date_creation = models.DateTimeField(auto_now_add=True, null=True)
    date_modification = models.DateTimeField(auto_now=True, null=True)

    @property
    def rupture(self):
        """Déterminer si le produit est en rupture de stock."""
        return self.stock_actuel <= self.seuil_alerte

    @property
    def statut_stock(self):
        """
        Logique métier centralisée du statut de stock :
        SI stock == 0 → RUPTURE
        SINON SI stock <= seuil_alerte → STOCK FAIBLE
        SINON SI stock >= stock_maximum → SURSTOCK
        SINON → STOCK NORMAL
        """
        if self.stock_actuel <= 0:
            return "RUPTURE"
        elif self.stock_actuel <= self.seuil_alerte:
            return "STOCK FAIBLE"
        elif self.stock_actuel >= self.stock_maximum:
            return "SURSTOCK"
        else:
            return "STOCK NORMAL"

    @property
    def marge_unitaire(self):
        """Marge unitaire sur le produit."""
        return self.prix_unitaire - self.prix_achat

    @property
    def taux_marge(self):
        """Taux de marge en pourcentage."""
        if self.prix_unitaire > 0:
            return round(((self.prix_unitaire - self.prix_achat) / self.prix_unitaire) * 100, 2)
        return 0.0

    @property
    def valeur_stock_achat(self):
        """Valeur totale au coût d'achat."""
        return self.stock_actuel * self.prix_achat

    @property
    def valeur_stock_vente(self):
        """Valeur totale au prix de vente."""
        return self.stock_actuel * self.prix_unitaire

    @property
    def prediction_ml(self):
        """Prédire les ventes du jour suivant."""
        from .services.prediction_service import predict_sales
        return predict_sales(self)

    @property
    def prediction_stockout(self):
        """Prédire le nombre de jours avant rupture de stock."""
        from .services.prediction_service import predict_stockout
        return predict_stockout(self)

    @property
    def prediction_rupture(self):
        """Prédire le nombre de jours avant rupture de stock (alias)."""
        from .services.prediction_service import predict_stockout
        return predict_stockout(self)

    class Meta:
        ordering = ['nom']

    def __str__(self):
        return self.nom



class MouvementStock(models.Model):
    TYPE_MOUVEMENT_CHOICES = [
        ('ENTREE', 'Entrée de stock'),
        ('SORTIE', 'Sortie de stock'),
        ('VENTE', 'Vente client'),
        ('ACHAT', 'Achat / Approvisionnement'),
        ('RETOUR', 'Retour produit'),
        ('AJUSTEMENT', 'Ajustement manuel'),
        ('INVENTAIRE', 'Régularisation d\'inventaire'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='mouvements')
    quantite = models.PositiveIntegerField()
    type_mouvement = models.CharField(max_length=20, choices=TYPE_MOUVEMENT_CHOICES)
    stock_avant = models.IntegerField()
    stock_apres = models.IntegerField()
    date_mouvement = models.DateTimeField(auto_now_add=True)
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True, default='')
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date_mouvement']
        verbose_name = "Mouvement de Stock"
        verbose_name_plural = "Mouvements de Stock"

    def __str__(self):
        return f"{self.get_type_mouvement_display()} : {self.produit.nom} ({self.quantite}) [{self.stock_avant} -> {self.stock_apres}]"


class ClotureCaisse(models.Model):
    """
    Modèle de Clôture de Caisse Journalière / Session de Caisse (Rapport Z).
    Phase 11 — Audit et traçabilité des encaissements en point de vente.
    Enregistre les encaissements théoriques par mode de règlement,
    les montants physiques déclarés par le caissier et les éventuels écarts de caisse.
    """
    STATUT_CONFORMITE_CHOICES = [
        ('CONFORME', 'Conforme (Écart nul)'),
        ('EXCEDENT', 'Excédentaire (+ Encaissé en trop)'),
        ('DEFICIT', 'Déficitaire (- Manquant en caisse)'),
    ]

    reference = models.CharField(max_length=60, unique=True, help_text="Numéro officiel Rapport Z (ex: Z-20260916-001)")
    caissier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clotures_caisse')
    date_ouverture = models.DateTimeField(default=timezone.now)
    date_cloture = models.DateTimeField(default=timezone.now)

    # Fond de caisse
    fond_de_caisse_initial = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Monnaie de départ dans le tiroir")

    # Encaissements théoriques calculés pour la session
    total_especes_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_carte_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_mobile_money_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_cheque_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_credit_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_ventes_brut = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_remises = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_ventes_net = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    nombre_tickets = models.PositiveIntegerField(default=0)
    nombre_articles = models.PositiveIntegerField(default=0)

    # Montants physiques déclarés lors du comptage réel
    montant_especes_reel = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Total espèces compté dans le tiroir")
    montant_carte_reel = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Total télécollecte TPE")
    montant_mobile_money_reel = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Total relevé Mobile Money")
    montant_cheque_reel = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Total chèques en portefeuille")

    # Écarts constatés
    ecart_especes = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    ecart_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    statut_conformite = models.CharField(max_length=20, choices=STATUT_CONFORMITE_CHOICES, default='CONFORME')

    commentaire = models.TextField(blank=True, null=True, help_text="Justification d'un éventuel écart ou note de passation")
    valide_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clotures_validees')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_cloture', '-date_creation']
        verbose_name = "Clôture de Caisse (Rapport Z)"
        verbose_name_plural = "Clôtures de Caisse (Rapports Z)"

    def __str__(self):
        return f"Rapport Z {self.reference} ({self.caissier.username}) - Net: {self.total_ventes_net} [{self.get_statut_conformite_display()}]"

    def calculer_ecarts(self):
        """
        Calcule les écarts de caisse :
        - Tiroir espèces théorique = fond de caisse initial + encaissements espèces
        - Écart espèces = montant_especes_reel - (fond_de_caisse_initial + total_especes_theorique)
        - Écart carte = montant_carte_reel - total_carte_theorique
        - Écart mobile money = montant_mobile_money_reel - total_mobile_money_theorique
        - Écart chèque = montant_cheque_reel - total_cheque_theorique
        """
        tiroir_theorique = self.fond_de_caisse_initial + self.total_especes_theorique
        self.ecart_especes = self.montant_especes_reel - tiroir_theorique
        ecart_carte = self.montant_carte_reel - self.total_carte_theorique
        ecart_momo = self.montant_mobile_money_reel - self.total_mobile_money_theorique
        ecart_cheque = self.montant_cheque_reel - self.total_cheque_theorique
        self.ecart_total = self.ecart_especes + ecart_carte + ecart_momo + ecart_cheque

        if self.ecart_total == Decimal('0.00'):
            self.statut_conformite = 'CONFORME'
        elif self.ecart_total > Decimal('0.00'):
            self.statut_conformite = 'EXCEDENT'
        else:
            self.statut_conformite = 'DEFICIT'

    def save(self, *args, **kwargs):
        self.calculer_ecarts()
        super().save(*args, **kwargs)

    @property
    def total_tiroir_theorique(self):
        """Total attendu dans le tiroir espèces (fond initial + espèces encaissées)."""
        return self.fond_de_caisse_initial + self.total_especes_theorique

    @property
    def total_declare_reel(self):
        """Somme totale déclarée tous moyens confondus."""
        return self.montant_especes_reel + self.montant_carte_reel + self.montant_mobile_money_reel + self.montant_cheque_reel


class Vente(models.Model):
    MODE_PAIEMENT_CHOICES = [
        ('ESPECES', 'Espèces'),
        ('CARTE', 'Carte Bancaire'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CHEQUE', 'Chèque'),
        ('CREDIT', 'Crédit / Avoir'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    client = models.ForeignKey('Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventes')
    cloture = models.ForeignKey('ClotureCaisse', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventes')
    quantite = models.PositiveIntegerField()
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    prix_achat = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    remise = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    mode_paiement = models.CharField(max_length=50, choices=MODE_PAIEMENT_CHOICES, default='ESPECES')
    reference_ticket = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    date_vente = models.DateTimeField(auto_now_add=True)

    @property
    def montant_brut(self):
        return self.quantite * self.prix_unitaire

    @property
    def prix_total(self):
        tot = (self.quantite * self.prix_unitaire) - self.remise
        return max(tot, Decimal('0.00')) if hasattr(tot, '__gt__') else max(tot, 0)

    @property
    def marge_unitaire(self):
        return self.prix_unitaire - self.prix_achat

    @property
    def benefice_total(self):
        return self.prix_total - (self.quantite * self.prix_achat)

    def save(self, *args, **kwargs):
        if not self.prix_unitaire and self.produit:
            self.prix_unitaire = self.produit.prix_unitaire
        if not self.prix_achat and self.produit:
            self.prix_achat = self.produit.prix_achat
        if not self.reference_ticket:
            import uuid
            self.reference_ticket = f"TCK-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date_vente']

    def __str__(self):
        return f"{self.produit.nom} - {self.quantite} x {self.prix_unitaire} [{self.get_mode_paiement_display()}]"



class Approvisionnement(models.Model):
    STATUT_CHOICES = [
        ('RECU', 'Reçu / En stock'),
        ('COMMANDE', 'Commandé / En cours'),
        ('ANNULE', 'Annulé'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.PositiveIntegerField()
    cout_unitaire = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Coût unitaire d'achat")
    date_approvisionnement = models.DateTimeField(auto_now_add=True)
    fournisseur = models.CharField(max_length=200, blank=True)
    fournisseur_fk = models.ForeignKey('Fournisseur', on_delete=models.SET_NULL, null=True, blank=True, related_name='approvisionnements')
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='RECU')
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date_approvisionnement']

    def __str__(self):
        return f"{self.produit.nom} +{self.quantite} ({self.nom_fournisseur})"

    @property
    def cout_total(self):
        cu = self.cout_unitaire if (self.cout_unitaire and self.cout_unitaire > 0) else (self.produit.prix_achat or Decimal('0.00'))
        return Decimal(self.quantite) * cu

    @property
    def nom_fournisseur(self):
        if self.fournisseur_fk:
            return self.fournisseur_fk.nom
        return self.fournisseur or "Fournisseur Général"

    def save(self, *args, **kwargs):
        # Synchronisation automatique bidirectionnelle
        if self.fournisseur_fk and not self.fournisseur:
            self.fournisseur = self.fournisseur_fk.nom
        elif not self.fournisseur_fk and self.fournisseur and self.fournisseur.strip():
            fourn, _ = Fournisseur.objects.get_or_create(nom=self.fournisseur.strip())
            self.fournisseur_fk = fourn
        super().save(*args, **kwargs)


class AlerteRupture(models.Model):
    NIVEAU_CHOICES = [
        ('info', 'Information'),
        ('alerte', 'Alerte'),
        ('critique', 'Critique'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='alertes')
    niveau = models.CharField(max_length=10, choices=NIVEAU_CHOICES, default='alerte')
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    est_resolue = models.BooleanField(default=False)
    date_resolution = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"Alerte {self.niveau}: {self.produit.nom}"


class Depense(models.Model):
    """
    Modèle de gestion des charges et dépenses d'exploitation (Phase 7 - Finances & Trésorerie).
    Permet le calcul du résultat net réel d'exploitation et le suivi du cash out.
    """
    CATEGORIE_DEPENSE_CHOICES = [
        ('LOYER', 'Loyer & Charges locatives'),
        ('SALAIRE', 'Salaires & Rémunérations'),
        ('ELECTRICITE', 'Électricité & Eau'),
        ('INTERNET', 'Télécoms & Internet'),
        ('TRANSPORT', 'Transport & Logistique'),
        ('MARKETING', 'Publicité & Marketing'),
        ('FOURNITURE', 'Fournitures de bureau'),
        ('MAINTENANCE', 'Entretien & Réparations'),
        ('TAXE', 'Impôts & Taxes'),
        ('AUTRE', 'Autre charge opérationnelle'),
    ]

    titre = models.CharField(max_length=200)
    categorie = models.CharField(max_length=50, choices=CATEGORIE_DEPENSE_CHOICES, default='AUTRE')
    montant = models.DecimalField(max_digits=12, decimal_places=2)
    date_depense = models.DateField(default=timezone.now)
    beneficiaire = models.CharField(max_length=200, blank=True, null=True)
    justificatif = models.CharField(max_length=100, blank=True, null=True, help_text="Numéro de reçu ou facture")
    notes = models.TextField(blank=True, null=True)
    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_depense', '-date_creation']
        verbose_name = "Dépense / Charge"
        verbose_name_plural = "Dépenses & Charges"

    def __str__(self):
        return f"{self.titre} - {self.montant} ({self.get_categorie_display()})"


class JournalAudit(models.Model):
    """
    Journal d'Audit Centralisé SMART-TECH (Phase 9 - Rôles, Permissions & Audit).
    Enregistre de façon immuable toutes les actions d'administration,
    modifications de prix, ajustements de stock, suppressions et règlements financiers.
    """
    ACTION_CHOICES = [
        ('CREATION', 'Création'),
        ('MODIFICATION_PRIX', 'Changement de Prix'),
        ('MODIFICATION', 'Modification Fiche'),
        ('SUPPRESSION', 'Suppression'),
        ('AJUSTEMENT_STOCK', 'Ajustement de Stock'),
        ('VENTE', 'Vente / Encaissement'),
        ('CLOTURE_CAISSE', 'Clôture Caisse (Rapport Z)'),
        ('REGLEMENT_DETTE', 'Règlement Dette / Créance'),
        ('DEPENSE', 'Charge OPEX'),
        ('CONNEXION', 'Connexion / Sécurité'),
    ]

    MODULE_CHOICES = [
        ('PRODUIT', 'Produits & Tarifs'),
        ('STOCK', 'Stock & Inventaire'),
        ('VENTE', 'Ventes & Caisse POS'),
        ('CAISSE', 'Caisse & Sessions'),
        ('APPROVISIONNEMENT', 'Approvisionnements'),
        ('FOURNISSEUR', 'Fournisseurs & Dettes'),
        ('CLIENT', 'Clients & Crédits'),
        ('FINANCES', 'Finances & OPEX'),
        ('SECURITE', 'Sécurité & Rôles'),
        ('NOTIFICATION', 'Centre d\'Alertes & Notifications'),
    ]

    utilisateur = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    objet_concerne = models.CharField(max_length=255, help_text="Entité visée (ex: Produit #12, Vente TCK-...)")
    description = models.TextField(help_text="Détail explicatif de l'opération (valeurs avant/après, motif)")
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Journal d'Audit"
        verbose_name_plural = "Journaux d'Audit"

    def __str__(self):
        user_str = self.utilisateur.username if self.utilisateur else "Système"
        return f"[{self.date_creation.strftime('%d/%m/%Y %H:%M')}] {self.get_action_display()} sur {self.objet_concerne} par {user_str}"

    @classmethod
    def log_action(cls, utilisateur, action, module, objet_concerne, description, request=None):
        """
        Méthode utilitaire rapide pour consigner un événement d'audit.
        """
        ip = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
            if not utilisateur and request.user and request.user.is_authenticated:
                utilisateur = request.user

        return cls.objects.create(
            utilisateur=utilisateur,
            action=action,
            module=module,
            objet_concerne=str(objet_concerne)[:255],
            description=description,
            adresse_ip=ip
        )


class Notification(models.Model):
    """
    Système de Notifications Internes Proactives & Alertes Métier (Phase 12).
    Alerte en temps réel sur les ruptures de stock, dettes fournisseurs,
    créances clients, anomalies de caisse et événements système.
    """
    TYPE_CHOICES = [
        ('STOCK_RUPTURE', 'Rupture de Stock'),
        ('STOCK_FAIBLE', 'Seuil d\'Alerte Stock'),
        ('DETTE_FOURNISSEUR', 'Dette Fournisseur'),
        ('CREANCE_CLIENT', 'Créance Client'),
        ('ANOMALIE_CAISSE', 'Anomalie de Caisse'),
        ('SYSTEME', 'Information Système'),
    ]

    NIVEAU_CHOICES = [
        ('INFO', 'Information'),
        ('WARNING', 'Avertissement'),
        ('CRITICAL', 'Critique'),
    ]

    destinataire = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        help_text="Destinataire spécifique ou null pour visibilité équipe/staff"
    )
    type_notification = models.CharField(max_length=30, choices=TYPE_CHOICES, default='SYSTEME')
    niveau = models.CharField(max_length=15, choices=NIVEAU_CHOICES, default='INFO')
    titre = models.CharField(max_length=200)
    message = models.TextField()
    lien = models.CharField(max_length=255, blank=True, null=True, help_text="Lien d'action rapide")
    cle_unicite = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
        help_text="Clé de déduplication d'alerte (ex: stock_rupture_12)"
    )
    est_lue = models.BooleanField(default=False, db_index=True)
    est_archivee = models.BooleanField(default=False, db_index=True)
    date_creation = models.DateTimeField(auto_now_add=True, db_index=True)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        status = "Lue" if self.est_lue else "Non lue"
        return f"[{self.get_niveau_display()}] {self.titre} ({status})"

    def marquer_comme_lue(self):
        if not self.est_lue:
            self.est_lue = True
            self.date_lecture = timezone.now()
            self.save(update_fields=['est_lue', 'date_lecture'])

    def archiver(self):
        self.est_archivee = True
        if not self.est_lue:
            self.est_lue = True
            self.date_lecture = timezone.now()
        self.save(update_fields=['est_archivee', 'est_lue', 'date_lecture'])