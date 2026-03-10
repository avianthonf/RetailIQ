from decimal import Decimal
import uuid
import pytest
from app import db
from app.models import Product, Store, User
from app.models.expansion_models import Country, CountryTaxConfig, StoreTaxRegistration, TaxTransaction
from app.tax_engine.engine import IndiaGSTCalculator, USSalesTaxCalculator, GenericVATCalculator, get_tax_calculator, BaseTaxCalculator

@pytest.fixture
def tax_setup(app, test_store):
    # Setup countries
    countries = [
        Country(code="IN", name="India", default_currency="INR", default_locale="en-IN", timezone="Asia/Kolkata", tax_system="GST"),
        Country(code="US", name="United States", default_currency="USD", default_locale="en-US", timezone="UTC", tax_system="SALES_TAX"),
        Country(code="UK", name="United Kingdom", default_currency="GBP", default_locale="en-GB", timezone="Europe/London", tax_system="VAT")
    ]
    for c in countries:
        if not db.session.get(Country, c.code):
            db.session.add(c)
    db.session.commit()

    # Setup tax configs
    configs = [
        CountryTaxConfig(country_code="IN", tax_type="GST", standard_rate=18.0),
        CountryTaxConfig(country_code="US", tax_type="SALES_TAX", standard_rate=5.0, has_subnational_tax=True, subnational_config={"NY": 4.0}),
        CountryTaxConfig(country_code="UK", tax_type="VAT", standard_rate=20.0)
    ]
    for cfg in configs:
        db.session.add(cfg)
    db.session.commit()

    # Setup registrations
    regs = [
        StoreTaxRegistration(store_id=test_store.store_id, country_code="IN", tax_id="GSTIN123", is_tax_enabled=True),
        StoreTaxRegistration(store_id=test_store.store_id, country_code="US", tax_id="EIN123", is_tax_enabled=True, state_province="NY")
    ]
    for r in regs:
        db.session.add(r)
    db.session.commit()
    return {"countries": countries, "configs": configs, "regs": regs}

def test_get_tax_config_success(client, owner_headers, tax_setup):
    resp = client.get("/api/v1/tax/config?country_code=IN", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["tax_id"] == "GSTIN123"

def test_get_tax_config_not_found(client, owner_headers, tax_setup):
    resp = client.get("/api/v1/tax/config?country_code=UK", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["is_tax_enabled"] is False

def test_calculate_tax_india(client, owner_headers, tax_setup):
    prod = Product(store_id=1, name="P1", sku_code="P1", selling_price=1000.0, cost_price=800.0, current_stock=10)
    db.session.add(prod)
    db.session.commit()
    
    payload = {
        "country_code": "IN",
        "items": [{"product_id": prod.product_id, "quantity": 1, "selling_price": 1180.0}]
    }
    resp = client.post("/api/v1/tax/calculate", json=payload, headers=owner_headers)
    assert resp.status_code == 200
    assert abs(resp.json["data"]["tax_amount"] - 180.0) < 0.1

def test_calculate_tax_us(client, owner_headers, tax_setup):
    # US is tax exclusive in our calculator
    payload = {
        "country_code": "US",
        "items": [{"product_id": 1, "quantity": 1, "selling_price": 1000.0}]
    }
    resp = client.post("/api/v1/tax/calculate", json=payload, headers=owner_headers)
    assert resp.status_code == 200
    # 5% standard + 4% NY = 9%
    assert abs(resp.json["data"]["tax_amount"] - 90.0) < 0.1

def test_calculate_tax_errors(client, owner_headers, tax_setup, monkeypatch):
    # Bad request (Exception in request.json)
    resp = client.post("/api/v1/tax/calculate", data="invalid json", headers=owner_headers)
    assert resp.status_code == 422

    # Calculation error
    from app.tax_engine import routes
    def mock_error(*args, **kwargs):
        raise Exception("Calc error")
    # Mock IndiaGSTCalculator.calculate_tax instead of get_tax_calculator to trigger the try-except in route
    monkeypatch.setattr(IndiaGSTCalculator, "calculate_tax", mock_error)
    payload = {"country_code": "IN", "items": []}
    resp = client.post("/api/v1/tax/calculate", json=payload, headers=owner_headers)
    assert resp.status_code == 500

def test_tax_summary_success(client, owner_headers, tax_setup):
    # Seed a TaxTransaction
    txn = TaxTransaction(
        transaction_id=uuid.uuid4(),
        store_id=1,
        country_code="IN",
        tax_type="GST",
        period="2026-03",
        taxable_amount=1000.0,
        tax_amount=180.0
    )
    # Need a real transaction_id from a Transaction object
    from app.models import Transaction
    t = Transaction(transaction_id=txn.transaction_id, store_id=1, total_amount=1180.0)
    db.session.add(t)
    db.session.add(txn)
    db.session.commit()
    
    resp = client.get("/api/v1/tax/filing-summary?period=2026-03&country_code=IN", headers=owner_headers)
    assert resp.status_code == 200
    assert resp.json["data"]["total_taxable"] == 1000.0
    assert resp.json["data"]["invoice_count"] == 1

def test_tax_summary_missing_period(client, owner_headers):
    resp = client.get("/api/v1/tax/filing-summary", headers=owner_headers)
    assert resp.status_code == 422

def test_base_calculator_abstract(tax_setup):
    calc = BaseTaxCalculator(1, "IN")
    with pytest.raises(NotImplementedError):
        calc.calculate_tax([])

def test_generic_vat_calculator_fallback(client, owner_headers, tax_setup):
    # UK should fall back to GenericVATCalculator if not registered (wait, UK is registered as config but no store reg)
    # Registration is missing for UK in tax_setup
    payload = {
        "country_code": "UK",
        "items": [{"product_id": 1, "quantity": 1, "selling_price": 120.0}]
    }
    # First, test unregistered store (should return 0 tax)
    calc = get_tax_calculator(1, "UK")
    assert isinstance(calc, GenericVATCalculator)
    res = calc.calculate_tax(payload["items"])
    assert res.tax_amount == 0
    
    # Now register store for UK VAT
    reg = StoreTaxRegistration(store_id=1, country_code="UK", tax_id="VAT123", is_tax_enabled=True)
    db.session.add(reg)
    db.session.commit()
    
    # Create product
    prod = Product(store_id=1, name="P2", sku_code="P2", selling_price=100.0, cost_price=80.0, current_stock=10)
    db.session.add(prod)
    db.session.commit()
    
    payload["items"] = [{"product_id": prod.product_id, "quantity": 1, "selling_price": 120.0}]
    resp = client.post("/api/v1/tax/calculate", json=payload, headers=owner_headers)
    assert resp.status_code == 200
    # 20% VAT on 120 = 20 tax (since it's tax inclusive like GST in this calculator)
    assert abs(resp.json["data"]["tax_amount"] - 20.0) < 0.1

def test_india_calculator_disabled(tax_setup):
    # Disable tax for IN
    reg = db.session.query(StoreTaxRegistration).filter_by(store_id=1, country_code="IN").first()
    reg.is_tax_enabled = False
    db.session.commit()
    
    calc = IndiaGSTCalculator(1, "IN")
    res = calc.calculate_tax([{"product_id": 1}])
    assert res.tax_amount == 0

def test_india_calculator_hsn_rate(tax_setup):
    from app.models import HSNMaster
    hsn = HSNMaster(hsn_code="HSN001", description="D", default_gst_rate=12)
    db.session.add(hsn)
    db.session.commit()
    
    prod = Product(store_id=1, name="PHSN", sku_code="PHSN", hsn_code="HSN001", selling_price=1120.0)
    db.session.add(prod)
    db.session.commit()
    
    calc = IndiaGSTCalculator(1, "IN")
    res = calc.calculate_tax([{"product_id": prod.product_id, "quantity": 1, "selling_price": 1120.0}])
    # 12% on 1120 = 120 tax
    assert abs(res.tax_amount - Decimal("120.0")) < Decimal("0.1")

def test_india_calculator_exempt(tax_setup):
    prod = Product(store_id=1, name="PEX", sku_code="PEX", gst_category="EXEMPT", selling_price=100.0)
    db.session.add(prod)
    db.session.commit()
    calc = IndiaGSTCalculator(1, "IN")
    res = calc.calculate_tax([{"product_id": prod.product_id, "quantity": 1, "selling_price": 100.0}])
    assert res.tax_amount == 0

def test_us_calculator_disabled(tax_setup):
    reg = db.session.query(StoreTaxRegistration).filter_by(store_id=1, country_code="US").first()
    reg.is_tax_enabled = False
    db.session.commit()
    calc = USSalesTaxCalculator(1, "US")
    res = calc.calculate_tax([{"product_id": 1}])
    assert res.tax_amount == 0

def test_generic_vat_calculator_no_product(tax_setup):
    calc = GenericVATCalculator(1, "UK")
    # UK config exists, reg doesn't yet or is disabled?
    # Actually calc.calculate_tax(items) loops through items and gets product
    res = calc.calculate_tax([{"product_id": 99999, "quantity": 1, "selling_price": 100.0}])
    assert res.tax_amount == 0
