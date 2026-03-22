"""RetailIQ E-Invoicing Engine — country adapter factory."""

import base64
import html
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BaseEInvoiceAdapter:
    invoice_format = "STANDARD"
    invoice_prefix = "INV"
    submission_status = "ACCEPTED"
    gateway_name = "RetailIQ Local Gateway"

    def __init__(self, country_code: str, store_id: int):
        self.country_code = country_code
        self.store_id = store_id

    def _stable_token(self, txn) -> uuid.UUID:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"retailiq:einvoice:{self.country_code.upper()}:{self.store_id}:{txn.transaction_id}",
        )

    def _invoice_number(self, txn, token: uuid.UUID) -> str:
        return f"{self.invoice_prefix}-{token.hex[:16].upper()}"

    def _base_generate_payload(self, txn) -> dict:
        token = self._stable_token(txn)
        invoice_number = self._invoice_number(txn, token)
        total_amount = getattr(txn, "total_amount", 0) or 0

        payload = {
            "format": self.invoice_format,
            "uuid": str(token),
            "transaction_id": str(txn.transaction_id),
            "store_id": self.store_id,
            "country_code": self.country_code.upper(),
            "invoice_number": invoice_number,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_amount": float(total_amount),
        }
        payload.update(self._generation_extras(txn, token, invoice_number))
        return payload

    def _generation_extras(self, txn, token: uuid.UUID, invoice_number: str) -> dict:
        return {}

    def _submission_extras(self, payload: dict, authority_ref: str) -> dict:
        return {}

    def _qr_code_url(self, payload: dict, authority_ref: str) -> str:
        label = html.escape(f"{self.gateway_name} | {self.country_code.upper()} | {authority_ref}")
        invoice_number = html.escape(str(payload.get("invoice_number", "")))
        transaction_id = html.escape(str(payload.get("transaction_id", "")))
        status = html.escape(self.submission_status)
        svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="240" viewBox="0 0 480 240">
  <rect width="100%" height="100%" fill="#0f172a" rx="18" ry="18" />
  <text x="24" y="48" fill="#f8fafc" font-size="24" font-family="Arial, sans-serif">RetailIQ E-Invoice</text>
  <text x="24" y="88" fill="#cbd5e1" font-size="15" font-family="Arial, sans-serif">{label}</text>
  <text x="24" y="122" fill="#cbd5e1" font-size="14" font-family="Arial, sans-serif">Invoice: {invoice_number}</text>
  <text x="24" y="148" fill="#cbd5e1" font-size="14" font-family="Arial, sans-serif">Txn: {transaction_id}</text>
  <text x="24" y="174" fill="#cbd5e1" font-size="14" font-family="Arial, sans-serif">Status: {status}</text>
  <rect x="336" y="48" width="120" height="120" fill="#1e293b" stroke="#38bdf8" stroke-width="4" rx="12" ry="12" />
  <text x="396" y="115" fill="#38bdf8" font-size="42" text-anchor="middle" font-family="Arial, sans-serif">QR</text>
</svg>
""".strip()
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    def build_qr_code_url(self, payload: dict, authority_ref: str) -> str:
        return self._qr_code_url(payload, authority_ref)

    def generate_invoice(self, txn) -> dict:
        return self._base_generate_payload(txn)

    def submit_invoice(self, payload: dict) -> dict:
        authority_ref = (
            payload.get("authority_ref")
            or payload.get("protocol")
            or payload.get("sat_seal")
            or payload.get("faktur_pajak_no")
            or payload.get("chave_acesso")
            or payload.get("irn")
            or payload.get("invoice_number")
            or payload.get("uuid")
        )
        response = {
            "status": self.submission_status,
            "authority_ref": authority_ref,
            "qr_code_url": self._qr_code_url(payload, str(authority_ref)),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "submission_mode": "LOCAL_GATEWAY",
            "gateway_name": self.gateway_name,
        }
        response.update(self._submission_extras(payload, str(authority_ref)))
        return response


class IndiaEInvoiceAdapter(BaseEInvoiceAdapter):
    invoice_format = "IRP_JSON"
    invoice_prefix = "IRN"
    gateway_name = "India IRP Local Gateway"

    def _generation_extras(self, txn, token: uuid.UUID, invoice_number: str) -> dict:
        return {
            "irn": invoice_number,
            "acknowledgement_number": f"ACK-{token.hex[:10].upper()}",
            "digital_signature": f"SIG-{token.hex[:24].upper()}",
        }

    def _submission_extras(self, payload: dict, authority_ref: str) -> dict:
        return {
            "protocol": authority_ref,
        }


class BrazilEInvoiceAdapter(BaseEInvoiceAdapter):
    invoice_format = "NF_E"
    invoice_prefix = "NFE"
    gateway_name = "Brazil NF-e Local Gateway"

    def _generation_extras(self, txn, token: uuid.UUID, invoice_number: str) -> dict:
        access_key = f"31{token.hex[:42].upper()}"
        return {
            "chave_acesso": access_key,
            "xml_payload": f"<NFe><infNFe Id='{access_key}'>...</infNFe></NFe>",
        }

    def _submission_extras(self, payload: dict, authority_ref: str) -> dict:
        return {"protocol": authority_ref}


class MexicoEInvoiceAdapter(BaseEInvoiceAdapter):
    invoice_format = "CFDI"
    invoice_prefix = "CFDI"
    gateway_name = "Mexico CFDI Local Gateway"

    def _generation_extras(self, txn, token: uuid.UUID, invoice_number: str) -> dict:
        return {
            "xml_payload": (
                "<cfdi:Comprobante Total='"
                f"{float(getattr(txn, 'total_amount', 0) or 0):.2f}' Version='4.0'>...</cfdi:Comprobante>"
            ),
        }

    def _submission_extras(self, payload: dict, authority_ref: str) -> dict:
        return {
            "protocol": authority_ref,
            "sat_seal": f"SAT-{authority_ref[-12:]}",
        }


class IndonesiaEInvoiceAdapter(BaseEInvoiceAdapter):
    invoice_format = "E_FAKTUR"
    invoice_prefix = "FKTR"
    gateway_name = "Indonesia e-Faktur Local Gateway"

    def _generation_extras(self, txn, token: uuid.UUID, invoice_number: str) -> dict:
        total_amount = float(getattr(txn, "total_amount", 0) or 0)
        return {"xml_payload": f"<eFaktur><DPP>{total_amount:.2f}</DPP></eFaktur>"}

    def _submission_extras(self, payload: dict, authority_ref: str) -> dict:
        return {
            "protocol": authority_ref,
            "faktur_pajak_no": authority_ref,
        }


class GenericEInvoiceAdapter(BaseEInvoiceAdapter):
    """Generic fallback adapter."""


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
