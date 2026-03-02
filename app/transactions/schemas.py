from marshmallow import Schema, fields, validate


class TransactionItemCreateSchema(Schema):
    product_id = fields.Int(required=True)
    quantity = fields.Float(required=True, validate=validate.Range(min=0.001))
    selling_price = fields.Float(required=True, validate=validate.Range(min=0))
    discount_amount = fields.Float(load_default=0)

class TransactionCreateSchema(Schema):
    transaction_id = fields.UUID(required=True)
    timestamp = fields.DateTime(required=True)
    payment_mode = fields.String(required=True, validate=validate.OneOf(['CASH', 'UPI', 'CARD', 'CREDIT']))
    customer_id = fields.Int(allow_none=True, load_default=None)
    notes = fields.String(allow_none=True, validate=validate.Length(max=200), load_default=None)
    line_items = fields.List(fields.Nested(TransactionItemCreateSchema), required=True, validate=validate.Length(min=1))

class BatchTransactionCreateSchema(Schema):
    transactions = fields.List(fields.Nested(TransactionCreateSchema), required=True, validate=validate.Length(min=1, max=500))

class ReturnItemSchema(Schema):
    product_id = fields.Int(required=True)
    quantity_returned = fields.Float(required=True, validate=validate.Range(min=0.001))
    reason = fields.String(allow_none=True, load_default=None)

class TransactionReturnSchema(Schema):
    items = fields.List(fields.Nested(ReturnItemSchema), required=True, validate=validate.Length(min=1))
