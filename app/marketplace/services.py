import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from app.models.marketplace_models import (
    RFQ,
    CatalogItem,
    MarketplacePOItem,
    MarketplacePurchaseOrder,
    ProcurementRecommendation,
    RFQResponse,
    SupplierProfile,
    SupplierReview,
)


def search_catalog(db: Session, query: str | None = None, category: str | None = None,
                   min_price: float | None = None, max_price: float | None = None,
                   min_rating: float | None = None, max_moq: int | None = None,
                   sort_by: str = "relevance", limit: int = 20, offset: int = 0) -> dict:

    q = db.query(CatalogItem, SupplierProfile).join(SupplierProfile, CatalogItem.supplier_profile_id == SupplierProfile.id)

    q = q.filter(CatalogItem.is_active == True)

    if query:
        q = q.filter(or_(
            CatalogItem.name.ilike(f"%{query}%"),
            CatalogItem.description.ilike(f"%{query}%"),
            SupplierProfile.business_name.ilike(f"%{query}%")
        ))

    if category:
        q = q.filter(CatalogItem.category == category)

    if min_price is not None:
        q = q.filter(CatalogItem.unit_price >= min_price)

    if max_price is not None:
        q = q.filter(CatalogItem.unit_price <= max_price)

    if min_rating is not None:
        q = q.filter(SupplierProfile.rating >= min_rating)

    if max_moq is not None:
        q = q.filter(CatalogItem.moq <= max_moq)

    # Sorting
    if sort_by == "price_asc":
        q = q.order_by(CatalogItem.unit_price.asc())
    elif sort_by == "price_desc":
        q = q.order_by(CatalogItem.unit_price.desc())
    elif sort_by == "rating_desc":
        q = q.order_by(SupplierProfile.rating.desc())
    else:
        # relevance or default
        q = q.order_by(CatalogItem.id.desc())

    total_count = q.count()
    results = q.limit(limit).offset(offset).all()

    items = []
    for item, supplier in results:
        items.append({
            "id": item.id,
            "sku": item.sku,
            "name": item.name,
            "description": item.description,
            "category": item.category,
            "unit_price": float(item.unit_price),
            "currency": item.currency,
            "moq": item.moq,
            "case_pack": item.case_pack,
            "lead_time_days": item.lead_time_days,
            "images": item.images,
            "specifications": item.specifications,
            "bulk_pricing": item.bulk_pricing,
            "available_quantity": item.available_quantity,
            "supplier": {
                "id": supplier.id,
                "name": supplier.business_name,
                "rating": float(supplier.rating) if supplier.rating else None,
                "verified": supplier.verified
            }
        })

    return {
        "items": items,
        "total": total_count,
        "page": (offset // limit) + 1,
        "pages": (total_count + limit - 1) // limit
    }

def get_procurement_recommendations(db: Session, merchant_id: int, category: str | None = None, urgency: str | None = None) -> list[dict]:
    q = db.query(ProcurementRecommendation).filter(ProcurementRecommendation.merchant_id == merchant_id)

    if category:
        q = q.filter(ProcurementRecommendation.product_category == category)
    if urgency:
        q = q.filter(ProcurementRecommendation.urgency == urgency)

    q = q.filter(ProcurementRecommendation.acted_upon == False)
    q = q.filter(or_(ProcurementRecommendation.expires_at.is_(None), ProcurementRecommendation.expires_at > datetime.now(timezone.utc)))
    q = q.order_by(ProcurementRecommendation.confidence.desc())

    recommendations = q.all()

    result = []
    for r in recommendations:
        result.append({
            "id": r.id,
            "category": r.product_category,
            "recommended_items": r.recommended_items,
            "recommended_supplier_ids": r.recommended_supplier_ids,
            "estimated_savings": float(r.estimated_savings) if r.estimated_savings else None,
            "urgency": r.urgency,
            "trigger": r.trigger_event,
            "confidence": float(r.confidence) if r.confidence else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None
        })
    return result

def create_rfq(db: Session, merchant_id: int, items: list) -> dict:
    rfq = RFQ(
        merchant_id=merchant_id,
        items=items,
        status="OPEN"
    )
    db.add(rfq)
    db.flush()

    # In a real engine, we'd query Elasticsearch or rules to find matched suppliers count
    # Stub:
    matched_count = 3
    rfq.matched_suppliers_count = matched_count

    db.commit()

    return {
        "rfq_id": rfq.id,
        "matched_suppliers_count": matched_count
    }

def create_marketplace_order(db: Session, merchant_id: int, supplier_profile_id: int, items: list, payment_terms: str, finance_requested: bool) -> dict:
    import uuid

    order_number = f"PO-{uuid.uuid4().hex[:8].upper()}"

    subtotal = 0.0
    po_items_to_add = []

    for item in items:
        # In a real system, we'd fetch actual price or apply bulk pricing
        # For this implementation, we take unit_price from the API directly or calculate it
        # Assuming the caller provided catalog_item_id and quantity
        cat_item = db.query(CatalogItem).filter(CatalogItem.id == item["catalog_item_id"]).first()
        if not cat_item:
            raise ValueError(f"Catalog item {item['catalog_item_id']} not found")

        qty = item["quantity"]
        unit_price = float(cat_item.unit_price) # Simplification: should use calculate_bulk_price here
        item_subtotal = qty * unit_price
        subtotal += item_subtotal

        po_item = MarketplacePOItem(
            catalog_item_id=cat_item.id,
            quantity=qty,
            unit_price=unit_price,
            subtotal=item_subtotal
        )
        po_items_to_add.append(po_item)

    tax = subtotal * 0.05 # Mock 5% tax
    shipping_cost = 50.0 # Mock shipping
    total = subtotal + tax + shipping_cost

    loan_id = None
    if finance_requested:
        from app.models.finance_models import LoanApplication
        # Simplified: Create a placeholder loan application or trigger Team 2's engine
        loan_app = LoanApplication(
            store_id=merchant_id,
            product_id=1, # Mock term loan
            requested_amount=total,
            status="APPROVED", # Auto-approve for demo
            outstanding_principal=total
        )
        db.add(loan_app)
        db.flush()
        loan_id = loan_app.id

    po = MarketplacePurchaseOrder(
        order_number=order_number,
        merchant_id=merchant_id,
        supplier_profile_id=supplier_profile_id,
        status="SUBMITTED",
        subtotal=subtotal,
        tax=tax,
        shipping_cost=shipping_cost,
        total=total,
        payment_terms=payment_terms,
        payment_status="PENDING",
        financed_by_retailiq=finance_requested,
        loan_id=loan_id,
        expected_delivery=datetime.now(timezone.utc).date() + timedelta(days=5)
    )

    db.add(po)
    db.flush()

    for pi in po_items_to_add:
        pi.order_id = po.id
        db.add(pi)

    db.commit()

    return {
        "order_id": po.id,
        "order_number": po.order_number,
        "total": total,
        "estimated_delivery": po.expected_delivery.isoformat() if po.expected_delivery else None,
        "financing_decision": "APPROVED" if finance_requested else "N/A"
    }

def get_supplier_dashboard(db: Session, supplier_profile_id: int) -> dict:
    total_orders = db.query(MarketplacePurchaseOrder).filter(MarketplacePurchaseOrder.supplier_profile_id == supplier_profile_id).count()
    revenue = db.query(func.sum(MarketplacePurchaseOrder.subtotal)).filter(
        MarketplacePurchaseOrder.supplier_profile_id == supplier_profile_id,
        MarketplacePurchaseOrder.status.in_(["DELIVERED", "SHIPPED"])
    ).scalar() or 0.0

    supplier = db.query(SupplierProfile).filter(SupplierProfile.id == supplier_profile_id).first()

    return {
        "total_orders": total_orders,
        "revenue": float(revenue),
        "avg_rating": float(supplier.rating) if supplier and supplier.rating else None,
        "top_products": [], # Stub
        "demand_insights": [] # Stub
    }

def calculate_bulk_price(catalog_item_id: int, quantity: int, db: Session) -> float:
    cat_item = db.query(CatalogItem).filter(CatalogItem.id == catalog_item_id).first()
    if not cat_item:
        return 0.0

    base_price = float(cat_item.unit_price)
    if not cat_item.bulk_pricing:
        return base_price

    # bulk_pricing: [{"qty": 100, "price": 9.50}, {"qty": 500, "price": 8.00}]
    best_price = base_price
    # Assume bulk_pricing is a list of dicts, sorted or we can just iterate
    import json
    bulk_tiers = cat_item.bulk_pricing
    if isinstance(bulk_tiers, str):
        try:
            bulk_tiers = json.loads(bulk_tiers)
        except Exception:
            bulk_tiers = []

    for tier in bulk_tiers:
        if quantity >= tier.get("qty", 0):
            if tier.get("price", float('inf')) < best_price:
                best_price = tier.get("price")

    return best_price
