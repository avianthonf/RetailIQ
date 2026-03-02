import os
import uuid

from flask import current_app, g, jsonify, request

from app import db, limiter
from app.auth.decorators import require_auth
from app.models import OcrJob, OcrJobItem, Product, StockAdjustment
from app.tasks.tasks import process_ocr_job
from app.vision import vision_bp

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def _store_key_func():
    """Rate limit key: use store_id from JWT if available, else IP."""
    user = getattr(g, 'current_user', None)
    if user and 'store_id' in user:
        return f"store:{user['store_id']}"
    return request.remote_addr

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@vision_bp.route('/api/v1/vision/ocr/upload', methods=['POST'])
@require_auth
@limiter.limit("20/hour", key_func=_store_key_func)
def upload_invoice():
    user = g.current_user
    if 'invoice_image' not in request.files:
        return jsonify({"message": "No invoice_image part"}), 400

    file = request.files['invoice_image']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"message": "Unsupported Media Type"}), 415

    # Check size
    file.seek(0, os.SEEK_END)
    size = file.tell()
    if size > MAX_FILE_SIZE:
        return jsonify({"message": "Payload Too Large. Max size 10MB."}), 413
    file.seek(0)

    store_id = user['store_id']
    job_uuid = uuid.uuid4()

    # Save file
    upload_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'ocr', str(store_id))
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"{job_uuid}.jpg"
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    # Create DB Job
    job = OcrJob(
        id=job_uuid,
        store_id=store_id,
        image_path=file_path,
        status='QUEUED'
    )
    db.session.add(job)
    db.session.commit()

    # Enqueue task
    process_ocr_job.delay(str(job_uuid))

    return jsonify({"job_id": str(job_uuid)}), 201

@vision_bp.route('/api/v1/vision/ocr/<uuid:job_id>', methods=['GET'])
@require_auth
def get_job_status(job_id):
    user = g.current_user
    job = db.session.get(OcrJob, job_id)
    if not job or job.store_id != user['store_id']:
        return jsonify({"message": "Job not found"}), 404

    items = OcrJobItem.query.filter_by(job_id=job_id).all()
    items_data = []
    for item in items:
        # Get product name using product_id
        product_name = None
        if item.matched_product_id:
            prod = db.session.get(Product, item.matched_product_id)
            if prod:
                product_name = prod.name

        items_data.append({
            "item_id": str(item.id),
            "raw_text": item.raw_text,
            "matched_product_id": item.matched_product_id,
            "product_name": product_name,
            "confidence": float(item.confidence) if item.confidence else None,
            "quantity": float(item.quantity) if item.quantity else None,
            "unit_price": float(item.unit_price) if item.unit_price else None,
            "is_confirmed": item.is_confirmed
        })

    return jsonify({
        "job_id": str(job.id),
        "status": job.status,
        "error_message": job.error_message,
        "items": items_data
    }), 200

@vision_bp.route('/api/v1/vision/ocr/<uuid:job_id>/confirm', methods=['POST'])
@require_auth
def confirm_job(job_id):
    from decimal import Decimal
    user = g.current_user
    job = db.session.get(OcrJob, job_id)
    if not job or job.store_id != user['store_id']:
        return jsonify({"message": "Job not found"}), 404

    if job.status != 'REVIEW':
        return jsonify({"message": "Job is not in REVIEW status"}), 400

    data = request.json
    confirmed_items = data.get('confirmed_items', [])

    try:
        for c_item in confirmed_items:
            item_id = c_item.get('item_id')
            qty = c_item.get('quantity')
            pid = c_item.get('matched_product_id')

            # Fetch DB Item
            job_item = db.session.get(OcrJobItem, uuid.UUID(item_id))
            if not job_item or job_item.job_id != job.id:
                raise ValueError(f"Invalid item_id: {item_id}")

            product = db.session.get(Product, pid)
            if not product or product.store_id != user['store_id']:
                raise ValueError(f"Invalid product_id: {pid}")

            if not qty or float(qty) <= 0:
                raise ValueError(f"Invalid quantity: {qty}")

            # Update item
            job_item.is_confirmed = True
            job_item.matched_product_id = pid
            job_item.quantity = qty
            if 'unit_price' in c_item:
                job_item.unit_price = c_item['unit_price']

            # Update Stock
            current = product.current_stock or Decimal('0')
            product.current_stock = current + Decimal(str(qty))

            # Log Transaction
            tx = StockAdjustment(
                product_id=product.product_id,
                quantity_added=float(qty),
                adjusted_by=user.get('user_id'),
                reason=f"OCR Intake Confirmation (Job: {job.id})"
            )
            db.session.add(tx)

        job.status = 'APPLIED'
        db.session.commit()
        return jsonify({"message": "Stock updated successfully"}), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({"message": str(e)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"message": "An error occurred during confirmation"}), 500

@vision_bp.route('/api/v1/vision/ocr/<uuid:job_id>/dismiss', methods=['POST'])
@require_auth
def dismiss_job(job_id):
    user = g.current_user
    job = db.session.get(OcrJob, job_id)
    if not job or job.store_id != user['store_id']:
        return jsonify({"message": "Job not found"}), 404

    if job.status not in ('REVIEW', 'QUEUED', 'PROCESSING'):
        return jsonify({"message": "Job cannot be dismissed in its current state"}), 400

    job.status = 'FAILED'
    job.error_message = 'Dismissed by user'
    db.session.commit()
    return jsonify({"message": "Job dismissed"}), 200
