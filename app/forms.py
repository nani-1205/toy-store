from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, IntegerField, DecimalField, HiddenField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, NumberRange, Optional, URL

from .models import find_user_by_email, find_user_by_username

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

    # Custom validators to check uniqueness
    def validate_username(self, username):
        user = find_user_by_username(username.data)
        if user:
            raise ValidationError('That username is already taken. Please choose a different one.')

    def validate_email(self, email):
        user = find_user_by_email(email.data)
        if user:
            raise ValidationError('That email is already registered. Please use a different one or login.')

class ToyForm(FlaskForm):
    name = StringField('Toy Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = DecimalField('Price (INR)', places=2, validators=[DataRequired(), NumberRange(min=0)])
    image_url = StringField('Image URL', validators=[DataRequired(), URL(), Length(max=500)]) # Simple URL for now
    stock = IntegerField('Stock Quantity', validators=[DataRequired(), NumberRange(min=0)])
    submit = SubmitField('Save Toy')

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
    # No CSRF needed usually if submitted via JS/simple link, but good practice for forms
    # Add CSRF token manually if needed for non-form POSTs