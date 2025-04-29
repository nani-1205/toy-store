from flask import render_template, current_app
from . import main_bp
from .. import mongo
from ..models import get_all_toys

@main_bp.route('/')
@main_bp.route('/index')
def index():
    # Fetch toys that are in stock for the homepage
    toys = get_all_toys(in_stock_only=True)
    return render_template('index.html', title='Welcome', toys=toys)

# Add other general routes like about page if needed
# @main_bp.route('/about')
# def about():
#     return render_template('about.html', title='About Us')