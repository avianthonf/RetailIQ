from marshmallow import Schema, fields


class CreateStoreGroupSchema(Schema):
    name = fields.String(required=True)


class AddStoreToGroupSchema(Schema):
    store_id = fields.Integer(required=True)
    manager_user_id = fields.Integer(required=False, allow_none=True)


class ConfirmTransferSchema(Schema):
    suggested_qty = fields.Float(required=False, allow_none=True)
