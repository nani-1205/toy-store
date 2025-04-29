import os
from flask import Flask, session, g, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user, login_user # Added login_user here for admin dummy user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from bson import ObjectId
from datetime import datetime
import pytz

from .config import Config
from .utils import format_inr, format_datetime_ist

# Initialize extensions (globally accessible)
mongo = PyMongo()
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()

# --- User Loader ---
@login_manager.user_loader
def load_user(user_id):
    # Check admin first (session-based, not in DB)
    if user_id == "admin": # Check specifically for the admin ID
        # Create a dummy admin user object for Flask-Login context
        class AdminUser:
            is_authenticated = True
            is_active = True
            is_anonymous = False
            id = "admin" # Consistent ID

            def get_id(self):
                return self.id

            def is_admin(self): # Custom method
                return True
        # Only return AdminUser if the session confirms admin status
        if session.get('is_admin'):
            return AdminUser()
        else:
            return None # Prevent loading admin if session flag is missing

    # Check regular customer users from DB
    try:
        # Import model function here to avoid circular import at top level
        from .models import find_user_by_id
        user_data = find_user_by_id(user_id) # Use the model function

        # Ensure user exists and is approved
        if user_data and user_data.get('is_approved', False):
             # Create a user object compatible with Flask-Login
            class User:
                def __init__(self, data):
                    self._data = data # Store raw data
                    self.id = str(data['_id'])
                    self.is_authenticated = True
                    self.is_active = True # Assuming active if approved
                    self.is_anonymous = False

                def get_id(self):
                    return self.id

                # Delegate attribute access to the underlying data dictionary
                def __getattr__(self, name):
                    # Common attributes
                    if name in ['username', 'email', 'address', 'phone', 'is_approved']:
                         return self._data.get(name)
                    # Special method for admin check
                    if name == 'is_admin':
                        return False
                    # Raise AttributeError for other undefined attributes
                    raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

            return User(user_data)
        else:
            return None # User not found or not approved
    except Exception as e: # Handle invalid ObjectId etc.
        print(f"Error in load_user for ID {user_id}: {e}")
        return None

# --- App Factory Function ---
def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Flask extensions WITH the app context
    mongo_uri = app.config['MONGO_URI']
    db_name = app.config['MONGO_DB_NAME']
    auth_source = app.config.get('MONGO_AUTH_SOURCE', 'admin')

    # Construct the final URI correctly for PyMongo
    # PyMongo expects the database name in the options/separate config
    app.config['MONGO_URI'] = f"{mongo_uri}?authSource={auth_source}"
    app.config['MONGO_DBNAME'] = db_name # Tell Flask-PyMongo which DB to use

    mongo.init_app(app)
    login_manager.init_app(app) # Initialize LoginManager with the app
    csrf.init_app(app)
    bcrypt.init_app(app)

    # --- Configure Flask-Login settings ---
    login_manager.login_view = 'auth.login' # Redirect non-logged-in users here
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info' # Flash message category
    login_manager.needs_refresh_message = 'To protect your account, please reauthenticate.'
    login_manager.needs_refresh_message_category = 'info' # For session freshness (if used)

    # --- Unauthorized Handler ---
    # Define it HERE, after login_manager is initialized with the app
    @login_manager.unauthorized
    def unauthorized():
        # Decide where to redirect based on the request path
        # Check request.blueprint safely
        is_admin_route = request and hasattr(request, 'blueprint') and request.blueprint == 'admin'

        if is_admin_route:
            flash('You need to log in as an admin to access this page.', 'warning')
            return redirect(url_for('auth.admin_login'))
        else:
            flash('You need to log in to access this page.', 'info')
            # Safely get the next URL
            next_url = request.url if request else None
            return redirect(url_for('auth.login', next=next_url))

    # --- Register Blueprints ---
    # Import them AFTER initializing extensions and defining handlers
    from .routes import main_bp, auth_bp, admin_bp, customer_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(customer_bp, url_prefix='/customer')

    # --- Context Processors ---
    @app.context_processor
    def inject_global_vars():
        cart = session.get('cart', {})
        cart_item_count = sum(item['quantity'] for item in cart.values())
        # Function to check admin status based on session
        def check_is_admin():
             # Check both session flag and if current_user object has is_admin method returning True
             return session.get('is_admin', False) and \
                    current_user.is_authenticated and \
                    hasattr(current_user, 'is_admin') and \
                    current_user.is_admin()

        return dict(
            current_user=current_user, # Provided by Flask-Login
            is_admin=check_is_admin(), # Use the check function
            cart_item_count=cart_item_count,
            now=datetime.now # Make datetime available for footer year etc.
        )

    # --- Jinja Filters ---
    app.jinja_env.filters['inr'] = format_inr
    app.jinja_env.filters['datetime_ist'] = format_datetime_ist

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        # In a real app, log the error details
        app.logger.error(f"Server Error: {error}", exc_info=True) # Log traceback
        # Optionally rollback DB session if using transactions
        # mongo.cx.rollback()
        return render_template('500.html'), 500

    # --- Database Check/Index Creation ---
    # Use app_context for operations needing app configuration
    with app.app_context():
        try:
            # Test connection and get server info
            server_info = mongo.cx.server_info()
            print(f"Successfully connected to MongoDB server v{server_info['version']}")
            print(f"Using database: {mongo.db.name}")

            # Create indexes (idempotent - safe to run every time)
            # Ensure indexes exist for faster queries and enforce uniqueness
            mongo.db.users.create_index('email', unique=True, background=True)
            mongo.db.users.create_index('username', unique=True, background=True)
            mongo.db.toys.create_index('name', background=True)
            mongo.db.orders.create_index('user_id', background=True)
            mongo.db.orders.create_index('created_at', background=True)
            print(f"Indexes checked/created on collections: {mongo.db.list_collection_names()}")

        except Exception as e:
            print(f"\n!!! --- WARNING: Error connecting to MongoDB or creating indexes --- !!!")
            print(f"Error details: {e}")
            print("The application might not function correctly without a database connection.")
            print("Please check your MONGO_URI and network connectivity.")
            # Consider whether to raise the exception to stop the app
            # raise e # Uncomment to stop app start on DB connection error

    return app