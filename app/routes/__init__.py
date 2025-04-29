from flask import Blueprint

# Create blueprint objects
main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')
admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')
customer_bp = Blueprint('customer', __name__, template_folder='../templates/customer')

# Import the routes to register them with the blueprints
# Import at the end to avoid circular dependencies
from . import main, auth, admin, customer