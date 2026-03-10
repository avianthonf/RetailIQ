from marshmallow import Schema, fields, validate


class LoyaltyProgramUpsertSchema(Schema):
    points_per_rupee = fields.Float(validate=validate.Range(min=0))
    redemption_rate = fields.Float(validate=validate.Range(min=0))
    min_redemption_points = fields.Int(validate=validate.Range(min=0))
    expiry_days = fields.Int(validate=validate.Range(min=1))
    is_active = fields.Bool()


class RedeemPointsSchema(Schema):
    points_to_redeem = fields.Float(required=True, validate=validate.Range(min=0.01))
    transaction_id = fields.UUID(allow_none=True, load_default=None)


class RepayCreditSchema(Schema):
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    notes = fields.String(allow_none=True, load_default=None)
