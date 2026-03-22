from marshmallow import Schema, ValidationError, fields, validate, validates_schema


class RegisterSchema(Schema):
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    password = fields.String(required=True, validate=validate.Length(min=6))
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
    store_name = fields.String(required=False, validate=validate.Length(max=100))
    email = fields.Email(required=True)
    role = fields.String(
        required=False, validate=validate.OneOf(["owner", "staff"])
    )  # usually registration is owner, but allowing flexibility


class LoginSchema(Schema):
    email = fields.Email(required=False)
    mobile_number = fields.String(required=False, validate=validate.Length(min=10, max=15))
    password = fields.String(required=False)
    mfa_code = fields.String(required=False, validate=validate.Length(equal=6))

    @validates_schema
    def validate_login_identifier(self, data, **kwargs):
        email = data.get("email")
        mobile_number = data.get("mobile_number")
        password = data.get("password")

        if email:
            return

        if mobile_number and password:
            return

        raise ValidationError("Email is required for OTP login", field_name="email")


class MfaSetupSchema(Schema):
    password = fields.String(required=True)


class MfaVerifySchema(Schema):
    mfa_code = fields.String(required=True, validate=validate.Length(equal=6))


class OTPSchema(Schema):
    email = fields.Email(required=False)
    mobile_number = fields.String(required=False, validate=validate.Length(min=10, max=15))
    otp = fields.String(required=True, validate=validate.Length(equal=6))

    @validates_schema
    def validate_identifier(self, data, **kwargs):
        if data.get("email") or data.get("mobile_number"):
            return
        raise ValidationError("Email is required for OTP verification", field_name="email")


class RefreshSchema(Schema):
    refresh_token = fields.String(required=True)


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=False)
    mobile_number = fields.String(required=False, validate=validate.Length(min=10, max=15))

    @validates_schema
    def validate_identifier(self, data, **kwargs):
        if data.get("email") or data.get("mobile_number"):
            return
        raise ValidationError("Email is required for password reset", field_name="email")


class ResetPasswordSchema(Schema):
    token = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=6))


class TeamInviteSchema(Schema):
    # The role that the new team member will have. 'staff' by default
    role = fields.String(required=False, validate=validate.OneOf(["staff"]), dump_default="staff")


class TeamJoinSchema(Schema):
    invite_code = fields.String(required=True, validate=validate.Length(equal=6))
    mobile_number = fields.String(required=True, validate=validate.Length(min=10, max=15))
    password = fields.String(required=True, validate=validate.Length(min=6))
    full_name = fields.String(required=True, validate=validate.Length(min=2, max=100))
