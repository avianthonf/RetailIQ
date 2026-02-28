import logging
import uuid
from datetime import datetime, timezone
from .. import db
from ..models import Transaction, TransactionItem, Product
from app.tasks.tasks import rebuild_daily_aggregates, evaluate_alerts


logger = logging.getLogger(__name__)


def _dispatch_async(task, *args):
    """Queue background work without failing primary transaction flow."""
    try:
        task.delay(*args)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Background task dispatch failed for %s args=%s: %s", getattr(task, 'name', task), args, exc)


def process_single_transaction(data, store_id, is_batch=False, session_id=None):
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
        is_return=False,
        session_id=session_id
    )
    db.session.add(txn)

    grand_total = 0
    for item in data['line_items']:
        product = product_map[item['product_id']]
        from decimal import Decimal
        if product.current_stock is None:
            product.current_stock = Decimal('0')

        product.current_stock -= Decimal(str(item['quantity']))
        if product.current_stock < 0:
            print(f"WARNING: Product {product.product_id} stock went negative: {product.current_stock}")

        qty = item['quantity']
        selling_price = item['selling_price']
        discount = item.get('discount_amount', 0)
        grand_total += (qty * selling_price) - discount

        txn_item = TransactionItem(
            transaction_id=txn.transaction_id,
            product_id=product.product_id,
            quantity=qty,
            selling_price=selling_price,
            original_price=float(product.selling_price) if product.selling_price else selling_price,
            discount_amount=discount,
            cost_price_at_time=float(product.cost_price) if product.cost_price else 0
        )
        db.session.add(txn_item)

    from decimal import Decimal
    payment_mode = data.get('payment_mode')
    customer_id = data.get('customer_id')

    if payment_mode == 'CREDIT' and customer_id:
        from ..models import CreditLedger, CreditTransaction
        ledger = db.session.query(CreditLedger).filter_by(customer_id=customer_id, store_id=store_id).first()
        if not ledger:
            ledger = CreditLedger(customer_id=customer_id, store_id=store_id)
            db.session.add(ledger)
            db.session.flush()

        if Decimal(str(ledger.balance)) + Decimal(str(grand_total)) > Decimal(str(ledger.credit_limit)):
            raise ValueError(f"Credit limit of ₹{ledger.credit_limit} would be exceeded")

        ledger.balance = Decimal(str(ledger.balance)) + Decimal(str(grand_total))
        ledger.updated_at = datetime.now(timezone.utc)
        
        ctxn = CreditTransaction(
            ledger_id=ledger.id,
            transaction_id=txn.transaction_id,
            type='CREDIT_SALE',
            amount=grand_total,
            balance_after=ledger.balance,
            notes=f"Credit sale for transaction {txn.transaction_id}"
        )
        db.session.add(ctxn)

    if customer_id:
        from ..models import LoyaltyProgram, CustomerLoyaltyAccount, LoyaltyTransaction
        program = db.session.query(LoyaltyProgram).filter_by(store_id=store_id, is_active=True).first()
        if program:
            points_earned = Decimal(str(grand_total)) * Decimal(str(program.points_per_rupee))
            if points_earned > 0:
                account = db.session.query(CustomerLoyaltyAccount).filter_by(customer_id=customer_id, store_id=store_id).first()
                if not account:
                    account = CustomerLoyaltyAccount(customer_id=customer_id, store_id=store_id)
                    db.session.add(account)
                    db.session.flush()
                
                account.total_points = Decimal(str(account.total_points)) + points_earned
                account.redeemable_points = Decimal(str(account.redeemable_points)) + points_earned
                account.lifetime_earned = Decimal(str(account.lifetime_earned)) + points_earned
                account.last_activity_at = datetime.now(timezone.utc)
                
                ltxn = LoyaltyTransaction(
                    account_id=account.id,
                    transaction_id=txn.transaction_id,
                    type='EARN',
                    points=points_earned,
                    balance_after=account.total_points,
                    notes=f"Earned from transaction {txn.transaction_id}"
                )
                db.session.add(ltxn)

    # ── GST Transaction Recording ───────────────────────────────────
    from ..models import StoreGSTConfig, GSTTransaction as GSTTxn, HSNMaster, Category
    gst_config = db.session.query(StoreGSTConfig).filter_by(store_id=store_id, is_gst_enabled=True).first()
    if gst_config and gst_config.registration_type == 'REGULAR':
        hsn_breakdown = {}
        total_taxable = Decimal('0')
        total_cgst = Decimal('0')
        total_sgst = Decimal('0')
        total_igst = Decimal('0')

        for item in data['line_items']:
            product = product_map[item['product_id']]
            qty = Decimal(str(item['quantity']))
            sp = Decimal(str(item['selling_price']))
            disc = Decimal(str(item.get('discount_amount', 0)))
            line_total = qty * sp - disc

            # Skip exempt/zero GST categories
            cat = product.gst_category or 'REGULAR'
            if cat in ('EXEMPT', 'ZERO'):
                continue

            # Determine GST rate: product HSN rate or category rate
            gst_rate = Decimal('0')
            hsn_code_val = product.hsn_code or 'NONE'
            if product.hsn_code:
                hsn_entry = db.session.query(HSNMaster).filter_by(hsn_code=product.hsn_code).first()
                if hsn_entry and hsn_entry.default_gst_rate:
                    gst_rate = Decimal(str(hsn_entry.default_gst_rate))
            if gst_rate == 0 and product.category_id:
                category = db.session.query(Category).filter_by(category_id=product.category_id).first()
                if category and category.gst_rate:
                    gst_rate = Decimal(str(category.gst_rate))

            if gst_rate == 0:
                continue

            # Taxable value = line_total / (1 + rate/100)
            taxable = line_total / (1 + gst_rate / 100)
            tax = line_total - taxable

            # Intrastate: CGST = SGST = tax / 2
            cgst = tax / 2
            sgst = tax / 2
            igst = Decimal('0')

            total_taxable += taxable
            total_cgst += cgst
            total_sgst += sgst

            if hsn_code_val not in hsn_breakdown:
                hsn_breakdown[hsn_code_val] = {
                    'taxable': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'rate': float(gst_rate)
                }
            hsn_breakdown[hsn_code_val]['taxable'] += float(round(taxable, 2))
            hsn_breakdown[hsn_code_val]['cgst'] += float(round(cgst, 2))
            hsn_breakdown[hsn_code_val]['sgst'] += float(round(sgst, 2))

        if total_taxable > 0 or total_cgst > 0:
            period_str = txn.created_at.strftime('%Y-%m')
            gst_txn_row = GSTTxn(
                transaction_id=txn.transaction_id,
                store_id=store_id,
                period=period_str,
                taxable_amount=round(total_taxable, 2),
                cgst_amount=round(total_cgst, 2),
                sgst_amount=round(total_sgst, 2),
                igst_amount=round(total_igst, 2),
                total_gst=round(total_cgst + total_sgst + total_igst, 2),
                hsn_breakdown=hsn_breakdown
            )
            db.session.add(gst_txn_row)

    date_str = txn.created_at.strftime('%Y-%m-%d')
    _dispatch_async(rebuild_daily_aggregates, store_id, date_str)
    _dispatch_async(evaluate_alerts, store_id)

    return txn

def process_batch_transactions(transactions_data, store_id, session_id=None):
    accepted = 0
    rejected = 0
    errors = []

    for t_data in transactions_data:
        try:
            with db.session.begin_nested():
                txn = process_single_transaction(t_data, store_id, is_batch=True, session_id=session_id)
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
    _dispatch_async(rebuild_daily_aggregates, store_id, date_str)

    return ret_txn
