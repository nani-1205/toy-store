# File: app/__init__.py

import os
from flask import Flask, session, g, render_template, request, redirect, url_for, flash
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user, login_user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from bson import ObjectId
from datetime import datetime
import pytz
import pymongo.errors

from .config import Config # Import Config class
from .utils import format_inr, format_datetime_ist

# Initialize extensions
mongo = PyMongo()
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()

# --- User Loader ---
# (User loader code remains the same)
@login_manager.user_loader
def load_user(user_id):
    if user_id == "admin":
        class AdminUser:
            is_authenticated = True; is_active = True; is_anonymous = False; id = "admin"
            def get_id(self): return self.id
            def is_admin(self): return True
        if session.get('is_admin'): return AdminUser()
        else: return None
    try:
        from .models import find_user_by_id
        user_data = find_user_by_id(user_id)
        if user_data and user_data.get('is_approved', False):
            class User:
                def __init__(self, data): self._data = data; self.id = str(data['_id']); self.is_authenticated = True; self.is_active = True; self.is_anonymous = False
                def get_id(self): return self.id
                def __getattr__(self, name):
                    if name in ['username', 'email', 'address', 'phone', 'is_approved']: return self._data.get(name)
                    if name == 'is_admin': return False
                    raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
            return User(user_data)
        else: return None
    except Exception as e:
        logger = getattr(Flask, 'logger', None); log_message = f"Error in load_user for ID {user_id}: {e}"
        if logger: logger.error(log_message); else: print(log_message)
        return None

# --- App Factory Function ---
def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    # Enable Jinja 'do' extension
    app.jinja_env.add_extension('jinja2.ext.do')

    # Load configuration
    app.config.from_object(config_class)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- >>> Create Upload Folder if it doesn't exist <<< ---
    upload_folder = app.config.get('UPLOAD_FOLDER')
    if upload_folder:
        if not os.path.exists(upload_folder):
            try:
                # Create parent directories if they don't exist
                os.makedirs(upload_folder, exist_ok=True)
                print(f"Created upload folder: {upload_folder}")
            except OSError as e:
                print(f"ERROR: Could not create upload folder {upload_folder}: {e}")
                # Decide whether to stop the app
                # raise e # Uncomment to fail startup if folder creation fails
        else:
             print(f"Upload folder already exists: {upload_folder}")
    else:
        print("WARNING: UPLOAD_FOLDER not configured in config.py. File uploads will likely fail.")
    # --- >>> End Create Upload Folder <<< ---


    # --- DB Config Section ---
    # (DB Config logic remains the same)
    mongo_uri_base = app.config.get('MONGO_URI')
    db_name_from_env = app.config.get('MONGO_DB_NAME')
    auth_source = app.config.get('MONGO_AUTH_SOURCE')
    if not mongo_uri_base: raise ValueError("MONGO_URI not found in config.")
    if not db_name_from_env: raise ValueError("MONGO_DB_NAME not found in config.")
    options = {}
    if auth_source: options['authSource'] = auth_source
    if 'retryWrites' not in mongo_uri_base: options['retryWrites'] = 'true'
    final_mongo_uri = mongo_uri_base
    if options:
        separator = '&' if '?' in final_mongo_uri else '?'
        options_string = '&'.join([f"{key}={value}" for key, value in options.items()])
        final_mongo_uri += f"{separator}{options_string}"
    app.config['MONGO_URI'] = final_mongo_uri
    app.config['MONGO_DBNAME'] = db_name_from_env
    print(f"Final computed MONGO_URI: {app.config['MONGO_URI']}")
    print(f"Using MONGO_DBNAME: {app.config['MONGO_DBNAME']}")
    app.config['MONGO_CONNECT_TIMEOUT_MS'] = 5000
    app.config['MONGO_SERVER_SELECTION_TIMEOUT_MS'] = 5000

    # Initialize extensions AFTER setting config
    mongo.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)

    # --- Configure Flask-Login settings ---
    # (Settings remain the same)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # --- Define and Assign Unauthorized Handler ---
    # (Handler remains the same)
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
    # (Blueprint registration remains the same)
    from .routes import main_bp, auth_bp, admin_bp, customer_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(customer_bp, url_prefix='/customer')

    # --- Context Processors ---
    # (Context processor remains the same)
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
    # (Filters remain the same)
    app.jinja_env.filters['inr'] = format_inr
    app.jinja_env.filters['datetime_ist'] = format_datetime_ist

    # --- Error Handlers ---
    # (Error handlers remain the same)
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Server Error: {error}", exc_info=True)
        return render_template('500.html'), 500

    # --- Database Initialization and Verification (Simplified Check) ---
    # (DB Init code remains the same)
    with app.app_context():
        target_db_name = app.config['MONGO_DBNAME']
        try:
            print("Attempting to connect to MongoDB server...")
            server_info = mongo.cx.server_info()
            print(f"Successfully connected to MongoDB server v{server_info['version']}")
            print(f"Attempting write operation (create_index on 'users') in database '{target_db_name}'...")
            db_handle = mongo.cx[target_db_name]
            db_handle.users.create_index('email', unique=True, background=True)
            print(f"Successfully verified write access to '{target_db_name}' (index created/verified).")
            print("Checking/creating remaining indexes...")
            db_handle.users.create_index('username', unique=True, background=True)
            db_handle.toys.create_index('name', background=True)
            db_handle.orders.create_index('user_id', background=True)
            db_handle.orders.create_index('created_at', background=True)
            print(f"All indexes checked/created.")
        except pymongo.errors.OperationFailure as e:
            print(f"\n!!! --- FATAL: MongoDB Operation Failure --- !!!")
            print(f"Error Details: {e.details}"); auth_user = 'specified in URI'; auth_src = app.config.get('MONGO_AUTH_SOURCE', 'default')
            print(f"Reason: Authorization failed. User '{auth_user}' (authenticating via '{auth_src}') likely lacks permissions on database '{target_db_name}'."); print("Application startup failed."); raise e
        except pymongo.errors.ConnectionFailure as e:
            print(f"\n!!! --- FATAL: MongoDB Connection Failure --- !!!")
            print(f"Error Details: {e}"); print(f"Reason: Could not connect to MongoDB server."); print("Check MongoDB server status, network connectivity, firewalls."); print("Application startup failed."); raise e
        except pymongo.errors.InvalidURI as e:
             print(f"\n!!! --- FATAL: Invalid MongoDB URI --- !!!")
             print(f"Error Details: {e}"); print(f"The final computed URI was: {app.config.get('MONGO_URI')}"); print("Check .env file and URI construction logic."); print("Application startup failed."); raise e
        except Exception as e:
            print(f"\n!!! --- FATAL: Unexpected Error during DB Initialization --- !!!")
            print(f"Error type: {type(e).__name__}"); print(f"Error details: {e}"); print("Application startup failed."); raise e
        print("Database connection verified and initial setup completed.")


    print("Flask application initialization completed successfully.")
    return app