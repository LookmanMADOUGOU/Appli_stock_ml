"""
Service de génération automatique des Bons de Commande Fournisseur.

Identifie les produits en rupture ou prévus en rupture sous 7 jours,
calcule la quantité conseillée et génère un bon de commande PDF imprimable
ou convertible en vrais approvisionnements.
"""

import io
from datetime import timedelta
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from stockapp.models import Produit, Approvisionnement
from stockapp.services.prediction_service import predict_stockout_ml, get_demand_forecast


def generate_purchase_order_data() -> dict:
    """
    Analyse le stock et les prédictions ML pour construire les items du Bon de Commande.
    
    Returns:
        dict: {
            'date_generation': datetime,
            'items': list[dict],
            'total_articles': int,
            'total_estime': float,
        }
    """
    produits = Produit.objects.select_related('categorie').all()
    items = []
    total_estime = 0.0
    total_articles = 0

    for product in produits:
        # Vérifier si le produit est en alerte ou prédit en rupture <= 7 jours
        stockout_days = predict_stockout_ml(product, days_lookback=30)

        doit_commander = False
        raison = ""

        if product.stock_actuel <= 0:
            doit_commander = True
            raison = "Rupture totale de stock"
        elif product.stock_actuel <= product.seuil_alerte:
            doit_commander = True
            raison = f"Seuil d'alerte atteint ({product.stock_actuel}/{product.seuil_alerte})"
        elif isinstance(stockout_days, (int, float)) and stockout_days <= 7.0:
            doit_commander = True
            raison = f"IA: Rupture estimée dans {stockout_days} jour(s)"

        if doit_commander:
            # Demande prédite pour 14 jours
            demand_info = get_demand_forecast(product, days_ahead=14, days_lookback=30)
            if isinstance(demand_info, dict) and 'predictions' in demand_info:
                demande_14j = sum(demand_info['predictions'].values())
            else:
                demande_14j = product.seuil_alerte * 3

            # Quantité recommandée = Max(Demande 14j + seuil - stock, 10)
            qte_rec = max(int(demande_14j + product.seuil_alerte - product.stock_actuel), 10)
            prix_unit_achat = float(product.prix_achat) if product.prix_achat > 0 else float(product.prix_unitaire * 0.7)
            montant_estime = qte_rec * prix_unit_achat

            items.append({
                'produit': product,
                'produit_id': product.id,
                'nom': product.nom,
                'reference': product.reference,
                'categorie': product.categorie.nom if product.categorie else "Général",
                'stock_actuel': product.stock_actuel,
                'seuil_alerte': product.seuil_alerte,
                'quantite_recommandee': qte_rec,
                'prix_achat_unitaire': round(prix_unit_achat, 2),
                'montant_estime': round(montant_estime, 2),
                'raison': raison,
            })

            total_articles += qte_rec
            total_estime += montant_estime

    return {
        'date_generation': timezone.now(),
        'items': items,
        'nb_produits': len(items),
        'total_articles': total_articles,
        'total_estime': round(total_estime, 2),
    }


def generate_purchase_order_pdf(order_data: dict) -> bytes:
    """
    Génère un fichier PDF élégant du Bon de Commande Fournisseur.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=30, rightMargin=30, topMargin=35, bottomMargin=35)
    styles = getSampleStyleSheet()

    # Style personnalisé
    title_style = ParagraphStyle(
        'POTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'POSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b')
    )

    story = []

    # En-tête du document
    story.append(Paragraph("BON DE COMMANDE FOURNISSEUR — SUGGESTION IA", title_style))
    story.append(Paragraph(f"Généré automatiquement le {order_data['date_generation'].strftime('%d/%m/%Y à %H:%M')}", subtitle_style))
    story.append(Spacer(1, 15))

    # Bloc Résumé
    summary_text = (
        f"<b>Produits à réapprovisionner :</b> {order_data['nb_produits']} | "
        f"<b>Total articles à commander :</b> {order_data['total_articles']} | "
        f"<b>Budget total estimé :</b> {order_data['total_estime']} FCFA/€"
    )
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 15))

    # Tableau des produits
    headers = ['Réf', 'Produit', 'Stock', 'Seuil', 'Qté Rec.', 'P.U Achat', 'Total Est.', 'Raison']
    table_data = [headers]

    for item in order_data['items']:
        table_data.append([
            item['reference'],
            item['nom'],
            str(item['stock_actuel']),
            str(item['seuil_alerte']),
            str(item['quantite_recommandee']),
            f"{item['prix_achat_unitaire']} FCFA",
            f"{item['montant_estime']} FCFA",
            item['raison']
        ])

    if not order_data['items']:
        table_data.append(['—', 'Aucun produit en rupture ou prévision de rupture', '—', '—', '—', '—', '—', '—'])

    tbl = Table(table_data, colWidths=[60, 110, 45, 45, 55, 75, 75, 85])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0891b2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (2, 0), (6, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 20))

    # Signatures
    sig_data = [
        ['Visa Responsable Stock', 'Visa Fournisseur'],
        ['\n\n__________________________', '\n\n__________________________']
    ]
    sig_tbl = Table(sig_data, colWidths=[270, 270])
    sig_tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
    ]))
    story.append(sig_tbl)

    doc.build(story)
    return buffer.getvalue()


def convert_order_data_to_approvisionnements(order_data: dict, fournisseur_nom: str = "Fournisseur Automatique IA") -> int:
    """
    Convertit la suggestion de bon de commande en véritables enregistrements d'approvisionnements.
    Le stock des produits est automatiquement crédité via les signals / services.
    """
    created_count = 0
    for item in order_data.get('items', []):
        p_id = item['produit_id']
        qte = item['quantite_recommandee']
        try:
            produit = Produit.objects.get(pk=p_id)
            Approvisionnement.objects.create(
                produit=produit,
                quantite=qte,
                fournisseur=fournisseur_nom
            )
            created_count += 1
        except Produit.DoesNotExist:
            continue
    return created_count
