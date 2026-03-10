"""
Multi-Country Tax Engine

Replaces the hardcoded GST module with a dynamic, per-country tax calculation engine.
"""

from decimal import Decimal
from typing import Any, Dict, List

from .. import db
from ..models import Product, TransactionItem
from ..models.expansion_models import CountryTaxConfig, StoreTaxRegistration

# Registry of country-specific tax calculators
_tax_calculators = {}


class TaxCalculationResult:
    def __init__(self, taxable_amount: Decimal, tax_amount: Decimal, breakdown: dict[str, Decimal]):
        self.taxable_amount = taxable_amount
        self.tax_amount = tax_amount
        self.breakdown = breakdown


def register_tax_calculator(country_code: str):
    """Decorator to register a country-specific tax calculation strategy."""
    def decorator(cls):
        _tax_calculators[country_code] = cls
        return cls
    return decorator


class BaseTaxCalculator:
    """Base class for country-specific tax calculations."""

    def __init__(self, store_id: int, country_code: str):
        self.store_id = store_id
        self.country_code = country_code
        self.registration = self._get_registration()
        self.config = self._get_config()

    def _get_registration(self):
        return db.session.query(StoreTaxRegistration).filter_by(
            store_id=self.store_id, country_code=self.country_code
        ).first()

    def _get_config(self):
        return db.session.query(CountryTaxConfig).filter_by(
            country_code=self.country_code
        ).first()

    def calculate_tax(self, items: list[dict[str, Any]]) -> TaxCalculationResult:
        """
        Calculate tax for a list of items.
        Each item is expected to have 'product_id', 'quantity', 'selling_price', 'discount'.
        Returns TaxCalculationResult.
        """
        raise NotImplementedError("Subclasses must implement calculate_tax")


@register_tax_calculator("IN")
class IndiaGSTCalculator(BaseTaxCalculator):
    """India GST calculation (IGST, CGST, SGST)."""

    def calculate_tax(self, items: list[dict[str, Any]]) -> TaxCalculationResult:
        if not self.registration or not self.registration.is_tax_enabled:
            return TaxCalculationResult(Decimal("0"), Decimal("0"), {})

        total_taxable = Decimal("0")
        total_tax = Decimal("0")
        breakdown = {"CGST": Decimal("0"), "SGST": Decimal("0"), "IGST": Decimal("0")}

        # Note: In a real implementation, we would check if it's intrastate vs interstate
        # For this prototype, we'll assume intrastate (CGST + SGST)

        for item in items:
            product = db.session.query(Product).get(item["product_id"])
            if not product or product.gst_category in ("EXEMPT", "ZERO"):
                continue

            # Need to fetch rate from HSN or category, here we use standard rate as fallback
            rate = Decimal(str(self.config.standard_rate))
            if product.hsn_code:
                from ..models import HSNMaster
                hsn = db.session.query(HSNMaster).filter_by(hsn_code=product.hsn_code).first()
                if hsn and hsn.default_gst_rate:
                    rate = Decimal(str(hsn.default_gst_rate))

            qty = Decimal(str(item["quantity"]))
            sp = Decimal(str(item["selling_price"]))
            disc = Decimal(str(item.get("discount", 0)))

            line_total = (qty * sp) - disc
            taxable = line_total / (1 + (rate / 100))
            tax = line_total - taxable

            total_taxable += taxable
            total_tax += tax
            breakdown["CGST"] += tax / 2
            breakdown["SGST"] += tax / 2

        return TaxCalculationResult(
            round(total_taxable, 2),
            round(total_tax, 2),
            {k: round(v, 2) for k, v in breakdown.items()}
        )


@register_tax_calculator("US")
class USSalesTaxCalculator(BaseTaxCalculator):
    """US Sales Tax calculation."""

    def calculate_tax(self, items: list[dict[str, Any]]) -> TaxCalculationResult:
        if not self.registration or not self.registration.is_tax_enabled:
            return TaxCalculationResult(Decimal("0"), Decimal("0"), {})

        # In US, tax is usually added on top, but for consistency with pos-systems
        # we might assume tax inclusive or exclusive depending on store settings.
        # Here we assume exclusive, then add it.

        base_rate = Decimal(str(self.config.standard_rate))
        state_rate = Decimal("0")

        if self.config.has_subnational_tax and self.registration.state_province:
            state_rates = self.config.subnational_config or {}
            state_rate = Decimal(str(state_rates.get(self.registration.state_province, 0)))

        total_rate = base_rate + state_rate

        total_taxable = Decimal("0")
        total_tax = Decimal("0")
        breakdown = {"STATE_TAX": Decimal("0"), "LOCAL_TAX": Decimal("0")}

        for item in items:
            qty = Decimal(str(item["quantity"]))
            sp = Decimal(str(item["selling_price"]))
            disc = Decimal(str(item.get("discount", 0)))

            taxable = (qty * sp) - disc
            tax = taxable * (total_rate / 100)

            total_taxable += taxable
            total_tax += tax

            breakdown["STATE_TAX"] += taxable * (state_rate / 100)
            breakdown["LOCAL_TAX"] += taxable * (base_rate / 100)

        return TaxCalculationResult(
            round(total_taxable, 2),
            round(total_tax, 2),
            {k: round(v, 2) for k, v in breakdown.items()}
        )


def get_tax_calculator(store_id: int, country_code: str) -> BaseTaxCalculator:
    """Factory to get the correct tax calculator for a country."""
    calculator_cls = _tax_calculators.get(country_code)
    if not calculator_cls:
        # Fallback to a generic VAT calculator if specific one doesn't exist
        return GenericVATCalculator(store_id, country_code)
    return calculator_cls(store_id, country_code)


class GenericVATCalculator(BaseTaxCalculator):
    """Generic VAT/IVA calculator for EU, UK, Latin America, Africa."""

    def calculate_tax(self, items: list[dict[str, Any]]) -> TaxCalculationResult:
        if not self.registration or not self.registration.is_tax_enabled:
            return TaxCalculationResult(Decimal("0"), Decimal("0"), {})

        rate = Decimal(str(self.config.standard_rate))

        total_taxable = Decimal("0")
        total_tax = Decimal("0")

        tax_name = self.config.tax_type

        for item in items:
            product = db.session.query(Product).get(item["product_id"])
            if not product:
                continue

            # In a real app, we'd check if product is in reduced/zero/exempt list

            qty = Decimal(str(item["quantity"]))
            sp = Decimal(str(item["selling_price"]))
            disc = Decimal(str(item.get("discount", 0)))

            line_total = (qty * sp) - disc
            taxable = line_total / (1 + (rate / 100))
            tax = line_total - taxable

            total_taxable += taxable
            total_tax += tax

        return TaxCalculationResult(
            round(total_taxable, 2),
            round(total_tax, 2),
            {tax_name: round(total_tax, 2)}
        )
