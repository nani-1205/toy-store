from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash # Use werkzeug instead of flask_bcrypt for admin check

from . import auth_bp
from .. import mongo, bcrypt, login_manager
from ..forms import LoginForm, SignupForm, AdminLoginForm
from ..models import find_user_by_email, create_user, find_user_by_username

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and not session.get('is_admin'):
        return redirect(url_for('customer.dashboard'))
    if session.get('is_admin'):
         return redirect(url_for('admin.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user_data = find_user_by_email(form.email.data)
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            if user_data.get('is_approved', False):
                # Load user properly using the loader
                user_obj = login_manager._user_callback(str(user_data['_id']))
                if user_obj:
                    login_user(user_obj, remember=form.remember.data)
                    flash('Login successful!', 'success')
                    next_page = request.args.get('next')
                    return redirect(next_page or url_for('customer.dashboard'))
                else:
                    flash('Error loading user profile.', 'danger') # Should not happen if loader is correct
            else:
                flash('Your account is pending admin approval. Please wait.', 'warning')
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Customer Login', form=form)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # Or customer dashboard

    form = SignupForm()
    if form.validate_on_submit():
        user_id = create_user(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data,
            address=form.address.data,
            phone=form.phone.data
        )
        if user_id:
            flash('Account created successfully! Please wait for admin approval.', 'success')
            return redirect(url_for('auth.login'))
        else:
            # Error message (e.g., duplicate) handled by model/forms, show generic error
             flash('Account creation failed. Please try again.', 'danger')
    # else: # Debug form errors
    #     if form.errors:
    #         print("Signup Form Errors:", form.errors)

    return render_template('signup.html', title='Sign Up', form=form)

@auth_bp.route('/logout')
@login_required # Must be logged in to log out
def logout():
    # Clear admin flag if it exists
    session.pop('is_admin', None)
    logout_user()
    session.pop('cart', None) # Clear cart on logout
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))

# --- Admin Login ---
@auth_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'):
        return redirect(url_for('admin.dashboard'))
    # Prevent logged-in customers from accessing admin login
    if current_user.is_authenticated and not session.get('is_admin'):
         flash('Customers cannot access the admin login page.', 'warning')
         return redirect(url_for('main.index'))


    form = AdminLoginForm()
    if form.validate_on_submit():
        admin_user = current_app.config['ADMIN_USERNAME']
        # SECURITY WARNING: Comparing plain text passwords is bad practice!
        # In a real app, hash the admin password stored in config/env.
        admin_pass = current_app.config['ADMIN_PASSWORD']

        # Simplified check against .env values
        if form.username.data == admin_user and form.password.data == admin_pass:
            session['is_admin'] = True # Set admin flag in session
            # Use the user_loader to load a dummy admin user for context
            admin_obj = login_manager._user_callback("admin")
            if admin_obj:
                 login_user(admin_obj) # Log in the admin representation
                 flash('Admin login successful!', 'success')
                 return redirect(url_for('admin.dashboard'))
            else:
                 flash('Failed to initialize admin session.', 'danger')

        else:
            flash('Invalid admin credentials.', 'danger')
    return render_template('admin_login.html', title='Admin Login', form=form)

@auth_bp.route('/admin_logout')
def admin_logout():
    if session.get('is_admin'):
        session.pop('is_admin', None)
        logout_user() # Logs out the dummy admin user
        flash('Admin logged out successfully.', 'info')
    return redirect(url_for('auth.admin_login'))

# --- Unauthorized Handler ---
@login_manager.unauthorized
def unauthorized():
    # Decide where to redirect based on the request path
    if request.blueprint == 'admin':
        flash('You need to log in as an admin to access this page.', 'warning')
        return redirect(url_for('auth.admin_login'))
    else:
        flash('You need to log in to access this page.', 'info')
        return redirect(url_for('auth.login', next=request.url))