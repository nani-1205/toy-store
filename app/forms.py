# File: app/forms.py

from flask_wtf import FlaskForm
# Import FileField and validators
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, IntegerField, DecimalField, HiddenField
# Make FileField optional for editing using Optional validator
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, NumberRange, Optional

from .models import find_user_by_email, find_user_by_username

# --- Other Forms (LoginForm, AdminLoginForm, SignupForm, etc.) ---
# (These remain unchanged)
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')

class AdminLoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Admin Login')

class SignupForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    address = TextAreaField('Address', validators=[Optional(), Length(max=200)])
    phone = StringField('Phone Number', validators=[Optional(), Length(min=10, max=15)])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = find_user_by_username(username.data)
        if user: raise ValidationError('Username taken.')
    def validate_email(self, email):
        user = find_user_by_email(email.data)
        if user: raise ValidationError('Email already registered.')

class AddressPhoneForm(FlaskForm):
    address = TextAreaField('Shipping Address', validators=[DataRequired(), Length(max=200)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    submit = SubmitField('Confirm Order')

class UpdateProfileForm(FlaskForm):
    address = TextAreaField('Address', validators=[DataRequired(), Length(max=200)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    submit = SubmitField('Update Profile')

class CartUpdateForm(FlaskForm):
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Update')
# --- End Other Forms ---


# --- Toy Form (Updated for File Upload) ---
class ToyForm(FlaskForm):
    name = StringField('Toy Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = DecimalField('Price (INR)', places=2, validators=[DataRequired(), NumberRange(min=0)])
    # Changed from StringField to FileField
    image = FileField('Toy Image (JPG, PNG, GIF)', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Only image files (jpg, png, gif) are allowed!'),
        # Make it optional here; requirement handled in route logic
        Optional()
    ])
    stock = IntegerField('Stock Quantity', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Save Toy')