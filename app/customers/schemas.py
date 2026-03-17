import re

from marshmallow import Schema, ValidationError, fields, validate, validates

MOBILE_RE = re.compile(r"^\d{10,15}$")


class CustomerCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    mobile_number = fields.Str(required=True)
    email = fields.Str(load_default=None, allow_none=True)
    gender = fields.Str(load_default=None, allow_none=True, validate=validate.OneOf(["male", "female", "other"]))
    birth_date = fields.Date(load_default=None, allow_none=True)  # YYYY-MM-DD
    address = fields.Str(load_default=None, allow_none=True)
    notes = fields.Str(load_default=None, allow_none=True)

    @validates("mobile_number")
    def validate_mobile(self, value, **kwargs):
        if not MOBILE_RE.match(value):
            raise ValidationError("mobile_number must be 10–15 digits.")


class CustomerUpdateSchema(Schema):
    name = fields.Str(validate=validate.Length(min=1, max=255))
    mobile_number = fields.Str()
    email = fields.Str(allow_none=True)
    gender = fields.Str(allow_none=True, validate=validate.OneOf(["male", "female", "other"]))
    birth_date = fields.Date(allow_none=True)
    address = fields.Str(allow_none=True)
    notes = fields.Str(allow_none=True)

    @validates("mobile_number")
    def validate_mobile(self, value, **kwargs):
        if value and not MOBILE_RE.match(value):
            raise ValidationError("mobile_number must be 10–15 digits.")
