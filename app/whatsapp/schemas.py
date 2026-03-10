from marshmallow import Schema, fields, validate


class WhatsAppConfigUpsertSchema(Schema):
    phone_number_id = fields.String(required=False, allow_none=True)
    access_token = fields.String(required=False, allow_none=True)
    webhook_verify_token = fields.String(required=False, allow_none=True)
    is_active = fields.Boolean(required=False)
    waba_id = fields.String(required=False, allow_none=True)


class SendAlertSchema(Schema):
    alert_id = fields.Integer(required=True)


class SendPOSchema(Schema):
    po_id = fields.String(required=True)
