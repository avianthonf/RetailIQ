from marshmallow import Schema, fields, validate


class GSTConfigUpsertSchema(Schema):
    gstin = fields.String(required=False, allow_none=True, validate=validate.Length(max=15))
    registration_type = fields.String(
        required=False,
        validate=validate.OneOf(['REGULAR', 'COMPOSITION', 'UNREGISTERED'])
    )
    state_code = fields.String(required=False, validate=validate.Length(max=2))
    is_gst_enabled = fields.Boolean(required=False)
