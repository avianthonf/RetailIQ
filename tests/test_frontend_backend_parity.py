from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app import db
from app.auth.utils import generate_access_token
from app.models import (
    APIUsageRecord,
    Customer,
    DataSource,
    Developer,
    FinancialAccount,
    GSTFilingPeriod,
    HSNMaster,
    LoyaltyProgram,
    MarketAlert,
    MarketSignal,
    TreasuryConfig,
    TreasuryTransaction,
    User,
    WebhookEvent,
    WhatsAppConfig,
)
from app.models.finance_models import LedgerEntry


def _chain_headers(user_id, store_id, group_id):
    token = generate_access_token(user_id, store_id, "owner", chain_group_id=str(group_id), chain_role="CHAIN_OWNER")
    return {"Authorization": f"Bearer {token}"}


def test_developer_extended_endpoints(client, owner_headers, test_owner):
    developer = Developer(name="Dev Owner", email="owner-dev@example.com", user_id=test_owner.user_id)
    db.session.add(developer)
    db.session.commit()

    created = client.post(
        "/api/v1/developer/apps",
        headers=owner_headers,
        json={
            "name": "Parity App",
            "app_type": "WEB",
            "redirect_uris": ["https://example.com/callback"],
            "scopes": ["read:inventory"],
        },
    )
    assert created.status_code == 201
    app_data = created.get_json()["data"]
    app_id = str(app_data["id"])

    updated = client.patch(f"/api/v1/developer/apps/{app_id}", headers=owner_headers, json={"description": "Updated"})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["description"] == "Updated"

    regenerated = client.post(f"/api/v1/developer/apps/{app_id}/regenerate-secret", headers=owner_headers)
    assert regenerated.status_code == 200
    assert regenerated.get_json()["data"]["client_secret"]

    webhook = client.post(
        "/api/v1/developer/webhooks",
        headers=owner_headers,
        json={"url": "https://example.com/hook", "events": ["transaction.created"], "app_id": app_id},
    )
    assert webhook.status_code == 201

    usage = APIUsageRecord(
        app_id=int(app_id),
        endpoint="/api/v2/inventory",
        method="GET",
        minute_bucket=datetime.now(timezone.utc).replace(second=0, microsecond=0),
        request_count=12,
        error_count=2,
        avg_latency_ms=120,
    )
    event = WebhookEvent(
        app_id=int(app_id),
        event_type="transaction.created",
        payload={"ok": True},
        delivery_url="https://example.com/hook",
        status="FAILED",
    )
    db.session.add_all([usage, event])
    db.session.commit()

    stats = client.get("/api/v1/developer/usage", headers=owner_headers)
    assert stats.status_code == 200
    assert stats.get_json()["data"]["total_requests"] == 12

    limits = client.get("/api/v1/developer/rate-limits", headers=owner_headers)
    assert limits.status_code == 200
    assert len(limits.get_json()["data"]) == 1

    logs = client.get("/api/v1/developer/logs", headers=owner_headers)
    assert logs.status_code == 200
    assert logs.get_json()["data"]["total"] >= 1

    with patch("app.tasks.webhook_tasks.deliver_webhook.delay") as mock_delay:
        tested = client.post(f"/api/v1/developer/webhooks/{app_id}/test", headers=owner_headers)
        assert tested.status_code == 200
        assert mock_delay.called


def test_market_parity_endpoints(client, owner_headers, test_store, test_product):
    source = DataSource(name="RivalMart", source_type="competitor")
    db.session.add(source)
    db.session.flush()
    db.session.add_all(
        [
            MarketSignal(
                signal_type="PRICE",
                source_id=source.id,
                category_id=test_product.category_id,
                region_code="KA",
                value=110,
            ),
            MarketSignal(
                signal_type="PRICE",
                source_id=source.id,
                category_id=test_product.category_id,
                region_code="KA",
                value=115,
            ),
            MarketAlert(merchant_id=test_store.store_id, alert_type="PRICE_DROP", severity="HIGH", message="Price gap"),
        ]
    )
    db.session.commit()

    competitors = client.get("/api/v1/market/competitors", headers=owner_headers)
    assert competitors.status_code == 200
    assert competitors.get_json()["data"][0]["name"] == "RivalMart"

    forecasts = client.get("/api/v1/market/forecasts", headers=owner_headers)
    assert forecasts.status_code == 200
    assert forecasts.get_json()["data"][0]["product_id"] == str(test_product.product_id)

    generated = client.post(
        "/api/v1/market/forecasts/generate",
        headers=owner_headers,
        json={"product_id": test_product.product_id, "forecast_period": "next_30_days"},
    )
    assert generated.status_code == 200
    assert generated.get_json()["data"]["product_id"] == str(test_product.product_id)

    recommendations = client.get("/api/v1/market/recommendations", headers=owner_headers)
    assert recommendations.status_code == 200
    assert len(recommendations.get_json()["data"]) >= 1


def test_loyalty_parity_endpoints(client, owner_headers, test_store):
    customer = Customer(
        store_id=test_store.store_id, mobile_number="9999999999", name="Parity Customer", email="cust@example.com"
    )
    db.session.add(customer)
    db.session.commit()

    configured = client.put(
        "/api/v1/loyalty/program",
        headers=owner_headers,
        json={
            "points_per_rupee": 1.0,
            "redemption_rate": 0.1,
            "min_redemption_points": 10,
            "expiry_days": 365,
            "is_active": True,
        },
    )
    assert configured.status_code == 200

    tier = client.post(
        "/api/v1/loyalty/tiers",
        headers=owner_headers,
        json={
            "name": "Gold",
            "description": "Gold tier",
            "min_points": 100,
            "benefits": ["priority support"],
            "multiplier": 2,
        },
    )
    assert tier.status_code == 201
    tier_id = tier.get_json()["data"]["id"]

    enrolled = client.post(f"/api/v1/loyalty/customers/{customer.customer_id}/enroll", headers=owner_headers)
    assert enrolled.status_code == 200

    adjusted = client.post(
        f"/api/v1/loyalty/customers/{customer.customer_id}/adjust",
        headers=owner_headers,
        json={"points": 150, "reason": "Bonus"},
    )
    assert adjusted.status_code == 200

    bulk = client.post(
        "/api/v1/loyalty/customers/adjustments/bulk",
        headers=owner_headers,
        json={"adjustments": [{"customer_id": customer.customer_id, "points": 10, "reason": "Bulk bonus"}]},
    )
    assert bulk.status_code == 200
    assert len(bulk.get_json()["data"]["successful"]) == 1

    tier_update = client.put(
        f"/api/v1/loyalty/customers/{customer.customer_id}/tier",
        headers=owner_headers,
        json={"tier_id": tier_id},
    )
    assert tier_update.status_code == 200
    assert tier_update.get_json()["data"]["tier_id"] == tier_id

    expiring = client.get("/api/v1/loyalty/expiring-points?days=400", headers=owner_headers)
    assert expiring.status_code == 200


def test_gst_parity_endpoints(client, owner_headers, test_store, test_category):
    db.session.add(HSNMaster(hsn_code="1001", description="Test HSN", default_gst_rate=5))
    db.session.add(GSTFilingPeriod(store_id=test_store.store_id, period="2026-03", status="READY"))
    db.session.commit()

    created = client.post(
        "/api/v1/gst/hsn-mappings",
        headers=owner_headers,
        json={"hsn_code": "1001", "category_id": test_category.category_id, "tax_rate": 5, "description": "Mapped"},
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/gst/hsn-mappings", headers=owner_headers)
    assert listed.status_code == 200
    assert listed.get_json()["data"][0]["hsn_code"] == "1001"

    updated = client.patch(
        "/api/v1/gst/hsn-mappings/1001",
        headers=owner_headers,
        json={"description": "Updated mapping"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["description"] == "Updated mapping"

    filed = client.post("/api/v1/gst/gstr1/file", headers=owner_headers, json={"period": "2026-03"})
    assert filed.status_code == 200
    assert filed.get_json()["data"]["status"] == "FILED"

    deleted = client.delete("/api/v1/gst/hsn-mappings/1001", headers=owner_headers)
    assert deleted.status_code == 200


def test_supplier_purchase_order_parity_endpoints(client, owner_headers, test_store, test_product):
    supplier_resp = client.post(
        "/api/v1/suppliers", headers=owner_headers, json={"name": "Parity Supplier", "email": "supplier@example.com"}
    )
    assert supplier_resp.status_code == 201
    supplier_id = supplier_resp.get_json()["data"]["id"]

    link_resp = client.post(
        f"/api/v1/suppliers/{supplier_id}/products",
        headers=owner_headers,
        json={"product_id": test_product.product_id, "quoted_price": 80, "lead_time_days": 5},
    )
    assert link_resp.status_code == 201

    update_link = client.patch(
        f"/api/v1/suppliers/{supplier_id}/products/{test_product.product_id}",
        headers=owner_headers,
        json={"quoted_price": 85},
    )
    assert update_link.status_code == 200

    po_resp = client.post(
        "/api/v1/purchase-orders",
        headers=owner_headers,
        json={
            "supplier_id": supplier_id,
            "items": [{"product_id": test_product.product_id, "ordered_qty": 10, "unit_price": 85}],
        },
    )
    assert po_resp.status_code == 201
    po_id = po_resp.get_json()["data"]["id"]

    update_po = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        headers=owner_headers,
        json={
            "notes": "Updated draft",
            "items": [{"product_id": test_product.product_id, "ordered_qty": 12, "unit_price": 85}],
        },
    )
    assert update_po.status_code == 200

    sent = client.post(f"/api/v1/purchase-orders/{po_id}/send", headers=owner_headers)
    assert sent.status_code == 200

    confirmed = client.post(f"/api/v1/purchase-orders/{po_id}/confirm", headers=owner_headers)
    assert confirmed.status_code == 200
    assert confirmed.get_json()["data"]["status"] == "CONFIRMED"

    pdf = client.get(f"/api/v1/purchase-orders/{po_id}/pdf", headers=owner_headers)
    assert pdf.status_code == 200
    assert pdf.get_json()["data"]["url"].endswith("/pdf/download")

    emailed = client.post(
        f"/api/v1/purchase-orders/{po_id}/email",
        headers=owner_headers,
        json={"email": "supplier@example.com"},
    )
    assert emailed.status_code == 200

    deleted_link = client.delete(
        f"/api/v1/suppliers/{supplier_id}/products/{test_product.product_id}", headers=owner_headers
    )
    assert deleted_link.status_code == 200


def test_whatsapp_parity_endpoints(client, owner_headers, test_store):
    config = WhatsAppConfig(store_id=test_store.store_id, phone_number_id="123", is_active=True, waba_id="waba")
    config.access_token_encrypted = "token"
    db.session.add(config)
    db.session.commit()

    template = client.post(
        "/api/v1/whatsapp/templates",
        headers=owner_headers,
        json={
            "name": "promo",
            "category": "MARKETING",
            "language": "en",
            "components": [{"type": "BODY", "text": "Hello"}],
        },
    )
    assert template.status_code == 201
    template_id = template.get_json()["data"]["id"]

    message = client.post(
        "/api/v1/whatsapp/messages",
        headers=owner_headers,
        json={"to": "9876543210", "message_type": "TEXT", "content": "hello"},
    )
    assert message.status_code == 201

    bulk = client.post(
        "/api/v1/whatsapp/messages/bulk",
        headers=owner_headers,
        json={"messages": [{"to": "9876543210", "message_type": "TEXT", "content": "hello"}]},
    )
    assert bulk.status_code == 200
    assert len(bulk.get_json()["data"]["successful"]) == 1

    campaign = client.post(
        "/api/v1/whatsapp/campaigns",
        headers=owner_headers,
        json={
            "name": "Launch",
            "description": "Launch promo",
            "template_id": template_id,
            "recipients": ["9876543210"],
        },
    )
    assert campaign.status_code == 201
    campaign_id = campaign.get_json()["data"]["id"]

    sent_campaign = client.post(f"/api/v1/whatsapp/campaigns/{campaign_id}/send", headers=owner_headers)
    assert sent_campaign.status_code == 200

    opt_in = client.post("/api/v1/whatsapp/contacts/9876543210/opt-in", headers=owner_headers)
    assert opt_in.status_code == 200
    status = client.get("/api/v1/whatsapp/contacts/9876543210/status", headers=owner_headers)
    assert status.status_code == 200
    assert status.get_json()["data"]["status"] == "OPTED_IN"

    test_message = client.post(
        "/api/v1/whatsapp/messages/test",
        headers=owner_headers,
        json={"to": "9876543210", "template_name": "promo"},
    )
    assert test_message.status_code == 201


def test_chain_and_finance_parity_endpoints(client, app, test_owner, test_store, test_product):
    group_resp = client.post(
        "/api/v1/chain/groups",
        headers={"Authorization": f"Bearer {generate_access_token(test_owner.user_id, test_store.store_id, 'owner')}"},
        json={"name": "Parity Chain"},
    )
    assert group_resp.status_code == 200
    group_id = group_resp.get_json()["data"]["group_id"]
    headers = _chain_headers(test_owner.user_id, test_store.store_id, group_id)

    detail = client.get(f"/api/v1/chain/groups/{group_id}", headers=headers)
    assert detail.status_code == 200

    updated = client.patch(f"/api/v1/chain/groups/{group_id}", headers=headers, json={"name": "Updated Chain"})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "Updated Chain"

    from app.models import Store

    extra_store = Store(store_name="Parity Branch", store_type="grocery")
    db.session.add(extra_store)
    db.session.commit()

    added = client.post(
        f"/api/v1/chain/groups/{group_id}/stores", headers=headers, json={"store_id": extra_store.store_id}
    )
    assert added.status_code == 201

    removed = client.delete(f"/api/v1/chain/groups/{group_id}/stores/{extra_store.store_id}", headers=headers)
    assert removed.status_code == 200

    created_transfer = client.post(
        "/api/v1/chain/transfers",
        headers=headers,
        json={
            "from_store_id": test_store.store_id,
            "to_store_id": test_store.store_id,
            "product_id": test_product.product_id,
            "quantity": 5,
        },
    )
    assert created_transfer.status_code == 201

    reserve = FinancialAccount(store_id=test_store.store_id, account_type="RESERVE", balance=Decimal("2500"))
    operating = FinancialAccount(store_id=test_store.store_id, account_type="OPERATING", balance=Decimal("7500"))
    db.session.add_all([reserve, operating])
    db.session.flush()
    db.session.add(
        TreasuryConfig(
            store_id=test_store.store_id,
            sweep_enabled=True,
            sweep_strategy="AUTO",
            min_balance_threshold=Decimal("500"),
            is_active=True,
            sweep_target_account_id=reserve.id,
        )
    )
    db.session.add(
        TreasuryTransaction(store_id=test_store.store_id, amount=Decimal("200"), type="TRANSFER_IN", status="COMPLETED")
    )
    db.session.add(
        LedgerEntry(
            account_id=reserve.id,
            entry_type="CREDIT",
            amount=Decimal("200"),
            balance_after=Decimal("2500"),
            description="Treasury credit",
        )
    )
    db.session.commit()

    finance_headers = {
        "Authorization": f"Bearer {generate_access_token(test_owner.user_id, test_store.store_id, 'owner')}"
    }
    treasury_config = client.get("/api/v2/finance/treasury/config", headers=finance_headers)
    assert treasury_config.status_code == 200
    assert treasury_config.get_json()["auto_transfer_enabled"] is True

    treasury_transactions = client.get("/api/v2/finance/treasury/transactions", headers=finance_headers)
    assert treasury_transactions.status_code == 200
    assert len(treasury_transactions.get_json()) >= 1
