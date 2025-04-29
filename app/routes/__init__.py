# File: app/routes/__init__.py

from flask import Blueprint

# Create blueprint objects
# The template_folder paths are relative to the location of *this* file (app/routes/)
# So '../templates/auth' correctly points to app/templates/auth/
main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')
admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')
customer_bp = Blueprint('customer', __name__, template_folder='../templates/customer')

# Import the route modules AFTER defining the blueprints above.
# This is crucial because the route modules (.main, .auth, etc.)
# import the blueprint objects (main_bp, auth_bp, etc.) from this file
# to define their routes using decorators like @auth_bp.route().
from . import main
from . import auth
from . import admin
from . import customer