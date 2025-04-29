from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash # Use werkzeug for admin plain text check

from . import auth_bp
from .. import mongo, bcrypt, login_manager # login_manager might not be needed directly here anymore
from ..forms import LoginForm, SignupForm, AdminLoginForm
from ..models import find_user_by_email, create_user, find_user_by_username, find_user_by_id

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if already logged in (handle admin/customer separately)
    if current_user.is_authenticated:
        if session.get('is_admin') and hasattr(current_user, 'is_admin') and current_user.is_admin():
             return redirect(url_for('admin.dashboard'))
        elif not session.get('is_admin'):
             return redirect(url_for('customer.dashboard'))
        else:
            # Edge case: Session says admin, but user object isn't? Logout.
             logout_user()
             session.clear()


    form = LoginForm()
    if form.validate_on_submit():
        user_data = find_user_by_email(form.email.data)
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            if user_data.get('is_approved', False):
                # Load user properly using the user_loader callback from __init__.py
                # The user_loader is called implicitly by login_user
                user_obj = load_user(str(user_data['_id'])) # Explicit call might also work but login_user does it
                if user_obj:
                    # Log the user in. Flask-Login handles the session.
                    login_user(user_obj, remember=form.remember.data)
                    session['is_admin'] = False # Ensure admin flag is false for customer
                    flash('Login successful!', 'success')
                    next_page = request.args.get('next')
                    # Prevent open redirect vulnerability
                    # Add check here if next_page is internal
                    return redirect(next_page or url_for('customer.dashboard'))
                else:
                    # This case should ideally not happen if load_user is correct
                    flash('Error loading user profile after validation.', 'danger')
            else:
                flash('Your account is pending admin approval. Please wait.', 'warning')
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Customer Login', form=form)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated and not session.get('is_admin'):
        return redirect(url_for('customer.dashboard'))
    if session.get('is_admin'):
         return redirect(url_for('admin.dashboard'))


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
            # Specific error (like duplicate) should be caught by form validation,
            # This handles other potential DB errors during creation
             flash('Account creation failed due to a server issue. Please try again.', 'danger')
    # else: # Debug form errors if needed
    #     if form.errors:
    #         print("Signup Form Errors:", form.errors)

    return render_template('signup.html', title='Sign Up', form=form)

@auth_bp.route('/logout')
@login_required # Must be logged in to log out
def logout():
    # Store username before logout for flash message
    username = current_user.username if hasattr(current_user, 'username') else 'User'
    is_admin_logout = session.get('is_admin', False)

    logout_user() # Clears user session and Remember Me cookie
    session.clear() # Explicitly clear the whole session for good measure

    if is_admin_logout:
        flash(f'Admin {username} logged out successfully.', 'info')
        return redirect(url_for('auth.admin_login'))
    else:
        flash(f'{username}, you have been logged out.', 'info')
        return redirect(url_for('main.index'))

# --- Admin Login ---
@auth_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    # If already logged in as admin, redirect to dashboard
    if session.get('is_admin') and current_user.is_authenticated and current_user.get_id() == 'admin':
        return redirect(url_for('admin.dashboard'))

    # Prevent logged-in customers from accessing admin login
    if current_user.is_authenticated and not session.get('is_admin'):
         flash('Customers cannot access the admin login page.', 'warning')
         return redirect(url_for('customer.dashboard')) # Redirect to customer dashboard


    form = AdminLoginForm()
    if form.validate_on_submit():
        # Get configured admin credentials from app config
        config_admin_user = current_app.config['ADMIN_USERNAME']
        config_admin_pass = current_app.config['ADMIN_PASSWORD']

        # SECURITY WARNING: Comparing plain text passwords from config is INSECURE.
        # Consider using Flask-Bcrypt to hash the ADMIN_PASSWORD if stored in config,
        # or ideally, create an actual admin user in the 'users' collection with a role.
        # For this example, we stick to the simple plain text comparison as requested.
        submitted_user = form.username.data
        submitted_pass = form.password.data

        if submitted_user == config_admin_user and submitted_pass == config_admin_pass:
            # Manually create and log in the dummy admin user
            # Create the dummy object first
            class AdminUser:
                is_authenticated = True
                is_active = True
                is_anonymous = False
                id = "admin" # Consistent ID
                def get_id(self): return self.id
                def is_admin(self): return True

            admin_obj = AdminUser()
            login_user(admin_obj) # Log in the dummy admin user

            # Set the session flag AFTER successful login
            session['is_admin'] = True
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')

    return render_template('admin_login.html', title='Admin Login', form=form)


# --- Admin Logout (uses the main /logout route now) ---
# The /logout route handles both admin and customer logout based on session['is_admin']

# --- Unauthorized Handler is now defined in app/__init__.py ---
# Do NOT define @login_manager.unauthorized here.