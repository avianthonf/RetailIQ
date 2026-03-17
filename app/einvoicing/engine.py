"""RetailIQ E-Invoicing Engine — country adapter factory."""

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BaseEInvoiceAdapter:
    def __init__(self, country_code: str, store_id: int):
        self.country_code = country_code
        self.store_id = store_id

    def generate_invoice(self, txn) -> dict:
        raise NotImplementedError

    def submit_invoice(self, payload: dict) -> dict:
        raise NotImplementedError


class IndiaEInvoiceAdapter(BaseEInvoiceAdapter):
    """India GST e-invoice (IRP) — stub implementation."""

    def generate_invoice(self, txn) -> dict:
        return {
            "format": "IRP_JSON",
            "uuid": str(uuid.uuid4()),
            "transaction_id": str(txn.transaction_id),
            "store_id": self.store_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def submit_invoice(self, payload: dict) -> dict:
        return {
            "status": "SUBMITTED",
            "protocol": f"IRN{uuid.uuid4().hex[:16].upper()}",
            "qr_code_url": None,
        }


class BrazilEInvoiceAdapter(BaseEInvoiceAdapter):
    def generate_invoice(self, txn) -> dict:
        return {
            "format": "NF_E",
            "uuid": str(uuid.uuid4()),
            "chave_acesso": f"312308{uuid.uuid4().hex[:38].upper()}",
            "xml_payload": "<NFe>...</NFe>",
        }

    def submit_invoice(self, payload: dict) -> dict:
        return {"status": "ACCEPTED", "protocol": str(uuid.uuid4())}


class MexicoEInvoiceAdapter(BaseEInvoiceAdapter):
    def generate_invoice(self, txn) -> dict:
        return {
            "format": "CFDI",
            "uuid": str(uuid.uuid4()),
            "xml_payload": "<cfdi:Comprobante Total='150.00' Version='4.0'>...</cfdi:Comprobante>",
        }

    def submit_invoice(self, payload: dict) -> dict:
        return {"status": "ACCEPTED", "protocol": str(uuid.uuid4()), "sat_seal": "MOCK_SAT_SEAL"}


class IndonesiaEInvoiceAdapter(BaseEInvoiceAdapter):
    def generate_invoice(self, txn) -> dict:
        return {"format": "E_FAKTUR", "uuid": str(uuid.uuid4()), "xml_payload": "DPP: 150000"}

    def submit_invoice(self, payload: dict) -> dict:
        return {"status": "ACCEPTED", "protocol": str(uuid.uuid4()), "faktur_pajak_no": "MOCK_FAKTUR_NO"}


class GenericEInvoiceAdapter(BaseEInvoiceAdapter):
    """Generic fallback adapter."""

    def generate_invoice(self, txn) -> dict:
        return {"format": "STANDARD", "uuid": str(uuid.uuid4()), "transaction_id": str(txn.transaction_id)}

    def submit_invoice(self, payload: dict) -> dict:
        return {"status": "ACCEPTED", "protocol": str(uuid.uuid4())}


_ADAPTER_MAP = {
    "IN": IndiaEInvoiceAdapter,
    "BR": BrazilEInvoiceAdapter,
    "MX": MexicoEInvoiceAdapter,
    "ID": IndonesiaEInvoiceAdapter,
}


def get_einvoice_adapter(country_code: str, store_id: int) -> BaseEInvoiceAdapter:
    if country_code.upper() not in ("IN", "BR", "MX", "ID"):
        raise ValueError(f"No e-invoice adapter registered for country: {country_code}")
    cls = _ADAPTER_MAP.get(country_code.upper(), GenericEInvoiceAdapter)
    return cls(country_code, store_id)
