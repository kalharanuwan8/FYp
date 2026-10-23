from marshmallow import Schema, fields, validate

class UserSchema(Schema):
    id = fields.Str(dump_only=True)
    email = fields.Email(required=True)
    first_name = fields.Str(required=True)
    last_name = fields.Str(required=True)
    role = fields.Str(required=True, validate=validate.OneOf(["ADMIN", "TEACHER", "STUDENT"]))
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

class UserCreateSchema(UserSchema):
    password = fields.Str(required=True, validate=validate.Length(min=6))

class ConsentSchema(Schema):
    student_id = fields.Str(required=True)
    guardian_name = fields.Str(required=True)
    guardian_email = fields.Email(required=True)
    consent_granted = fields.Bool(required=True)
