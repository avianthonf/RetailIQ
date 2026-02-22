import uuid
from datetime import datetime, timezone
from .. import db
from ..models import Transaction, TransactionItem, Product
from .tasks import rebuild_daily_aggregates, evaluate_alerts

def process_single_transaction(data, store_id, is_batch=False):
    # Check idempotency
    existing_txn = db.session.query(Transaction).filter_by(transaction_id=data['transaction_id']).first()
    if existing_txn:
        if is_batch:
            return None
        else:
            raise ValueError("Transaction ID already exists")

    product_ids = [item['product_id'] for item in data['line_items']]
    products = db.session.query(Product).filter(
        Product.store_id == store_id,
        Product.product_id.in_(product_ids)
    ).all()
    product_map = {p.product_id: p for p in products}

    missing_products = set(product_ids) - set(product_map.keys())
    if missing_products:
        raise ValueError(f"Products not found: {missing_products}")

    txn = Transaction(
        transaction_id=data['transaction_id'],
        store_id=store_id,
        customer_id=data.get('customer_id'),
        payment_mode=data['payment_mode'],
        notes=data.get('notes'),
        created_at=data['timestamp'].replace(tzinfo=timezone.utc) if data['timestamp'].tzinfo is None else data['timestamp'],
        is_return=False
    )
    db.session.add(txn)

    for item in data['line_items']:
        product = product_map[item['product_id']]
        from decimal import Decimal
        if product.current_stock is None:
            product.current_stock = Decimal('0')

        product.current_stock -= Decimal(str(item['quantity']))
        if product.current_stock < 0:
            print(f"WARNING: Product {product.product_id} stock went negative: {product.current_stock}")

        txn_item = TransactionItem(
            transaction_id=txn.transaction_id,
            product_id=product.product_id,
            quantity=item['quantity'],
            selling_price=item['selling_price'],
            original_price=float(product.selling_price) if product.selling_price else item['selling_price'],
            discount_amount=item.get('discount_amount', 0),
            cost_price_at_time=float(product.cost_price) if product.cost_price else 0
        )
        db.session.add(txn_item)

    date_str = txn.created_at.strftime('%Y-%m-%d')
    rebuild_daily_aggregates.delay(store_id, date_str)
    evaluate_alerts.delay(store_id)

    return txn

def process_batch_transactions(transactions_data, store_id):
    accepted = 0
    rejected = 0
    errors = []

    for t_data in transactions_data:
        try:
            with db.session.begin_nested():
                txn = process_single_transaction(t_data, store_id, is_batch=True)
                if txn:
                    accepted += 1
        except Exception as e:
            rejected += 1
            errors.append({"transaction_id": str(t_data.get('transaction_id')), "error": str(e)})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors
    }

def process_return_transaction(original_txn_id, return_data, store_id):
    original_txn = db.session.query(Transaction).filter_by(
        transaction_id=original_txn_id, store_id=store_id
    ).first()

    if not original_txn:
        raise ValueError("Original transaction not found or does not belong to this store")

    return_txn_id = uuid.uuid4()

    ret_txn = Transaction(
        transaction_id=return_txn_id,
        store_id=store_id,
        customer_id=original_txn.customer_id,
        payment_mode=original_txn.payment_mode,
        notes=f"Return for {original_txn_id}",
        created_at=datetime.now(timezone.utc),
        is_return=True,
        original_transaction_id=original_txn_id
    )
    db.session.add(ret_txn)

    product_ids = [item['product_id'] for item in return_data['items']]
    products = db.session.query(Product).filter(
        Product.store_id == store_id,
        Product.product_id.in_(product_ids)
    ).all()
    product_map = {p.product_id: p for p in products}

    original_items = db.session.query(TransactionItem).filter_by(transaction_id=original_txn_id).all()
    orig_item_map = {item.product_id: item for item in original_items}

    for item_data in return_data['items']:
        product_id = item_data['product_id']
        qty_returned = item_data['quantity_returned']

        if product_id not in orig_item_map:
            raise ValueError(f"Product {product_id} not in original transaction")

        orig_item = orig_item_map[product_id]

        if qty_returned > orig_item.quantity:
            raise ValueError(f"Cannot return more than originally purchased for product {product_id}")

        product = product_map.get(product_id)
        if product:
            from decimal import Decimal
            if product.current_stock is None:
                product.current_stock = Decimal('0')
            product.current_stock += Decimal(str(qty_returned))

        ret_txn_item = TransactionItem(
            transaction_id=return_txn_id,
            product_id=product_id,
            quantity=-qty_returned,
            selling_price=orig_item.selling_price,
            original_price=orig_item.original_price,
            discount_amount=0,
            cost_price_at_time=orig_item.cost_price_at_time
        )
        db.session.add(ret_txn_item)

    date_str = ret_txn.created_at.strftime('%Y-%m-%d')
    rebuild_daily_aggregates.delay(store_id, date_str)

    return ret_txn
