from marshmallow import Schema, fields, validate


class StoreProfileSchema(Schema):
    store_id = fields.Int(dump_only=True)
    owner_user_id = fields.Int(dump_only=True)
    store_name = fields.Str(validate=validate.Length(min=1, max=100))
    store_type = fields.Str(
        validate=validate.OneOf(["grocery", "pharmacy", "general", "electronics", "clothing", "other"])
    )
    city = fields.Str(validate=validate.Length(max=100))
    state = fields.Str(validate=validate.Length(max=100))
    gst_number = fields.Str(validate=validate.Length(max=15))
    currency_symbol = fields.Str(validate=validate.Length(max=5))
    working_days = fields.Dict(keys=fields.Str(), values=fields.Bool())
    opening_time = fields.Time()
    closing_time = fields.Time()
    timezone = fields.Str(validate=validate.Length(max=50))


class CategorySchema(Schema):
    category_id = fields.Int(dump_only=True)
    store_id = fields.Int(dump_only=True)
    name = fields.Str(validate=validate.Length(min=1, max=100), required=True)
    color_tag = fields.Str(validate=validate.Length(max=20), load_default=None)
    is_active = fields.Bool(load_default=True)
    gst_rate = fields.Float(validate=validate.Range(min=0, max=100), load_default=0.0)


class TaxConfigItemSchema(Schema):
    category_id = fields.Int(required=True)
    gst_rate = fields.Float(validate=validate.Range(min=0, max=100), required=True)


class TaxConfigSchema(Schema):
    taxes = fields.List(fields.Nested(TaxConfigItemSchema), required=True)
