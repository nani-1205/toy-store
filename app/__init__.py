import os
from flask import Flask, session, g, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user, login_user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from bson import ObjectId
from datetime import datetime
import pytz
import pymongo.errors # Import pymongo errors

from .config import Config # Import Config class
from .utils import format_inr, format_datetime_ist

# Initialize extensions (globally accessible)
mongo = PyMongo()
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()

# --- User Loader ---
# (User Loader code remains the same as previous version)
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
    # Load configuration from the Config class (which reads from .env)
    app.config.from_object(config_class)

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- >>> Start Revised DB Config Section <<< ---
    # Get values loaded from Config / .env file
    mongo_uri_base = app.config.get('MONGO_URI') # Get the original URI from .env
    db_name_from_env = app.config.get('MONGO_DB_NAME')
    auth_source = app.config.get('MONGO_AUTH_SOURCE') # Get explicitly, handle None later

    # Basic check if essential DB config is missing
    if not mongo_uri_base:
        raise ValueError("MONGO_URI not found in configuration. Check .env file and config.py.")
    if not db_name_from_env:
        raise ValueError("MONGO_DB_NAME not found in configuration. Check .env file and config.py.")

    # Build the options string carefully
    options = {}
    if auth_source: # Only add authSource if it's defined in .env/config
        options['authSource'] = auth_source
    # Add retryWrites=true by default if not already in the base URI's options
    # (Requires parsing existing options, simpler to just add if authSource exists for now)
    # A more robust solution would parse existing options first.
    # Let's assume retryWrites isn't in the base URI for simplicity here.
    # If authSource is needed, we likely want retryWrites too.
    if options: # If we are adding any options (like authSource)
        options['retryWrites'] = 'true'

    # Construct the final URI
    final_mongo_uri = mongo_uri_base
    if options:
        # Check if the base URI already has options
        separator = '&' if '?' in final_mongo_uri else '?'
        # Build the options string like "key1=value1&key2=value2"
        options_string = '&'.join([f"{key}={value}" for key, value in options.items()])
        final_mongo_uri += f"{separator}{options_string}"

    # Set the final computed URI in the app config
    app.config['MONGO_URI'] = final_mongo_uri
    # Explicitly set the key Flask-PyMongo expects for the DB name
    app.config['MONGO_DBNAME'] = db_name_from_env

    print(f"Final computed MONGO_URI: {app.config['MONGO_URI']}") # Debug print
    print(f"Using MONGO_DBNAME: {app.config['MONGO_DBNAME']}")    # Debug print
    # --- >>> End Revised DB Config Section <<< ---


    # Configure PyMongo connection settings (optional)
    app.config['MONGO_CONNECT_TIMEOUT_MS'] = 5000 # 5 seconds
    app.config['MONGO_SERVER_SELECTION_TIMEOUT_MS'] = 5000 # 5 seconds

    # Initialize extensions AFTER setting their specific config keys
    mongo.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)

    # --- Configure Flask-Login settings ---
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    # ... (rest of login_manager settings)

    # --- Define and Assign Unauthorized Handler ---
    def handle_unauthorized():
        is_admin_route = request and hasattr(request, 'blueprint') and request.blueprint == 'admin'
        if is_admin_route:
            flash('You need to log in as an admin to access this page.', 'warning')
            return redirect(url_for('auth.admin_login'))
        else:
            flash('You need to log in to access this page.', 'info')
            next_url = request.url if request else None
            return redirect(url_for('auth.login', next=next_url))
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
        app.logger.error(f"Server Error: {error}", exc_info=True)
        return render_template('500.html'), 500

    # --- Database Initialization and Verification ---
    with app.app_context():
        db_connection_ok = False
        target_db_name = app.config['MONGO_DBNAME']
        try:
            # 1. Verify connection to the server
            print("Attempting to connect to MongoDB server...")
            server_info = mongo.cx.server_info(serverSelectionTimeoutMS=6000)
            print(f"Successfully connected to MongoDB server v{server_info['version']}")

            # 2. Attempt first write operation
            print(f"Attempting first write operation (create_index on 'users') in database '{target_db_name}'...")
            db_handle = mongo.cx[target_db_name]
            db_handle.users.create_index('email', unique=True, background=True)
            print(f"Successfully accessed/created 'users' collection and 'email' index in '{target_db_name}'.")

            # 3. Proceed with other indexes
            print("Checking/creating remaining indexes...")
            db_handle.users.create_index('username', unique=True, background=True)
            db_handle.toys.create_index('name', background=True)
            db_handle.orders.create_index('user_id', background=True)
            db_handle.orders.create_index('created_at', background=True)
            print(f"All indexes checked/created.")

            # 4. Confirm mongo.db handle
            if mongo.db is not None and mongo.db.name == target_db_name:
                print(f"Successfully obtained handle to database: {mongo.db.name}")
                db_connection_ok = True
            else:
                 print(f"WARNING: Write operation succeeded, but mongo.db handle is still not valid for '{target_db_name}'.")

        except pymongo.errors.OperationFailure as e:
            print(f"\n!!! --- FATAL: MongoDB Operation Failure --- !!!")
            print(f"Error Details: {e.details}")
            # ... (rest of specific OperationFailure handling)
            # Get username from URI if possible (complex parsing needed) or use config default
            auth_user = app.config.get('MONGO_USERNAME', 'specified in URI') # MONGO_USERNAME not usually set
            print(f"Reason: Authorization failed. User '{auth_user}' (authenticating via '{app.config.get('MONGO_AUTH_SOURCE', 'default')}') likely lacks permissions (e.g., readWrite, dbAdmin) on database '{target_db_name}'.")
            print("Application startup failed.")
            raise e # Re-raise to stop the app

        except pymongo.errors.ConnectionFailure as e:
            print(f"\n!!! --- FATAL: MongoDB Connection Failure --- !!!")
            print(f"Error Details: {e}")
            # ... (rest of ConnectionFailure handling)
            raise e # Re-raise to stop the app
        
        except pymongo.errors.InvalidURI as e:
             print(f"\n!!! --- FATAL: Invalid MongoDB URI --- !!!")
             print(f"Error Details: {e}")
             print(f"The final computed URI was: {app.config.get('MONGO_URI')}")
             print("Check the base MONGO_URI in your .env file and the logic for adding options in __init__.py.")
             print("Ensure special characters in username/password are URL-encoded.")
             print("Application startup failed.")
             raise e # Re-raise to stop the app

        except Exception as e:
            print(f"\n!!! --- FATAL: Unexpected Error during DB Initialization --- !!!")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {e}")
            print("Application startup failed.")
            raise e # Re-raise to stop the app

        # Final check
        if not db_connection_ok:
             print(f"\n!!! --- FATAL: Database connection verified but handle ('mongo.db') is not available. --- !!!")
             raise RuntimeError(f"Failed to obtain a valid handle for database '{target_db_name}' after connection verification.")


    print("Flask application initialization and database checks completed successfully.")
    return app