"""
Local Payment Adapters

Registry for country-specific payment methods.
"""

from typing import Any, Dict

from .. import db
from ..models.expansion_models import PaymentProvider, PaymentRecord, StorePaymentMethod

_payment_adapters = {}


def register_payment_adapter(code: str):
    def decorator(cls):
        _payment_adapters[code] = cls
        return cls
    return decorator


class BasePaymentAdapter:
    def __init__(self, store_id: int):
        self.store_id = store_id

    def create_payment_intent(self, amount: float, currency: str, txn_id: str, **kwargs) -> dict[str, Any]:
        """Initialize a payment with the provider."""
        raise NotImplementedError

    def verify_payment(self, provider_ref: str, **kwargs) -> bool:
        """Verify payment status via webhook or direct API call."""
        raise NotImplementedError


@register_payment_adapter("razorpay")
class RazorpayAdapter(BasePaymentAdapter):
    """India - Razorpay (UPI, Cards, NetBanking)."""

    def create_payment_intent(self, amount: float, currency: str, txn_id: str, **kwargs) -> dict[str, Any]:
        # Mock Razorpay Order creation
        return {
            "provider": "razorpay",
            "order_id": f"order_{txn_id}",
            "amount": amount * 100,  # Razorpay expects paise
            "currency": currency,
            "key_id": "rzp_test_12345"
        }

    def verify_payment(self, provider_ref: str, **kwargs) -> bool:
        # Mock verification
        return True


@register_payment_adapter("stripe")
class StripeAdapter(BasePaymentAdapter):
    """US/UK - Stripe."""

    def create_payment_intent(self, amount: float, currency: str, txn_id: str, **kwargs) -> dict[str, Any]:
        return {
            "provider": "stripe",
            "client_secret": f"pi_{txn_id}_secret_abc123",
            "amount": int(amount * 100) if currency in ("USD", "EUR", "GBP") else amount,
            "currency": currency,
        }

    def verify_payment(self, provider_ref: str, **kwargs) -> bool:
        return True


@register_payment_adapter("pix")
class PixAdapter(BasePaymentAdapter):
    """Brazil - PIX."""

    def create_payment_intent(self, amount: float, currency: str, txn_id: str, **kwargs) -> dict[str, Any]:
        return {
            "provider": "pix",
            "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==",
            "qr_code_string": f"00020126580014br.gov.bcb.pix0136{txn_id}",
            "amount": amount,
            "currency": "BRL"
        }

    def verify_payment(self, provider_ref: str, **kwargs) -> bool:
        return True


@register_payment_adapter("mpesa")
class MPesaAdapter(BasePaymentAdapter):
    """Kenya - M-Pesa."""

    def create_payment_intent(self, amount: float, currency: str, txn_id: str, **kwargs) -> dict[str, Any]:
        phone = kwargs.get("phone_number")
        if not phone:
            raise ValueError("Phone number required for M-Pesa STK push")
        return {
            "provider": "mpesa",
            "checkout_request_id": f"ws_{txn_id}",
            "message": f"STK Push sent to {phone}"
        }

    def verify_payment(self, provider_ref: str, **kwargs) -> bool:
        return True


def get_payment_adapter(provider_code: str, store_id: int) -> BasePaymentAdapter:
    adapter_cls = _payment_adapters.get(provider_code)
    if not adapter_cls:
        raise ValueError(f"No payment adapter registered for {provider_code}")
    return adapter_cls(store_id)
