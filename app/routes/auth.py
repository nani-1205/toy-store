from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user # login_user is important here
from werkzeug.security import check_password_hash

from . import auth_bp
from .. import mongo, bcrypt # Removed login_manager import as it's not directly used here
from ..forms import LoginForm, SignupForm, AdminLoginForm
# Import model functions needed
from ..models import find_user_by_email, create_user, find_user_by_username, find_user_by_id

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if already logged in
    if current_user.is_authenticated:
        if session.get('is_admin') and hasattr(current_user, 'is_admin') and current_user.is_admin():
             return redirect(url_for('admin.dashboard'))
        elif not session.get('is_admin'):
             return redirect(url_for('customer.dashboard'))
        else:
             logout_user()
             session.clear()

    form = LoginForm()
    if form.validate_on_submit():
        user_data = find_user_by_email(form.email.data)
        if user_data and bcrypt.check_password_hash(user_data['password_hash'], form.password.data):
            if user_data.get('is_approved', False):
                # --- CORRECTED SECTION ---
                # Find the user data first (already done above)
                # Then, create the user object expected by login_user.
                # The easiest way is often to re-fetch using the ID via the loader's logic,
                # OR create a compatible object directly if find_user_by_id returns the necessary data.
                # Let's rely on login_user to call the loader implicitly.
                # We need an object that has `is_active`, `is_authenticated`, `is_anonymous` and `get_id()`
                # The User class defined in __init__.py's load_user serves this purpose.
                # login_user will call load_user(user_data['_id']) internally.

                # We need *an object* to pass to login_user. It doesn't have to be
                # fully loaded yet, as long as get_id() works. Flask-Login
                # uses the ID to call your @login_manager.user_loader.
                # Create a temporary minimal user object for login_user to use the ID from.
                class TempUser:
                    def __init__(self, user_id):
                        self.id = user_id
                    def get_id(self):
                        return self.id
                    # These might not be strictly needed just for login_user to call the loader
                    # but good practice for consistency.
                    is_active = True
                    is_authenticated = True
                    is_anonymous = False

                temp_user_for_login = TempUser(str(user_data['_id']))

                # Pass this temporary object; Flask-Login uses its ID to call the REAL load_user
                login_was_successful = login_user(temp_user_for_login, remember=form.remember.data)

                # It's good practice to check if login_user succeeded (it calls the loader)
                if login_was_successful and current_user.is_authenticated:
                    session['is_admin'] = False # Ensure admin flag is false for customer
                    flash('Login successful!', 'success')
                    next_page = request.args.get('next')
                    # Add check here if next_page is internal to prevent open redirect
                    # is_safe_url should be implemented if needed
                    # if not is_safe_url(next_page):
                    #    return abort(400)
                    return redirect(next_page or url_for('customer.dashboard'))
                else:
                     # If login_user returns False, or current_user isn't authenticated,
                     # it means the user loaded by load_user was invalid (e.g., inactive)
                     # or load_user returned None.
                     flash('Login failed: Unable to load user profile.', 'danger')
                     # Log this situation for debugging
                     current_app.logger.warning(f"Login failed for user ID {user_data['_id']} after password check passed. Check load_user function.")
                # --- END CORRECTED SECTION ---

            else:
                flash('Your account is pending admin approval. Please wait.', 'warning')
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Customer Login', form=form)

# --- Signup Route ---
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    # (Signup code remains the same)
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
             flash('Account creation failed due to a server issue. Please try again.', 'danger')

    return render_template('signup.html', title='Sign Up', form=form)

# --- Logout Route ---
@auth_bp.route('/logout')
@login_required
def logout():
    # (Logout code remains the same)
    username = current_user.username if hasattr(current_user, 'username') else 'User'
    is_admin_logout = session.get('is_admin', False)

    logout_user()
    session.clear()

    if is_admin_logout:
        flash(f'Admin {username} logged out successfully.', 'info')
        return redirect(url_for('auth.admin_login'))
    else:
        flash(f'{username}, you have been logged out.', 'info')
        return redirect(url_for('main.index'))


# --- Admin Login Route ---
@auth_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    # (Admin login code remains the same)
    if session.get('is_admin') and current_user.is_authenticated and current_user.get_id() == 'admin':
        return redirect(url_for('admin.dashboard'))

    if current_user.is_authenticated and not session.get('is_admin'):
         flash('Customers cannot access the admin login page.', 'warning')
         return redirect(url_for('customer.dashboard'))

    form = AdminLoginForm()
    if form.validate_on_submit():
        config_admin_user = current_app.config['ADMIN_USERNAME']
        config_admin_pass = current_app.config['ADMIN_PASSWORD']
        submitted_user = form.username.data
        submitted_pass = form.password.data

        if submitted_user == config_admin_user and submitted_pass == config_admin_pass:
            class AdminUser: # Define the dummy admin user object
                is_authenticated = True
                is_active = True
                is_anonymous = False
                id = "admin"
                def get_id(self): return self.id
                def is_admin(self): return True

            admin_obj = AdminUser()
            login_user(admin_obj) # Log in the dummy admin user

            session['is_admin'] = True # Set session flag AFTER login
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'danger')

    return render_template('admin_login.html', title='Admin Login', form=form)