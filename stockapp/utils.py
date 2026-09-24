"""
Fonctions utilitaires génériques pour SMART-TECH.
Formatage des montants, génération de références uniques et aides documents.
"""

import uuid
from decimal import Decimal
from django.utils import timezone


def format_currency(amount, currency="FCFA/€") -> str:
    """Formate un montant financier avec séparateur de milliers."""
    if amount is None:
        amount = Decimal('0.00')
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    return f"{amount:,.2f} {currency}".replace(',', ' ')


def generate_ticket_number() -> str:
    """Génère un numéro unique de ticket de caisse : TCK-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    random_part = uuid.uuid4().hex[:6].upper()
    return f"TCK-{date_str}-{random_part}"


def generate_invoice_number() -> str:
    """Génère un numéro unique de facture commerciale : FAC-YYYYMMDD-XXXXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    random_part = uuid.uuid4().hex[:6].upper()
    return f"FAC-{date_str}-{random_part}"
