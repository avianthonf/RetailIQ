"""
Country-Specific KYC Adapters
"""

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict

from .. import db
from ..models.expansion_models import KYCProvider, KYCRecord

_kyc_adapters = {}


def register_kyc_adapter(code: str):
    def decorator(cls):
        _kyc_adapters[code] = cls
        return cls
    return decorator


class BaseKYCAdapter:
    def __init__(self, store_id: int):
        self.store_id = store_id

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict[str, Any]:
        """Perform KYC verification."""
        raise NotImplementedError


@register_kyc_adapter("aadhaar")
class AadhaarAdapter(BaseKYCAdapter):
    """India - UIDAI Aadhaar eKYC via OTP."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict[str, Any]:
        # Mock Aadhaar eKYC
        if len(id_number) != 12 or not id_number.isdigit():
            raise ValueError("Invalid Aadhaar format; must be 12 digits.")

        return {
            "status": "VERIFIED",
            "name_match_score": 0.95,
            "address_verified": True
        }


@register_kyc_adapter("ssn_ein")
class USEinAdapter(BaseKYCAdapter):
    """US - SSN/EIN verification against TIN matching system."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict[str, Any]:
        # Mock TIN check
        return {
            "status": "VERIFIED",
            "tin_type": "EIN",
            "match_status": "EXACT_MATCH"
        }


@register_kyc_adapter("bvn")
class BVNAdapter(BaseKYCAdapter):
    """Nigeria - Bank Verification Number."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict[str, Any]:
        if len(id_number) != 11:
            raise ValueError("BVN must be 11 digits.")
        return {
            "status": "VERIFIED",
            "bvn": "***********",
            "kyc_tier": "Tier3"
        }


@register_kyc_adapter("cnpj")
class CNPJAdapter(BaseKYCAdapter):
    """Brazil - CNPJ via Receita Federal."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict[str, Any]:
        return {
            "status": "VERIFIED",
            "company_status": "ACTIVE",
            "tax_regime": "Simples Nacional"
        }


def get_kyc_adapter(provider_code: str, store_id: int) -> BaseKYCAdapter:
    adapter_cls = _kyc_adapters.get(provider_code)
    if not adapter_cls:
        raise ValueError(f"No KYC adapter registered for {provider_code}")
    return adapter_cls(store_id)


def hash_id_number(id_number: str) -> str:
    """Hash sensitive PII like SSN, Aadhaar before storing in DB if required."""
    return hashlib.sha256(id_number.encode("utf-8")).hexdigest()
