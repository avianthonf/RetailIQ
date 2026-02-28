from datetime import datetime, timedelta, timezone, date
from uuid import UUID
from sqlalchemy.sql import func
from typing import Optional
from flask_sqlalchemy import SQLAlchemy

from app.models import PurchaseOrder, PurchaseOrderItem, GoodsReceiptNote, SupplierProduct

def compute_supplier_fill_rate(supplier_id: UUID, store_id: int, days: int, db: SQLAlchemy) -> float:
    """
    Ratio of received_qty to ordered_qty across fulfilled POs in the period.
    Returns a float between 0.0 and 1.0. Returns 1.0 if no orders exist.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    row = db.session.query(
        func.sum(PurchaseOrderItem.ordered_qty).label('total_ordered'),
        func.sum(PurchaseOrderItem.received_qty).label('total_received')
    ).join(PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.store_id == store_id,
        PurchaseOrder.status == 'FULFILLED',
        PurchaseOrder.updated_at >= cutoff
    ).first()
    
    if not row or not row.total_ordered or row.total_ordered == 0:
        return 1.0
        
    return min(1.0, float(row.total_received) / float(row.total_ordered))


def compute_avg_lead_time(supplier_id: UUID, store_id: int, db: SQLAlchemy) -> Optional[float]:
    """
    Average days between PO creation and GRN receiving.
    Looks at all FULFILLED POs for this supplier.
    """
    rows = db.session.query(
        PurchaseOrder.created_at,
        func.min(GoodsReceiptNote.received_at).label('received_at')
    ).join(GoodsReceiptNote, GoodsReceiptNote.po_id == PurchaseOrder.id).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.store_id == store_id,
        PurchaseOrder.status == 'FULFILLED'
    ).group_by(PurchaseOrder.id, PurchaseOrder.created_at).all()
    
    if not rows:
        return None
        
    lead_times = []
    for r in rows:
        if r.created_at and r.received_at:
            delta = r.received_at - r.created_at
            lead_times.append(delta.total_seconds() / 86400.0)
            
    if not lead_times:
        return None
        
    return sum(lead_times) / len(lead_times)


def compute_price_change_pct(supplier_id: UUID, product_id: int, months: int, db: SQLAlchemy) -> Optional[float]:
    """
    Calculates the percentage change in the unit_price from the supplier over the last N months.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    
    oldest = db.session.query(PurchaseOrderItem.unit_price).join(
        PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id
    ).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrderItem.product_id == product_id,
        PurchaseOrder.created_at >= cutoff
    ).order_by(PurchaseOrder.created_at.asc()).first()
    
    newest = db.session.query(PurchaseOrderItem.unit_price).join(
        PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.id
    ).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrderItem.product_id == product_id
    ).order_by(PurchaseOrder.created_at.desc()).first()
    
    if not oldest or not newest or not oldest.unit_price or not newest.unit_price:
        return None
        
    old_p = float(oldest.unit_price)
    new_p = float(newest.unit_price)
    
    if old_p == 0:
        return 0.0
        
    return ((new_p - old_p) / old_p) * 100.0
