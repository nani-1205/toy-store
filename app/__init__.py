import os
from flask import Flask, session, g, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user, login_user
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
        class AdminUser:
            is_authenticated = True
            is_active = True
            is_anonymous = False
            id = "admin" # Consistent ID
            def get_id(self): return self.id
            def is_admin(self): return True
        # Only return AdminUser if the session confirms admin status
        if session.get('is_admin'):
            return AdminUser()
        else:
            return None # Prevent loading admin if session flag is missing

    # Check regular customer users from DB
    try:
        from .models import find_user_by_id
        user_data = find_user_by_id(user_id) # Use the model function
        if user_data and user_data.get('is_approved', False):
            class User:
                def __init__(self, data):
                    self._data = data # Store raw data
                    self.id = str(data['_id'])
                    self.is_authenticated = True
                    self.is_active = True
                    self.is_anonymous = False
                def get_id(self): return self.id
                def __getattr__(self, name):
                    if name in ['username', 'email', 'address', 'phone', 'is_approved']:
                         return self._data.get(name)
                    if name == 'is_admin': return False
                    raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
            return User(user_data)
        else:
            return None # User not found or not approved
    except Exception as e:
        # Log error during user loading, but don't crash the app here
        # Use app.logger if available, otherwise print
        logger = getattr(Flask, 'logger', None)
        log_message = f"Error in load_user for ID {user_id}: {e}"
        if logger:
             logger.error(log_message)
        else:
             print(log_message)
        return None

# --- App Factory Function ---
def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Flask extensions WITH the app context
    mongo_uri = app.config['MONGO_URI']
    db_name = app.config['MONGO_DB_NAME']
    auth_source = app.config.get('MONGO_AUTH_SOURCE', 'admin')
    app.config['MONGO_URI'] = f"{mongo_uri}?authSource={auth_source}"
    app.config['MONGO_DBNAME'] = db_name

    mongo.init_app(app)
    login_manager.init_app(app) # Initialize LoginManager with the app
    csrf.init_app(app)
    bcrypt.init_app(app)

    # --- Configure Flask-Login settings ---
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.needs_refresh_message = 'To protect your account, please reauthenticate.'
    login_manager.needs_refresh_message_category = 'info'

    # --- Define the Unauthorized Handler Callback Function ---
    # Give it a unique name, define it plainly without a decorator
    def handle_unauthorized():
        # Decide where to redirect based on the request path
        is_admin_route = request and hasattr(request, 'blueprint') and request.blueprint == 'admin'

        if is_admin_route:
            flash('You need to log in as an admin to access this page.', 'warning')
            return redirect(url_for('auth.admin_login'))
        else:
            flash('You need to log in to access this page.', 'info')
            next_url = request.url if request else None
            return redirect(url_for('auth.login', next=next_url))

    # --- Assign the Handler Function Directly ---
    # Instead of using the decorator, assign the function to the manager's handler
    login_manager.unauthorized_handler(handle_unauthorized)

    # --- Register Blueprints ---
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
        def check_is_admin():
             return session.get('is_admin', False) and \
                    current_user.is_authenticated and \
                    hasattr(current_user, 'is_admin') and \
                    current_user.is_admin()
        return dict(
            current_user=current_user,
            is_admin=check_is_admin(),
            cart_item_count=cart_item_count,
            now=datetime.now
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
        # Log the error including traceback
        app.logger.error(f"Server Error: {error}", exc_info=True)
        # Avoid database operations in the 500 handler if the error might be DB related
        return render_template('500.html'), 500

    # --- Database Check/Index Creation ---
    # Use app_context for operations needing app configuration
    with app.app_context():
        try:
            # Test connection and get server info
            print("Attempting to connect to MongoDB...")
            server_info = mongo.cx.server_info() # This line will raise an error if connection fails
            print(f"Successfully connected to MongoDB server v{server_info['version']}")
            print(f"Using database: {mongo.db.name}")

            # Create indexes (idempotent - safe to run every time)
            print("Checking/creating database indexes...")
            mongo.db.users.create_index('email', unique=True, background=True)
            mongo.db.users.create_index('username', unique=True, background=True)
            mongo.db.toys.create_index('name', background=True)
            mongo.db.orders.create_index('user_id', background=True)
            mongo.db.orders.create_index('created_at', background=True)
            print(f"Indexes checked/created on collections: {mongo.db.list_collection_names()}")

        except Exception as e:
            # Log the specific connection error
            print(f"\n!!! --- FATAL: Error connecting to MongoDB or creating indexes --- !!!")
            print(f"Error details: {e}")
            print("Application startup failed.")
            print("Please check your MONGO_URI, network configuration, firewall, and MongoDB server status.")
            # --- >>> CRITICAL CHANGE FOR DEBUGGING <<< ---
            # Re-raise the exception to stop the Flask app from starting incorrectly.
            # This will make the actual connection error visible in PM2 logs.
            raise e
            # --- >>> END CRITICAL CHANGE <<< ---

    print("Flask application initialized successfully.") # Add success message
    return app