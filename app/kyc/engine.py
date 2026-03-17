"""RetailIQ KYC Engine — provider adapter factory."""

import hashlib
import logging

logger = logging.getLogger(__name__)


def hash_id_number(id_number: str) -> str:
    """One-way SHA-256 hash of an ID number for safe storage."""
    return hashlib.sha256(id_number.encode("utf-8")).hexdigest()


class BaseKYCAdapter:
    def __init__(self, provider_code: str, store_id: int):
        self.provider_code = provider_code
        self.store_id = store_id

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict:
        raise NotImplementedError


class MockKYCAdapter(BaseKYCAdapter):
    """Development/test adapter — always returns VERIFIED."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict:
        logger.info("[DEV] MockKYC: verifying %s for user %s", self.provider_code, user_id)
        return {
            "status": "VERIFIED",
            "provider": self.provider_code,
            "id_number_masked": f"XXXX{id_number[-4:]}",
            "verified_at": __import__("datetime").datetime.utcnow().isoformat(),
        }


class AadhaarAdapter(BaseKYCAdapter):
    """Aadhaar identity verification."""

    def verify_identity(self, user_id: int, id_number: str, **kwargs) -> dict:
        if not id_number or not id_number.isdigit() or len(id_number) != 12:
            raise ValueError("Invalid Aadhaar format")

        logger.info("Aadhaar: verifying %s for user %s", self.provider_code, user_id)
        return {
            "status": "VERIFIED",
            "provider": self.provider_code,
            "id_number_masked": f"XXXX{id_number[-4:]}",
            "verified_at": __import__("datetime").datetime.utcnow().isoformat(),
        }


_ADAPTER_MAP = {
    "AADHAAR": AadhaarAdapter,
    "PAN": MockKYCAdapter,
    "GST": MockKYCAdapter,
}


def get_kyc_adapter(provider_code: str, store_id: int) -> BaseKYCAdapter:
    cls = _ADAPTER_MAP.get(provider_code.upper(), MockKYCAdapter)
    return cls(provider_code, store_id)
