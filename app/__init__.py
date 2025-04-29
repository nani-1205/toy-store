import os
from flask import Flask, session, g, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user, login_user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from bson import ObjectId
from datetime import datetime
import pytz
# Import pymongo errors for more specific exception handling
import pymongo.errors

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
        logger = getattr(Flask, 'logger', None)
        log_message = f"Error in load_user for ID {user_id}: {e}"
        if logger: logger.error(log_message)
        else: print(log_message)
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
    db_name = app.config['MONGO_DBNAME']
    auth_source = app.config.get('MONGO_AUTH_SOURCE', 'admin')
    # Ensure MONGO_URI includes retryWrites=true (recommended for modern MongoDB)
    # Avoid duplicate query params if already present
    if 'retryWrites' not in mongo_uri:
        separator = '&' if '?' in mongo_uri else '?'
        mongo_uri += f"{separator}retryWrites=true"

    app.config['MONGO_URI'] = f"{mongo_uri}?authSource={auth_source}"
    app.config['MONGO_DBNAME'] = db_name

    # Configure PyMongo connection settings (optional but good practice)
    app.config['MONGO_CONNECT_TIMEOUT_MS'] = 5000 # 5 seconds
    app.config['MONGO_SERVER_SELECTION_TIMEOUT_MS'] = 5000 # 5 seconds

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
    def handle_unauthorized():
        is_admin_route = request and hasattr(request, 'blueprint') and request.blueprint == 'admin'
        if is_admin_route:
            flash('You need to log in as an admin to access this page.', 'warning')
            return redirect(url_for('auth.admin_login'))
        else:
            flash('You need to log in to access this page.', 'info')
            next_url = request.url if request else None
            return redirect(url_for('auth.login', next=next_url))

    # --- Assign the Handler Function Directly ---
    login_manager.unauthorized_handler(handle_unauthorized)

    # --- Register Blueprints ---
    # Import blueprints *after* extensions are initialized
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
        app.logger.error(f"Server Error: {error}", exc_info=True)
        return render_template('500.html'), 500

    # --- Database Initialization and Verification ---
    # Use app_context for operations needing app configuration and extensions
    with app.app_context():
        db_connection_ok = False
        try:
            # 1. Verify connection to the server
            print("Attempting to connect to MongoDB server...")
            # Increase timeout slightly for server_info() which can sometimes be slow
            server_info = mongo.cx.server_info(serverSelectionTimeoutMS=6000)
            print(f"Successfully connected to MongoDB server v{server_info['version']}")

            # 2. Attempt a minimal write operation to verify/trigger DB/collection creation
            #    This is the crucial step. If this fails, permissions are likely the issue.
            target_db_name = app.config['MONGO_DBNAME']
            print(f"Attempting first write operation (create_index on 'users') in database '{target_db_name}'...")
            # Access the database directly via the client connection 'cx'
            db_handle = mongo.cx[target_db_name]
            # Try creating the first index. This will fail if user 'jagan' lacks write permissions
            # on 'kondapalli_toys_db', even if the DB doesn't exist yet.
            db_handle.users.create_index('email', unique=True, background=True)
            print(f"Successfully accessed/created 'users' collection and 'email' index in '{target_db_name}'.")

            # 3. If the first write worked, proceed with other indexes
            print("Checking/creating remaining indexes...")
            db_handle.users.create_index('username', unique=True, background=True)
            db_handle.toys.create_index('name', background=True)
            db_handle.orders.create_index('user_id', background=True)
            db_handle.orders.create_index('created_at', background=True)
            print(f"All indexes checked/created.")

            # 4. Confirm we can now access mongo.db (should be valid after successful write)
            if mongo.db is not None and mongo.db.name == target_db_name:
                print(f"Successfully obtained handle to database: {mongo.db.name}")
                db_connection_ok = True
            else:
                 # This case should be rare if create_index succeeded, but good to check
                 print(f"WARNING: Write operation succeeded, but mongo.db handle is still not valid for '{target_db_name}'.")


        except pymongo.errors.OperationFailure as e:
            # Specific handling for MongoDB command failures (often authorization)
            print(f"\n!!! --- FATAL: MongoDB Operation Failure --- !!!")
            print(f"Error Details: {e.details}")
            print(f"Message: {e}")
            if e.has_error_label("AuthenticationFailed"):
                print("Reason: Authentication failed. Check username/password/authSource.")
            elif "command createIndexes requires authentication" in str(e) or \
                 "not authorized on" in str(e) or \
                 "CommandNotAuthorized" in str(e):
                 print(f"Reason: Authorization failed. User 'jagan' (authenticating via '{auth_source}') likely lacks permissions (e.g., readWrite, dbAdmin) on database '{db_name}'.")
            else:
                print("Reason: Could be permissions, configuration, or other MongoDB issue.")
            print("Application startup failed.")
            raise e # Re-raise to stop the app

        except pymongo.errors.ConnectionFailure as e:
            # Handles errors like server not reachable, connection refused
            print(f"\n!!! --- FATAL: MongoDB Connection Failure --- !!!")
            print(f"Error Details: {e}")
            print(f"Reason: Could not connect to MongoDB server at specified URI.")
            print("Check MongoDB server status, network connectivity, IP address, port, and firewalls.")
            print("Application startup failed.")
            raise e # Re-raise to stop the app

        except Exception as e:
            # Catch any other unexpected errors during initialization
            print(f"\n!!! --- FATAL: Unexpected Error during DB Initialization --- !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {e}")
            print("Application startup failed.")
            raise e # Re-raise to stop the app

        # Final check
        if not db_connection_ok:
             # If we somehow got here without raising an exception but DB is not ok
             print(f"\n!!! --- FATAL: Database connection verified but handle ('mongo.db') is not available. --- !!!")
             print("Application startup failed.")
             # Raise a generic exception if specific one wasn't caught
             raise RuntimeError(f"Failed to obtain a valid handle for database '{app.config['MONGO_DBNAME']}' after connection verification.")


    print("Flask application initialization and database checks completed successfully.")
    return app