import pytest
import uuid
from datetime import datetime
from unittest.mock import patch
from app.models import Transaction
from app.models.expansion_models import EInvoice
from app.einvoicing.engine import register_einvoice_adapter, BaseEInvoiceAdapter, get_einvoice_adapter

@pytest.fixture
def test_transaction(app, test_store):
    from app import db
    txn = Transaction(
        store_id=test_store.store_id,
        transaction_id=uuid.uuid4(),
        total_amount=150.0,
        payment_mode="CASH",
        created_at=datetime.utcnow()
    )
    db.session.add(txn)
    db.session.commit()
    return txn

def test_einvoice_get_adapter_not_found():
    with pytest.raises(ValueError, match="No e-invoice adapter registered"):
        get_einvoice_adapter("XX", 1)

def test_einvoice_adapters_generation(app, test_transaction):
    # Test Brazil NF-e
    br_adapter = get_einvoice_adapter("BR", 1)
    br_payload = br_adapter.generate_invoice(test_transaction)
    assert br_payload["format"] == "NF_E"
    assert "<NFe>" in br_payload["xml_payload"]
    assert "chave_acesso" in br_payload
    
    # Test Mexico CFDI
    mx_adapter = get_einvoice_adapter("MX", 1)
    mx_payload = mx_adapter.generate_invoice(test_transaction)
    assert mx_payload["format"] == "CFDI"
    assert "<cfdi:Comprobante Total='150.00' Version='4.0'>" in mx_payload["xml_payload"]
    assert "uuid" in mx_payload
    
    # Test Indonesia e-Faktur
    id_adapter = get_einvoice_adapter("ID", 1)
    id_payload = id_adapter.generate_invoice(test_transaction)
    assert id_payload["format"] == "E_FAKTUR"
    assert "DPP" in id_payload["xml_payload"]

def test_einvoice_adapters_submission():
    # Test Brazil Submission
    br_adapter = get_einvoice_adapter("BR", 1)
    br_resp = br_adapter.submit_invoice({})
    assert br_resp["status"] == "ACCEPTED"
    assert "protocol" in br_resp

    # Test Mexico Submission
    mx_adapter = get_einvoice_adapter("MX", 1)
    mx_resp = mx_adapter.submit_invoice({})
    assert mx_resp["status"] == "ACCEPTED"
    assert "sat_seal" in mx_resp
    
    # Test Indonesia Submission
    id_adapter = get_einvoice_adapter("ID", 1)
    id_resp = id_adapter.submit_invoice({})
    assert id_resp["status"] == "ACCEPTED"
    assert "faktur_pajak_no" in id_resp

def test_base_einvoice_adapter_not_implemented():
    adapter = BaseEInvoiceAdapter(store_id=1)
    with pytest.raises(NotImplementedError):
        adapter.generate_invoice(None)
    with pytest.raises(NotImplementedError):
        adapter.submit_invoice({})

def test_generate_einvoice_route_success(client, owner_headers, test_transaction):
    from app import db
    
    response = client.post(
        '/api/v1/einvoice/generate',
        json={"transaction_id": str(test_transaction.transaction_id), "country_code": "BR"},
        headers=owner_headers
    )
    
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['status'] == 'ACCEPTED'
    assert 'invoice_id' in data
    assert 'qr_code_url' in data

    einvoice = db.session.query(EInvoice).first()
    assert einvoice is not None
    assert einvoice.country_code == 'BR'
    assert einvoice.status == 'ACCEPTED'

def test_generate_einvoice_route_existing(client, owner_headers, test_transaction):
    from app import db
    
    # First submit successfully
    client.post(
        '/api/v1/einvoice/generate',
        json={"transaction_id": str(test_transaction.transaction_id), "country_code": "BR"},
        headers=owner_headers
    )
    
    # Try again, should return existing
    response2 = client.post(
        '/api/v1/einvoice/generate',
        json={"transaction_id": str(test_transaction.transaction_id), "country_code": "BR"},
        headers=owner_headers
    )
    
    assert response2.status_code == 200
    data2 = response2.get_json()['data']
    
    # Existing one doesn't return invoice_id, it returns invoice_number in the early exit block
    assert "invoice_number" in data2

def test_generate_einvoice_route_missing_fields(client, owner_headers):
    response = client.post(
        '/api/v1/einvoice/generate',
        json={},
        headers=owner_headers
    )
    assert response.status_code == 400
    assert "VALIDATION_ERROR" in response.get_json()["error"]["code"]

def test_generate_einvoice_route_txn_not_found(client, owner_headers):
    response = client.post(
        '/api/v1/einvoice/generate',
        json={"transaction_id": str(uuid.uuid4()), "country_code": "ID"},
        headers=owner_headers
    )
    assert response.status_code == 404
    assert "NOT_FOUND" in response.get_json()["error"]["code"]

def test_generate_einvoice_route_invalid_country(client, owner_headers, test_transaction):
    response = client.post(
        '/api/v1/einvoice/generate',
        json={"transaction_id": str(test_transaction.transaction_id), "country_code": "INVALID_COUNTRY"},
        headers=owner_headers
    )
    assert response.status_code == 400
    assert "ADAPTER_ERROR" in response.get_json()["error"]["code"]

def test_generate_einvoice_route_exception(client, owner_headers, test_transaction):
    with patch('app.einvoicing.routes.get_einvoice_adapter', side_effect=Exception("Server failure")):
        response = client.post(
            '/api/v1/einvoice/generate',
            json={"transaction_id": str(test_transaction.transaction_id), "country_code": "BR"},
            headers=owner_headers
        )
        assert response.status_code == 500
        assert "SERVER_ERROR" in response.get_json()["error"]["code"]

def test_get_einvoice_status_success(client, owner_headers, test_transaction):
    from app import db
    einvoice = EInvoice(
        transaction_id=test_transaction.transaction_id,
        store_id=1,
        country_code="BR",
        invoice_format="NF_E",
        xml_payload="<xml>",
        invoice_number="ABCDEFG",
        status="ACCEPTED",
        authority_ref="REF123"
    )
    db.session.add(einvoice)
    db.session.commit()
    
    response = client.get(f'/api/v1/einvoice/status/{einvoice.id}', headers=owner_headers)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "ACCEPTED"
    assert data["invoice_number"] == "ABCDEFG"
    
def test_get_einvoice_status_not_found(client, owner_headers):
    response = client.get('/api/v1/einvoice/status/9999', headers=owner_headers)
    assert response.status_code == 404
    assert 'NOT_FOUND' in response.get_json()['error']['code']
