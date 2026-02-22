from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class ProductCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    category_id = fields.Int(load_default=None)
    sku_code = fields.Str(load_default=None, allow_none=True)
    uom = fields.Str(
        load_default=None,
        validate=validate.OneOf(['pieces', 'kg', 'litre', 'pack'])
    )
    cost_price = fields.Float(required=True)
    selling_price = fields.Float(required=True)
    current_stock = fields.Float(load_default=0.0)
    reorder_level = fields.Float(load_default=0.0)
    supplier_name = fields.Str(load_default=None)
    barcode = fields.Str(load_default=None)
    image_url = fields.Str(load_default=None)
    lead_time_days = fields.Int(load_default=3)

    @validates_schema
    def validate_prices(self, data, **kwargs):
        if data.get('selling_price') is not None and data.get('cost_price') is not None:
            if data['selling_price'] < data['cost_price']:
                raise ValidationError(
                    'selling_price must be >= cost_price',
                    field_name='selling_price'
                )


class ProductUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=255))
    category_id = fields.Int(allow_none=True)
    sku_code = fields.Str(allow_none=True)
    uom = fields.Str(
        allow_none=True,
        validate=validate.OneOf(['pieces', 'kg', 'litre', 'pack'])
    )
    cost_price = fields.Float()
    selling_price = fields.Float()
    reorder_level = fields.Float()
    supplier_name = fields.Str(allow_none=True)
    barcode = fields.Str(allow_none=True)
    image_url = fields.Str(allow_none=True)
    lead_time_days = fields.Int()
    is_active = fields.Bool()


class StockUpdateSchema(Schema):
    quantity_added = fields.Float(required=True)
    purchase_price = fields.Float(required=True)
    date = fields.Str(load_default=None)          # YYYY-MM-DD string, optional
    supplier_name = fields.Str(load_default=None)
    update_cost_price = fields.Bool(load_default=False)


class StockAuditItemSchema(Schema):
    product_id = fields.Int(required=True)
    actual_qty = fields.Float(required=True)


class StockAuditSchema(Schema):
    items = fields.List(fields.Nested(StockAuditItemSchema), required=True, validate=validate.Length(min=1))
    notes = fields.Str(load_default=None)
