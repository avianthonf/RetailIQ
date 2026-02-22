from flask import request, g
from datetime import datetime, date
from marshmallow import ValidationError
from . import transactions_bp
from .schemas import TransactionCreateSchema, BatchTransactionCreateSchema, TransactionReturnSchema
from .services import process_single_transaction, process_batch_transactions, process_return_transaction
from ..auth.decorators import require_auth, require_role
from ..auth.utils import format_response
from ..models import Transaction, TransactionItem, Product
from .. import db
from sqlalchemy import func

@transactions_bp.route('', methods=['POST'])
@require_auth
def create_transaction():
    try:
        data = TransactionCreateSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    store_id = g.current_user['store_id']
    
    try:
        txn = process_single_transaction(data, store_id)
        db.session.commit()
        return format_response(True, data={"transaction_id": str(txn.transaction_id)}), 201
    except ValueError as e:
        db.session.rollback()
        return format_response(False, error={"code": "BAD_REQUEST", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500

@transactions_bp.route('/batch', methods=['POST'])
@require_auth
def create_batch_transactions():
    try:
        data = BatchTransactionCreateSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    store_id = g.current_user['store_id']
    
    result = process_batch_transactions(data['transactions'], store_id)
    db.session.commit()
    return format_response(True, data=result), 200

@transactions_bp.route('', methods=['GET'])
@require_auth
def get_transactions():
    store_id = g.current_user['store_id']
    role = g.current_user['role']
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    payment_mode = request.args.get('payment_mode')
    customer_id = request.args.get('customer_id')
    
    query = db.session.query(Transaction).filter(Transaction.store_id == store_id)
    
    if role == 'staff':
        # Enforce today only
        today = date.today()
        query = query.filter(func.date(Transaction.created_at) == today)
    else:
        if start_date:
            query = query.filter(func.date(Transaction.created_at) >= start_date)
        if end_date:
            query = query.filter(func.date(Transaction.created_at) <= end_date)
            
    if payment_mode:
        query = query.filter(Transaction.payment_mode == payment_mode)
    if customer_id:
        query = query.filter(Transaction.customer_id == customer_id)
        
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')
    
    if min_amount or max_amount:
        amount_subq = db.session.query(
            TransactionItem.transaction_id,
            func.sum(TransactionItem.quantity * TransactionItem.selling_price - TransactionItem.discount_amount).label('total')
        ).group_by(TransactionItem.transaction_id).subquery()
        
        query = query.join(amount_subq, Transaction.transaction_id == amount_subq.c.transaction_id)
        
        if min_amount:
            query = query.filter(amount_subq.c.total >= float(min_amount))
        if max_amount:
            query = query.filter(amount_subq.c.total <= float(max_amount))
            
    total = query.count()
    transactions = query.order_by(Transaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for t in transactions:
        result.append({
            "transaction_id": str(t.transaction_id),
            "created_at": t.created_at.isoformat(),
            "payment_mode": t.payment_mode,
            "customer_id": t.customer_id,
            "is_return": t.is_return,
        })
        
    meta = {
        "page": page,
        "page_size": page_size,
        "total": total
    }
    
    return format_response(True, data=result, meta=meta), 200

@transactions_bp.route('/<uuid:id>', methods=['GET'])
@require_auth
def get_transaction(id):
    store_id = g.current_user['store_id']
    txn = db.session.query(Transaction).filter_by(transaction_id=id, store_id=store_id).first()
    
    if not txn:
        return format_response(False, error={"code": "NOT_FOUND", "message": "Transaction not found"}), 404
        
    items = db.session.query(TransactionItem).filter_by(transaction_id=txn.transaction_id).all()
    
    items_data = []
    for item in items:
        product = db.session.query(Product).filter_by(product_id=item.product_id).first()
        items_data.append({
            "product_id": item.product_id,
            "product_name": product.name if product else None,
            "quantity": float(item.quantity) if item.quantity else 0,
            "selling_price": float(item.selling_price) if item.selling_price else 0,
            "discount_amount": float(item.discount_amount) if item.discount_amount else 0,
        })
        
    data = {
        "transaction_id": str(txn.transaction_id),
        "created_at": txn.created_at.isoformat(),
        "payment_mode": txn.payment_mode,
        "customer_id": txn.customer_id,
        "notes": txn.notes,
        "is_return": txn.is_return,
        "original_transaction_id": str(txn.original_transaction_id) if txn.original_transaction_id else None,
        "line_items": items_data
    }
    
    return format_response(True, data=data), 200

@transactions_bp.route('/<uuid:id>/return', methods=['POST'])
@require_auth
@require_role('owner')
def return_transaction(id):
    try:
        data = TransactionReturnSchema().load(request.json)
    except ValidationError as err:
        return format_response(False, error={"code": "VALIDATION_ERROR", "message": err.messages}), 400
        
    store_id = g.current_user['store_id']
    
    try:
        ret_txn = process_return_transaction(id, data, store_id)
        db.session.commit()
        return format_response(True, data={"return_transaction_id": str(ret_txn.transaction_id)}), 201
    except ValueError as e:
        db.session.rollback()
        return format_response(False, error={"code": "BAD_REQUEST", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return format_response(False, error={"code": "SERVER_ERROR", "message": str(e)}), 500

@transactions_bp.route('/summary/daily', methods=['GET'])
@require_auth
def get_daily_summary():
    store_id = g.current_user['store_id']
    date_str = request.args.get('date', date.today().isoformat())
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return format_response(False, error={"code": "INVALID_DATE", "message": "Date must be YYYY-MM-DD"}), 400
        
    query = db.session.query(Transaction).filter(
        Transaction.store_id == store_id,
        func.date(Transaction.created_at) == target_date
    )
    
    txns = query.all()
    txn_ids = [t.transaction_id for t in txns]
    
    returns_count = sum(1 for t in txns if t.is_return)
    transaction_count = len(txns) - returns_count
    
    revenue_by_mode = {}
    items = []
    if txn_ids:
        items = db.session.query(TransactionItem).filter(TransactionItem.transaction_id.in_(txn_ids)).all()
        
    total_rev = 0
    total_cost = 0
    product_sales = {}
    
    txn_map = {t.transaction_id: t for t in txns}
    
    for item in items:
        txn = txn_map[item.transaction_id]
        
        qty = float(item.quantity)
        rev = qty * float(item.selling_price) - float(item.discount_amount)
        cost = qty * float(item.cost_price_at_time) if item.cost_price_at_time else 0
        
        mode = txn.payment_mode
        revenue_by_mode[mode] = revenue_by_mode.get(mode, 0) + rev
        
        # Don't add to product sales for returns (negative quantity), but we process revenue/cost directly
        if not txn.is_return:
            product_sales[item.product_id] = product_sales.get(item.product_id, 0) + qty
            total_rev += rev
            total_cost += cost
        else:
            # Returns are negative
            total_rev += rev
            total_cost += cost
            
    gross_profit = total_rev - total_cost
    avg_basket = total_rev / transaction_count if transaction_count > 0 else 0
    
    top_product_ids = sorted(product_sales.keys(), key=lambda k: product_sales[k], reverse=True)[:5]
    top_5_products = []
    if top_product_ids:
        products = db.session.query(Product).filter(Product.product_id.in_(top_product_ids)).all()
        p_map = {p.product_id: p for p in products}
        for pid in top_product_ids:
            if pid in p_map:
                top_5_products.append({
                    "product_id": pid,
                    "name": p_map[pid].name,
                    "quantity_sold": product_sales[pid]
                })
                
    summary = {
        "revenue_by_payment_mode": revenue_by_mode,
        "top_5_products": top_5_products,
        "transaction_count": transaction_count,
        "avg_basket": avg_basket,
        "gross_profit": gross_profit,
        "returns_count": returns_count
    }
    
    return format_response(True, data=summary), 200
