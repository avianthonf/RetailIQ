"""
Tests for Team 9 Multi-Country Expansion
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app import db
from app.einvoicing.engine import get_einvoice_adapter
from app.kyc.engine import get_kyc_adapter
from app.models import Product, Transaction
from app.models.expansion_models import Country, CountryTaxConfig, KYCProvider, StoreTaxRegistration
from app.tax_engine.engine import get_tax_calculator


@pytest.fixture
def expansion_setup(app, test_store):
    """Setup expansion metadata (Countries, Taxes, Providers)."""

    c_in = Country(
        code="IN",
        name="India",
        default_currency="INR",
        default_locale="en-IN",
        timezone="Asia/Kolkata",
        tax_system="GST",
        is_active=True,
    )
    c_us = Country(
        code="US",
        name="United States",
        default_currency="USD",
        default_locale="en-US",
        timezone="America/New_York",
        tax_system="SALES_TAX",
        is_active=True,
    )
    c_br = Country(
        code="BR",
        name="Brazil",
        default_currency="BRL",
        default_locale="pt-BR",
        timezone="America/Sao_Paulo",
        tax_system="IVA",
        is_active=True,
    )

    db.session.add_all([c_in, c_us, c_br])
    db.session.flush()

    t_in = CountryTaxConfig(country_code="IN", tax_type="GST", standard_rate=18.0)
    t_us = CountryTaxConfig(
        country_code="US",
        tax_type="SALES_TAX",
        standard_rate=6.0,
        has_subnational_tax=True,
        subnational_config={"CA": 2.5, "NY": 4.0},
    )
    t_br = CountryTaxConfig(
        country_code="BR", tax_type="IVA", standard_rate=17.0, e_invoice_required=True, e_invoice_format="NF_E"
    )

    db.session.add_all([t_in, t_us, t_br])
    db.session.flush()

    reg_us = StoreTaxRegistration(
        store_id=test_store.store_id, country_code="US", tax_id="12-3456789", state_province="CA", is_tax_enabled=True
    )
    reg_br = StoreTaxRegistration(
        store_id=test_store.store_id, country_code="BR", tax_id="00.000.000/0001-91", is_tax_enabled=True
    )

    db.session.add_all([reg_us, reg_br])

    k_aadhaar = KYCProvider(code="aadhaar", name="Aadhaar", country_code="IN", verification_type="IDENTITY")
    k_ssn = KYCProvider(code="ssn_ein", name="SSN/EIN", country_code="US", verification_type="BUSINESS")

    db.session.add_all([k_aadhaar, k_ssn])
    db.session.commit()

    return {"countries": [c_in, c_us, c_br]}


def test_tax_engine_us_sales_tax(app, test_store, test_product, expansion_setup):
    """Test US sales tax calculator."""
    calculator = get_tax_calculator(test_store.store_id, "US")

    items = [{"product_id": test_product.product_id, "quantity": 2, "selling_price": 50.00, "discount": 0}]

    result = calculator.calculate_tax(items)
    print(f"Tax Result: base={result.taxable_amount}, tax={result.tax_amount}, breakdown={result.breakdown}")

    assert result.taxable_amount == Decimal("100.00")
    assert result.tax_amount == Decimal("8.50")
    assert result.breakdown["STATE_TAX"] == Decimal("2.50")
    assert result.breakdown["LOCAL_TAX"] == Decimal("6.00")


def test_kyc_adapters(app, test_store, test_owner, expansion_setup):
    """Test KYC adapters."""
    aadhaar = get_kyc_adapter("aadhaar", test_store.store_id)

    with pytest.raises(ValueError, match="Invalid Aadhaar format"):
        aadhaar.verify_identity(test_owner.user_id, "123")

    res = aadhaar.verify_identity(test_owner.user_id, "123456789012")
    assert res["status"] == "VERIFIED"


def test_einvoicing_brazil(app, test_store, expansion_setup):
    """Test Brazil NF-e e-invoicing generation."""
    txn = Transaction(
        transaction_id=uuid.uuid4(),
        store_id=test_store.store_id,
        total_amount=150.00,
        payment_mode="CARD",
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(txn)
    db.session.commit()

    nfe = get_einvoice_adapter("BR", test_store.store_id)
    payload = nfe.generate_invoice(txn)

    assert payload["format"] == "NF_E"
    assert "xml_payload" in payload
    assert "chave_acesso" in payload

    res = nfe.submit_invoice(payload)
    assert res["status"] == "ACCEPTED"
    assert "protocol" in res
