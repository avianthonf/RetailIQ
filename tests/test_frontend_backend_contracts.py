import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app import db
from app.auth.utils import generate_access_token
from app.models import (
    APIUsageRecord,
    Category,
    Customer,
    CustomerLoyaltyAccount,
    DataSource,
    Developer,
    FinancialAccount,
    GSTFilingPeriod,
    HSNMaster,
    LedgerEntry,
    LoyaltyTier,
    MarketAlert,
    MarketplaceApp,
    MarketSignal,
    PriceIndex,
    Store,
    StoreGroupMembership,
    SupplierProduct,
    TreasuryTransaction,
    WebhookEvent,
    WhatsAppConfig,
    WhatsAppMessageLog,
)
from app.models.finance_models import TreasuryConfig


def _chain_headers(user_id, store_id, group_id):
    token = generate_access_token(user_id, store_id, "owner", chain_group_id=str(group_id), chain_role="CHAIN_OWNER")
    return {"Authorization": f"Bearer {token}"}


def test_developer_contract_lifecycle_and_filters(client, owner_headers, test_owner):
    developer = Developer(name="Owner Dev", email="owner-dev@example.com", user_id=test_owner.user_id)
    db.session.add(developer)
    db.session.commit()

    created = client.post(
        "/api/v1/developer/apps",
        headers=owner_headers,
        json={
            "name": "Contracts App",
            "description": "Initial description",
            "app_type": "WEB",
            "redirect_uris": ["https://example.com/callback"],
            "scopes": ["read:inventory"],
        },
    )
    assert created.status_code == 201
    app_data = created.get_json()["data"]
    app_id = str(app_data["id"])

    listed = client.get("/api/v1/developer/apps", headers=owner_headers)
    assert listed.status_code == 200
    assert len(listed.get_json()["data"]) == 1

    updated = client.patch(
        f"/api/v1/developer/apps/{app_id}",
        headers=owner_headers,
        json={"name": "Contracts App v2", "status": "SUSPENDED"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "Contracts App v2"
    assert updated.get_json()["data"]["status"] == "SUSPENDED"

    webhook = client.post(
        "/api/v1/developer/webhooks",
        headers=owner_headers,
        json={
            "app_id": app_id,
            "url": "https://example.com/hooks/main",
            "events": ["transaction.created"],
            "secret": "abc123",
        },
    )
    assert webhook.status_code == 201
    assert webhook.get_json()["data"]["events"] == ["transaction.created"]

    webhook_list = client.get("/api/v1/developer/webhooks", headers=owner_headers)
    assert webhook_list.status_code == 200
    assert len(webhook_list.get_json()["data"]) == 1

    webhook_update = client.patch(
        f"/api/v1/developer/webhooks/{app_id}",
        headers=owner_headers,
        json={
            "url": "https://example.com/hooks/secondary",
            "events": ["transaction.created", "inventory.updated"],
            "is_active": False,
        },
    )
    assert webhook_update.status_code == 200
    assert webhook_update.get_json()["data"]["url"] == "https://example.com/hooks/secondary"
    assert webhook_update.get_json()["data"]["is_active"] is False

    bucket_now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    bucket_old = bucket_now - timedelta(days=3)
    db.session.add_all(
        [
            APIUsageRecord(
                app_id=int(app_id),
                endpoint="/api/v2/inventory",
                method="GET",
                minute_bucket=bucket_old,
                request_count=4,
                error_count=1,
                avg_latency_ms=100,
            ),
            APIUsageRecord(
                app_id=int(app_id),
                endpoint="/api/v2/sales",
                method="GET",
                minute_bucket=bucket_now,
                request_count=7,
                error_count=2,
                avg_latency_ms=120,
            ),
            WebhookEvent(
                app_id=int(app_id),
                event_type="transaction.created",
                payload={"ok": True},
                delivery_url="https://example.com/hooks/secondary",
                status="FAILED",
            ),
        ]
    )
    db.session.commit()

    recent_usage = client.get(
        "/api/v1/developer/usage",
        headers=owner_headers,
        query_string={"from_date": (bucket_now - timedelta(hours=1)).isoformat()},
    )
    assert recent_usage.status_code == 200
    usage_data = recent_usage.get_json()["data"]
    assert usage_data["total_requests"] == 7
    assert usage_data["top_endpoints"][0]["path"] == "/api/v2/sales"

    rate_limits = client.get("/api/v1/developer/rate-limits", headers=owner_headers)
    assert rate_limits.status_code == 200
    assert rate_limits.get_json()["data"][0]["remaining"] == 53

    error_logs = client.get("/api/v1/developer/logs", headers=owner_headers, query_string={"level": "error"})
    assert error_logs.status_code == 200
    logs_data = error_logs.get_json()["data"]
    assert logs_data["total"] >= 2
    assert all(log["level"] == "error" for log in logs_data["logs"])

    with patch("app.tasks.webhook_tasks.deliver_webhook.delay") as mock_delay:
        tested = client.post(f"/api/v1/developer/webhooks/{app_id}/test", headers=owner_headers)
        assert tested.status_code == 200
        assert mock_delay.called

    deleted_webhook = client.delete(f"/api/v1/developer/webhooks/{app_id}", headers=owner_headers)
    assert deleted_webhook.status_code == 200
    assert client.get("/api/v1/developer/webhooks", headers=owner_headers).get_json()["data"] == []

    db.session.add_all(
        [
            MarketplaceApp(
                developer_app_id=int(app_id),
                name="Approved App",
                tagline="Live",
                category="ops",
                pricing_model="FREE",
                review_status="APPROVED",
            ),
            MarketplaceApp(
                developer_app_id=int(app_id),
                name="Pending App",
                tagline="Draft",
                category="ops",
                pricing_model="FREE",
                review_status="PENDING",
            ),
        ]
    )
    db.session.commit()

    marketplace = client.get("/api/v1/developer/marketplace")
    assert marketplace.status_code == 200
    assert [item["name"] for item in marketplace.get_json()["data"]] == ["Approved App"]

    delete_candidate = client.post(
        "/api/v1/developer/apps",
        headers=owner_headers,
        json={"name": "Delete Me", "app_type": "BACKEND", "scopes": ["read:inventory"]},
    )
    delete_candidate_id = delete_candidate.get_json()["data"]["id"]
    deleted_app = client.delete(f"/api/v1/developer/apps/{delete_candidate_id}", headers=owner_headers)
    assert deleted_app.status_code == 200


def test_developer_webhook_test_requires_existing_subscription(client, owner_headers, test_owner):
    developer = Developer(name="Owner Dev", email="owner-dev-2@example.com", user_id=test_owner.user_id)
    db.session.add(developer)
    db.session.commit()

    created = client.post(
        "/api/v1/developer/apps",
        headers=owner_headers,
        json={"name": "No Hook App", "app_type": "BACKEND", "scopes": ["read:inventory"]},
    )
    app_id = created.get_json()["data"]["id"]

    tested = client.post(f"/api/v1/developer/webhooks/{app_id}/test", headers=owner_headers)
    assert tested.status_code == 404
    assert tested.get_json()["error"]["code"] == "NOT_FOUND"


def test_market_contracts_cover_detail_alerts_forecasts_and_recommendations(
    client, owner_headers, test_store, test_category, test_product
):
    source = DataSource(name="RivalMart", source_type="competitor")
    db.session.add(source)
    db.session.flush()
    db.session.add_all(
        [
            MarketSignal(
                signal_type="PRICE",
                source_id=source.id,
                category_id=test_category.category_id,
                region_code="KA",
                value=105,
            ),
            MarketSignal(
                signal_type="PRICE",
                source_id=source.id,
                category_id=test_category.category_id,
                region_code="KA",
                value=115,
            ),
            MarketAlert(
                merchant_id=test_store.store_id,
                alert_type="PRICE_SPIKE",
                severity="HIGH",
                message="Price pressure building",
                recommended_action="Review category pricing",
            ),
        ]
    )
    db.session.commit()

    missing_category = client.post("/api/v1/market/indices/compute", headers=owner_headers, json={})
    assert missing_category.status_code == 400

    empty_category = Category(store_id=test_store.store_id, name="Empty Category", gst_rate=5)
    db.session.add(empty_category)
    db.session.commit()
    no_data = client.post(
        "/api/v1/market/indices/compute",
        headers=owner_headers,
        json={"category_id": empty_category.category_id},
    )
    assert no_data.status_code == 404

    computed = client.post(
        "/api/v1/market/indices/compute",
        headers=owner_headers,
        json={"category_id": test_category.category_id},
    )
    assert computed.status_code == 200
    assert computed.get_json()["data"]["new_index"] == 110.0

    competitor_list = client.get("/api/v1/market/competitors", headers=owner_headers)
    assert competitor_list.status_code == 200
    assert competitor_list.get_json()["data"][0]["pricing_strategy"] == "COMPETITIVE"

    competitor_detail = client.get(f"/api/v1/market/competitors/{source.id}", headers=owner_headers)
    assert competitor_detail.status_code == 200
    assert competitor_detail.get_json()["data"]["name"] == "RivalMart"

    competitor_missing = client.get("/api/v1/market/competitors/999999", headers=owner_headers)
    assert competitor_missing.status_code == 404

    alerts = client.get("/api/v1/market/alerts", headers=owner_headers)
    assert alerts.status_code == 200
    assert len(alerts.get_json()["data"]) == 1

    alert_id = alerts.get_json()["data"][0]["id"]
    acknowledged = client.post(f"/api/v1/market/alerts/{alert_id}/acknowledge", headers=owner_headers)
    assert acknowledged.status_code == 200

    alerts_after_ack = client.get("/api/v1/market/alerts", headers=owner_headers)
    assert alerts_after_ack.status_code == 200
    assert alerts_after_ack.get_json()["data"] == []

    alerts_all = client.get(
        "/api/v1/market/alerts",
        headers=owner_headers,
        query_string={"unacknowledged_only": "false"},
    )
    assert alerts_all.status_code == 200
    assert alerts_all.get_json()["data"][0]["acknowledged"] is True

    forecasts = client.get(
        "/api/v1/market/forecasts",
        headers=owner_headers,
        query_string={"product_id": test_product.product_id},
    )
    assert forecasts.status_code == 200
    assert forecasts.get_json()["data"][0]["product_id"] == str(test_product.product_id)

    generate_missing = client.post("/api/v1/market/forecasts/generate", headers=owner_headers, json={})
    assert generate_missing.status_code == 400

    generate_not_found = client.post(
        "/api/v1/market/forecasts/generate",
        headers=owner_headers,
        json={"product_id": 999999, "forecast_period": "next_14_days"},
    )
    assert generate_not_found.status_code == 404

    generated = client.post(
        "/api/v1/market/forecasts/generate",
        headers=owner_headers,
        json={"product_id": test_product.product_id, "forecast_period": "next_14_days"},
    )
    assert generated.status_code == 200
    assert generated.get_json()["data"]["forecast_period"] == "next_14_days"

    recommendations = client.get("/api/v1/market/recommendations", headers=owner_headers)
    assert recommendations.status_code == 200
    rec = recommendations.get_json()["data"][0]
    assert rec["title"] == "Price Spike"
    assert rec["status"] == "COMPLETED"

    saved_index = db.session.query(PriceIndex).filter_by(category_id=test_category.category_id).first()
    assert saved_index is not None


def test_loyalty_contracts_cover_tier_crud_assignment_bulk_and_analytics(client, owner_headers, test_store):
    customer = Customer(store_id=test_store.store_id, mobile_number="9999999999", name="Tier Tester")
    db.session.add(customer)
    db.session.commit()

    configured = client.put(
        "/api/v1/loyalty/program",
        headers=owner_headers,
        json={
            "points_per_rupee": 1.0,
            "redemption_rate": 0.1,
            "min_redemption_points": 10,
            "expiry_days": 30,
            "is_active": True,
        },
    )
    assert configured.status_code == 200

    created_tier = client.post(
        "/api/v1/loyalty/tiers",
        headers=owner_headers,
        json={
            "name": "Gold",
            "description": "Priority tier",
            "min_points": 100,
            "max_points": 999,
            "benefits": ["priority support"],
            "multiplier": 2,
        },
    )
    assert created_tier.status_code == 201
    tier_id = created_tier.get_json()["data"]["id"]

    updated_tier = client.patch(
        f"/api/v1/loyalty/tiers/{tier_id}",
        headers=owner_headers,
        json={"description": "Priority tier updated", "multiplier": 2.5},
    )
    assert updated_tier.status_code == 200
    assert updated_tier.get_json()["data"]["multiplier"] == 2.5

    enrolled = client.post(f"/api/v1/loyalty/customers/{customer.customer_id}/enroll", headers=owner_headers)
    assert enrolled.status_code == 200
    assert enrolled.get_json()["data"]["tier_name"] == "Base"

    assigned = client.put(
        f"/api/v1/loyalty/customers/{customer.customer_id}/tier",
        headers=owner_headers,
        json={"tier_id": tier_id},
    )
    assert assigned.status_code == 200
    assert assigned.get_json()["data"]["tier_name"] == "Gold"

    adjusted = client.post(
        f"/api/v1/loyalty/customers/{customer.customer_id}/adjust",
        headers=owner_headers,
        json={"points": 150, "reason": "Promotion"},
    )
    assert adjusted.status_code == 200
    assert adjusted.get_json()["data"]["balance_after"] == 150.0

    bulk = client.post(
        "/api/v1/loyalty/customers/adjustments/bulk",
        headers=owner_headers,
        json={
            "adjustments": [
                {"customer_id": customer.customer_id, "points": 10, "reason": "Bonus"},
                {"customer_id": 999999, "points": 10, "reason": "Missing"},
            ]
        },
    )
    assert bulk.status_code == 200
    bulk_data = bulk.get_json()["data"]
    assert len(bulk_data["successful"]) == 1
    assert len(bulk_data["failed"]) == 1

    analytics = client.get("/api/v1/loyalty/analytics", headers=owner_headers)
    assert analytics.status_code == 200
    analytics_data = analytics.get_json()["data"]
    assert analytics_data["enrolled_customers"] == 1
    assert analytics_data["top_customers"][0]["customer_name"] == "Tier Tester"

    account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer.customer_id).first()
    account.last_activity_at = datetime.now(timezone.utc) - timedelta(days=25)
    db.session.commit()

    expiring = client.get("/api/v1/loyalty/expiring-points", headers=owner_headers, query_string={"days": 10})
    assert expiring.status_code == 200
    assert expiring.get_json()["data"][0]["customer_id"] == str(customer.customer_id)

    assigned_tier = db.session.query(LoyaltyTier).filter_by(id=account.tier_id).first()
    base_tier = db.session.query(LoyaltyTier).filter_by(program_id=assigned_tier.program_id, is_default=True).first()

    default_delete = client.delete(f"/api/v1/loyalty/tiers/{base_tier.id}", headers=owner_headers)
    assert default_delete.status_code == 422

    deleted_tier = client.delete(f"/api/v1/loyalty/tiers/{tier_id}", headers=owner_headers)
    assert deleted_tier.status_code == 200
    db.session.refresh(account)
    assert str(account.tier_id) == str(base_tier.id)


def test_gst_contracts_cover_mapping_errors_and_filing_json_updates(
    client, owner_headers, test_store, test_category, tmp_path
):
    default_config = client.get("/api/v1/gst/config", headers=owner_headers)
    assert default_config.status_code == 200
    assert default_config.get_json()["data"]["is_gst_enabled"] is False

    db.session.add(HSNMaster(hsn_code="1001", description="Rice", default_gst_rate=5))
    db.session.commit()

    invalid_mapping = client.post("/api/v1/gst/hsn-mappings", headers=owner_headers, json={"hsn_code": "1001"})
    assert invalid_mapping.status_code == 400

    created = client.post(
        "/api/v1/gst/hsn-mappings",
        headers=owner_headers,
        json={"hsn_code": "1001", "category_id": test_category.category_id, "tax_rate": 5, "description": "Rice tax"},
    )
    assert created.status_code == 201

    listed = client.get("/api/v1/gst/hsn-mappings", headers=owner_headers)
    assert listed.status_code == 200
    assert listed.get_json()["data"][0]["description"] == "Rice tax"

    updated = client.patch(
        "/api/v1/gst/hsn-mappings/1001",
        headers=owner_headers,
        json={"description": "Updated rice tax"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["description"] == "Updated rice tax"

    missing_update = client.patch("/api/v1/gst/hsn-mappings/9999", headers=owner_headers, json={"tax_rate": 12})
    assert missing_update.status_code == 404

    gstr1_path = tmp_path / "gstr1.json"
    gstr1_path.write_text(json.dumps({"period": "2026-03"}), encoding="utf-8")
    db.session.add(
        GSTFilingPeriod(
            store_id=test_store.store_id,
            period="2026-03",
            status="READY",
            gstr1_json_path=str(gstr1_path),
            total_taxable=Decimal("1000.00"),
        )
    )
    db.session.commit()

    filed = client.post("/api/v1/gst/gstr1/file", headers=owner_headers, json={"period": "2026-03"})
    assert filed.status_code == 200
    filed_data = filed.get_json()["data"]
    assert filed_data["status"] == "FILED"
    saved_payload = json.loads(gstr1_path.read_text(encoding="utf-8"))
    assert saved_payload["acknowledgement_number"] == filed_data["acknowledgement_number"]
    assert "filed_on" in saved_payload

    deleted = client.delete("/api/v1/gst/hsn-mappings/1001", headers=owner_headers)
    assert deleted.status_code == 200

    missing_delete = client.delete("/api/v1/gst/hsn-mappings/1001", headers=owner_headers)
    assert missing_delete.status_code == 404


def test_supplier_and_purchase_order_contracts_cover_draft_confirm_pdf_and_email(client, owner_headers, test_product):
    supplier = client.post(
        "/api/v1/suppliers",
        headers=owner_headers,
        json={"name": "Lifecycle Supplier", "email": "supplier@example.com"},
    )
    assert supplier.status_code == 201
    supplier_id = supplier.get_json()["data"]["id"]

    link = client.post(
        f"/api/v1/suppliers/{supplier_id}/products",
        headers=owner_headers,
        json={"product_id": test_product.product_id, "quoted_price": 50, "lead_time_days": 4},
    )
    assert link.status_code == 201

    link_update = client.patch(
        f"/api/v1/suppliers/{supplier_id}/products/{test_product.product_id}",
        headers=owner_headers,
        json={"quoted_price": 60, "is_preferred_supplier": True},
    )
    assert link_update.status_code == 200
    supplier_product = db.session.query(SupplierProduct).filter_by(product_id=test_product.product_id).first()
    assert float(supplier_product.quoted_price) == 60.0
    assert supplier_product.is_preferred_supplier is True

    po = client.post(
        "/api/v1/purchase-orders",
        headers=owner_headers,
        json={
            "supplier_id": supplier_id,
            "expected_delivery_date": "2026-04-10",
            "notes": "Initial draft",
            "items": [{"product_id": test_product.product_id, "ordered_qty": 8, "unit_price": 60}],
        },
    )
    assert po.status_code == 201
    po_id = po.get_json()["data"]["id"]

    invalid_update = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        headers=owner_headers,
        json={"expected_delivery_date": "bad-date"},
    )
    assert invalid_update.status_code == 422

    updated = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        headers=owner_headers,
        json={
            "notes": "Updated draft",
            "items": [{"product_id": test_product.product_id, "ordered_qty": 10, "unit_price": 65}],
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["notes"] == "Updated draft"
    assert updated.get_json()["data"]["items"][0]["ordered_qty"] == 10.0

    sent = client.post(f"/api/v1/purchase-orders/{po_id}/send", headers=owner_headers)
    assert sent.status_code == 200

    rejected_after_send = client.patch(
        f"/api/v1/purchase-orders/{po_id}",
        headers=owner_headers,
        json={"notes": "Should fail"},
    )
    assert rejected_after_send.status_code == 422

    confirmed = client.post(f"/api/v1/purchase-orders/{po_id}/confirm", headers=owner_headers)
    assert confirmed.status_code == 200
    assert confirmed.get_json()["data"]["status"] == "CONFIRMED"

    pdf_meta = client.get(f"/api/v1/purchase-orders/{po_id}/pdf", headers=owner_headers)
    assert pdf_meta.status_code == 200
    assert pdf_meta.get_json()["data"]["url"].endswith("/pdf/download")

    pdf_download = client.get(f"/api/v1/purchase-orders/{po_id}/pdf/download", headers=owner_headers)
    assert pdf_download.status_code == 200
    assert pdf_download.mimetype == "application/pdf"

    missing_email = client.post(f"/api/v1/purchase-orders/{po_id}/email", headers=owner_headers, json={})
    assert missing_email.status_code == 422

    with patch("app.suppliers.routes._send_raw", return_value=True):
        emailed = client.post(
            f"/api/v1/purchase-orders/{po_id}/email",
            headers=owner_headers,
            json={"email": "buyer@example.com"},
        )
    assert emailed.status_code == 200

    deleted_link = client.delete(
        f"/api/v1/suppliers/{supplier_id}/products/{test_product.product_id}",
        headers=owner_headers,
    )
    assert deleted_link.status_code == 200


def test_whatsapp_contracts_cover_template_campaign_log_and_contact_lifecycle(client, owner_headers, test_store):
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

    templates = client.get("/api/v1/whatsapp/templates", headers=owner_headers)
    assert templates.status_code == 200
    assert templates.get_json()["data"][0]["name"] == "promo"

    single_message = client.post(
        "/api/v1/whatsapp/messages",
        headers=owner_headers,
        json={"to": "9876543210", "message_type": "TEXT", "content": "hello"},
    )
    assert single_message.status_code == 201

    bulk = client.post(
        "/api/v1/whatsapp/messages/bulk",
        headers=owner_headers,
        json={
            "messages": [
                {"to": "9876543210", "message_type": "TEXT", "content": "hello"},
                {"message_type": "TEXT", "content": "missing recipient"},
            ]
        },
    )
    assert bulk.status_code == 200
    assert len(bulk.get_json()["data"]["successful"]) == 1
    assert len(bulk.get_json()["data"]["failed"]) == 1

    campaign = client.post(
        "/api/v1/whatsapp/campaigns",
        headers=owner_headers,
        json={
            "name": "Launch",
            "description": "Launch promo",
            "template_id": template_id,
            "recipients": ["9876543210", "912345678901"],
            "scheduled_at": "2026-04-10T09:00:00",
        },
    )
    assert campaign.status_code == 201
    campaign_id = campaign.get_json()["data"]["id"]
    assert campaign.get_json()["data"]["status"] == "SCHEDULED"

    updated_campaign = client.patch(
        f"/api/v1/whatsapp/campaigns/{campaign_id}",
        headers=owner_headers,
        json={"description": "Updated promo", "recipients": ["9876543210"]},
    )
    assert updated_campaign.status_code == 200
    assert updated_campaign.get_json()["data"]["recipient_count"] == 1

    fetched_campaign = client.get(f"/api/v1/whatsapp/campaigns/{campaign_id}", headers=owner_headers)
    assert fetched_campaign.status_code == 200
    assert fetched_campaign.get_json()["data"]["description"] == "Updated promo"

    sent_campaign = client.post(f"/api/v1/whatsapp/campaigns/{campaign_id}/send", headers=owner_headers)
    assert sent_campaign.status_code == 200
    assert sent_campaign.get_json()["data"]["status"] == "COMPLETED"
    assert sent_campaign.get_json()["data"]["sent_count"] == 1

    message_log = client.get("/api/v1/whatsapp/message-log", headers=owner_headers)
    assert message_log.status_code == 200
    assert len(message_log.get_json()["data"]) >= 3

    opted_out = client.post("/api/v1/whatsapp/contacts/9876543210/opt-out", headers=owner_headers)
    assert opted_out.status_code == 200
    status = client.get("/api/v1/whatsapp/contacts/9876543210/status", headers=owner_headers)
    assert status.status_code == 200
    assert status.get_json()["data"]["status"] == "OPTED_OUT"

    opted_in = client.post("/api/v1/whatsapp/contacts/9876543210/opt-in", headers=owner_headers)
    assert opted_in.status_code == 200
    status_after_in = client.get("/api/v1/whatsapp/contacts/9876543210/status", headers=owner_headers)
    assert status_after_in.get_json()["data"]["status"] == "OPTED_IN"

    test_message = client.post(
        "/api/v1/whatsapp/messages/test",
        headers=owner_headers,
        json={"to": "9876543210", "template_name": "promo"},
    )
    assert test_message.status_code == 201
    assert db.session.query(WhatsAppMessageLog).filter_by(message_type="test").count() == 1

    deleted = client.delete(f"/api/v1/whatsapp/campaigns/{campaign_id}", headers=owner_headers)
    assert deleted.status_code == 200


def test_chain_contracts_cover_group_update_membership_transfer_and_confirmation(
    client, test_owner, test_store, test_product
):
    base_headers = {
        "Authorization": f"Bearer {generate_access_token(test_owner.user_id, test_store.store_id, 'owner')}"
    }
    created = client.post("/api/v1/chain/groups", headers=base_headers, json={"name": "Main Chain"})
    assert created.status_code == 200
    group_id = created.get_json()["data"]["group_id"]
    chain_headers = _chain_headers(test_owner.user_id, test_store.store_id, group_id)

    updated = client.patch(f"/api/v1/chain/groups/{group_id}", headers=chain_headers, json={"name": "Main Chain v2"})
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "Main Chain v2"

    extra_store = Store(store_name="Second Branch", store_type="grocery")
    db.session.add(extra_store)
    db.session.commit()

    added = client.post(
        f"/api/v1/chain/groups/{group_id}/stores",
        headers=chain_headers,
        json={"store_id": extra_store.store_id},
    )
    assert added.status_code == 201

    detail = client.get(f"/api/v1/chain/groups/{group_id}", headers=chain_headers)
    assert detail.status_code == 200
    assert extra_store.store_id in detail.get_json()["data"]["member_store_ids"]

    missing_transfer = client.post(
        "/api/v1/chain/transfers", headers=chain_headers, json={"from_store_id": test_store.store_id}
    )
    assert missing_transfer.status_code == 400

    transfer = client.post(
        "/api/v1/chain/transfers",
        headers=chain_headers,
        json={
            "from_store_id": test_store.store_id,
            "to_store_id": extra_store.store_id,
            "product_id": test_product.product_id,
            "quantity": 4,
            "notes": "Move stock",
        },
    )
    assert transfer.status_code == 201
    transfer_id = transfer.get_json()["data"]["id"]

    transfers = client.get("/api/v1/chain/transfers", headers=chain_headers)
    assert transfers.status_code == 200
    assert len(transfers.get_json()["data"]) == 1

    confirmed = client.post(f"/api/v1/chain/transfers/{transfer_id}/confirm", headers=chain_headers)
    assert confirmed.status_code == 200

    removed = client.delete(f"/api/v1/chain/groups/{group_id}/stores/{extra_store.store_id}", headers=chain_headers)
    assert removed.status_code == 200
    assert db.session.query(StoreGroupMembership).filter_by(store_id=extra_store.store_id).count() == 0

    missing_membership = client.delete(
        f"/api/v1/chain/groups/{group_id}/stores/{extra_store.store_id}",
        headers=chain_headers,
    )
    assert missing_membership.status_code == 404


def test_finance_contracts_cover_treasury_defaults_and_ledger_history_fallback(client, owner_headers, test_store):
    default_config = client.get("/api/v2/finance/treasury/config", headers=owner_headers)
    assert default_config.status_code == 200
    assert default_config.get_json()["auto_transfer_enabled"] is False

    empty_history = client.get("/api/v2/finance/treasury/transactions", headers=owner_headers)
    assert empty_history.status_code == 200
    assert empty_history.get_json() == []

    reserve = FinancialAccount(store_id=test_store.store_id, account_type="RESERVE", balance=Decimal("1500.00"))
    operating = FinancialAccount(store_id=test_store.store_id, account_type="OPERATING", balance=Decimal("3500.00"))
    db.session.add_all([reserve, operating])
    db.session.flush()
    db.session.add(
        TreasuryConfig(
            store_id=test_store.store_id,
            sweep_enabled=True,
            sweep_strategy="BALANCED",
            min_balance_threshold=Decimal("500.00"),
            sweep_threshold=Decimal("250.00"),
            is_active=True,
            sweep_target_account_id=reserve.id,
        )
    )
    db.session.add(
        LedgerEntry(
            account_id=reserve.id,
            entry_type="CREDIT",
            amount=Decimal("250.00"),
            balance_after=Decimal("1500.00"),
            description="Treasury top-up",
        )
    )
    db.session.commit()

    config = client.get("/api/v2/finance/treasury/config", headers=owner_headers)
    assert config.status_code == 200
    config_data = config.get_json()
    assert config_data["auto_transfer_enabled"] is True
    assert config_data["reserve_percentage"] == 30.0
    assert config_data["strategy"] == "BALANCED"

    fallback_history = client.get("/api/v2/finance/treasury/transactions", headers=owner_headers)
    assert fallback_history.status_code == 200
    assert fallback_history.get_json()[0]["type"] == "TRANSFER_IN"

    db.session.add(
        TreasuryTransaction(
            store_id=test_store.store_id,
            amount=Decimal("100.00"),
            type="TRANSFER_OUT",
            transaction_type="SWEEP",
            status="COMPLETED",
        )
    )
    db.session.commit()

    explicit_history = client.get("/api/v2/finance/treasury/transactions", headers=owner_headers)
    assert explicit_history.status_code == 200
    assert explicit_history.get_json()[0]["description"] == "SWEEP"
