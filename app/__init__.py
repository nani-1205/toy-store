import os
from flask import Flask, session, g, render_template
from flask_pymongo import PyMongo
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from bson import ObjectId
from datetime import datetime
import pytz

from .config import Config
from .utils import format_inr, format_datetime_ist

# Initialize extensions
mongo = PyMongo()
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()

# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    # Check admin first (not stored in DB in this simplified example)
    if session.get('is_admin'):
        # Create a dummy admin user object for Flask-Login context
        class AdminUser:
            is_authenticated = True
            is_active = True
            is_anonymous = False
            def get_id(self):
                return "admin" # Static ID for admin
            def is_admin(self): # Custom method
                return True
        return AdminUser()

    # Check regular customer users
    try:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if user_data and user_data.get('is_approved', False): # Only load approved users
             # Create a user object compatible with Flask-Login
            class User:
                def __init__(self, data):
                    self.id = str(data['_id'])
                    self.username = data['username']
                    self.email = data['email']
                    self.address = data.get('address')
                    self.phone = data.get('phone')
                    self.is_approved = data.get('is_approved', False)
                    self.is_authenticated = True
                    self.is_active = True # You might add an 'is_active' field later
                    self.is_anonymous = False

                def get_id(self):
                    return self.id

                def is_admin(self): # Custom method
                    return False

            return User(user_data)
    except Exception: # Handle invalid ObjectId etc.
        return None
    return None

# Configure unauthorized access redirects
login_manager.login_view = 'auth.login' # Redirect non-logged-in users here
login_manager.login_message_category = 'info' # Flash message category
login_manager.needs_refresh_message_category = 'info' # For session freshness

# Function to check if the current user is an admin
def is_admin():
    return session.get('is_admin', False)

def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Flask extensions
    mongo_uri = app.config['MONGO_URI']
    db_name = app.config['MONGO_DB_NAME']
    auth_source = app.config.get('MONGO_AUTH_SOURCE', 'admin') # Default to 'admin'

    # Construct the final URI with db name and authSource if needed
    # PyMongo expects the database name in the options, not the URI path usually
    app.config['MONGO_URI'] = f"{mongo_uri}?authSource={auth_source}"
    app.config['MONGO_DBNAME'] = db_name # Tell Flask-PyMongo which DB to use

    mongo.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)

    # Register Blueprints
    from .routes import main_bp, auth_bp, admin_bp, customer_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(customer_bp, url_prefix='/customer')

    # Context processors to make variables available in all templates
    @app.context_processor
    def inject_user_and_admin():
        cart = session.get('cart', {})
        cart_item_count = sum(item['quantity'] for item in cart.values())
        return dict(
            current_user=current_user,
            is_admin=is_admin(),
            cart_item_count=cart_item_count
        )

    # Inject utility functions into Jinja environment
    app.jinja_env.filters['inr'] = format_inr
    app.jinja_env.filters['datetime_ist'] = format_datetime_ist

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        # In a real app, log the error details
        print(f"Server Error: {error}")
        return render_template('500.html'), 500

    # Create database and collections if they don't exist (by adding an index)
    with app.app_context():
        try:
            # Create indexes (this also ensures the collection exists)
            mongo.db.users.create_index('email', unique=True)
            mongo.db.users.create_index('username', unique=True)
            mongo.db.toys.create_index('name')
            mongo.db.orders.create_index('user_id')
            mongo.db.orders.create_index('created_at')
            print(f"Connected to MongoDB database: {mongo.db.name}")
            print(f"Collections checked/created: {mongo.db.list_collection_names()}")
        except Exception as e:
            print(f"Error connecting to MongoDB or creating indexes: {e}")
            # Decide if the app should fail to start here
            # raise e # Uncomment to stop app start on DB connection error

    return app