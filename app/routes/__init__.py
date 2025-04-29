# File: app/routes/__init__.py

from flask import Blueprint

# Create blueprint objects
main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')
admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')
customer_bp = Blueprint('customer', __name__, template_folder='../templates/customer')

# Import the routes modules AFTER defining the blueprints above.
from . import main
from . import auth
from . import admin
from . import customer

# REMOVED THE INCORRECT IMPORT BELOW:
# from .config import Config # Import Config class <-- REMOVE THIS LINE