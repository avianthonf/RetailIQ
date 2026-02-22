from marshmallow import Schema, fields, validate

class RegisterSchema(Schema):
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    password = fields.String(required=True, validate=validate.Length(min=6))
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    store_name = fields.String(required=False, validate=validate.Length(max=100))
    email = fields.Email(required=False)
    role = fields.String(required=False, validate=validate.OneOf(['owner', 'staff'])) # usually registration is owner, but allowing flexibility

class LoginSchema(Schema):
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    password = fields.String(required=True)

class OTPSchema(Schema):
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    otp = fields.String(required=True, validate=validate.Length(equal=6))

class RefreshSchema(Schema):
    refresh_token = fields.String(required=True)

class ForgotPasswordSchema(Schema):
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))

class ResetPasswordSchema(Schema):
    token = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=6))

class TeamInviteSchema(Schema):
    # The role that the new team member will have. 'staff' by default
    role = fields.String(required=False, validate=validate.OneOf(['staff']), default='staff')

class TeamJoinSchema(Schema):
    invite_code = fields.String(required=True, validate=validate.Length(equal=6))
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    password = fields.String(required=True, validate=validate.Length(min=6))
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
