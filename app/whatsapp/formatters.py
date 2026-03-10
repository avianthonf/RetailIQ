"""
Formatters for outbound WhatsApp messages.
"""


def format_po_message(po_id: str, db_session) -> str:
    """
    Renders a plain text PO summary for sending via WhatsApp.
    Format:
        Purchase Order #{short_ref}
        From: {store_name}
        Date: {date}

        Items:
        {product} x {qty} @ ₹{price}
        ...
        Total: ₹{total}

        Please confirm receipt.
    """
    import uuid

    from app.models import Product, PurchaseOrder, PurchaseOrderItem, Store

    try:
        po_uuid = uuid.UUID(po_id) if isinstance(po_id, str) else po_id
    except ValueError:
        return ""

    po = db_session.query(PurchaseOrder).filter_by(id=po_uuid).first()
    if not po:
        return ""

    store = db_session.query(Store).filter_by(store_id=po.store_id).first()
    store_name = store.store_name if store else "RetailIQ Store"

    date_str = po.created_at.strftime("%Y-%m-%d") if po.created_at else ""
    short_ref = str(po.id)[:8].upper()

    items = db_session.query(PurchaseOrderItem).filter_by(po_id=po_uuid).all()

    lines = [f"Purchase Order #{short_ref}", f"From: {store_name}", f"Date: {date_str}", "", "Items:"]

    total_amount = 0.0
    for item in items:
        product = db_session.query(Product).filter_by(product_id=item.product_id).first()
        prod_name = product.name if product else "Unknown Product"
        price_str = f"₹{float(item.unit_price):g}" if item.unit_price else "₹0"
        qty_str = (
            f"{float(item.ordered_qty):g}" if hasattr(item, "ordered_qty") and item.ordered_qty is not None else "0"
        )
        lines.append(f"- {prod_name} x {qty_str} @ {price_str}")
        total_amount += (float(item.ordered_qty) if item.ordered_qty else 0.0) * (
            float(item.unit_price) if item.unit_price else 0.0
        )

    total_str = f"₹{total_amount:g}"
    lines.extend(["", f"Total: {total_str}", "", "Please confirm receipt."])

    return "\n".join(lines)
