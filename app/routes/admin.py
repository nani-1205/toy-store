from flask import render_template, redirect, url_for, flash, request, session, abort, current_app
from flask_login import login_required, current_user
from functools import wraps
from bson import ObjectId

from . import admin_bp
from .. import mongo
from ..forms import ToyForm
from ..models import (
    get_admin_stats, get_all_toys, add_toy, find_toy_by_id, update_toy, delete_toy,
    get_all_orders, find_order_by_id, update_order_status,
    get_pending_users, get_approved_users, approve_user, find_user_by_id
)

# --- Decorator for Admin Routes ---
def admin_required(f):
    @wraps(f)
    @login_required # Ensure user is logged in first
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash("Admin access required for this page.", "danger")
            # Check if it was a customer trying to access
            if current_user.is_authenticated and hasattr(current_user, 'is_admin') and not current_user.is_admin():
                return redirect(url_for('customer.dashboard')) # Redirect customer away
            else:
                 return redirect(url_for('auth.admin_login')) # Redirect potential non-admins or logged out users
        # Check if the logged-in user object (even the dummy one) confirms it's admin
        # This check might be redundant if session['is_admin'] is the primary gate,
        # but good for consistency if using current_user properties elsewhere.
        if not (hasattr(current_user, 'is_admin') and current_user.is_admin()):
             # This case should ideally not be reached if session check works
             flash("Admin privileges verification failed.", "danger")
             return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Admin Dashboard Routes ---

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Main admin dashboard showing overview stats."""
    stats = get_admin_stats()
    return render_template('dashboard.html', title='Admin Dashboard', stats=stats)

@admin_bp.route('/stats')
@admin_required
def stats():
    """Dedicated statistics page (can be expanded)."""
    stats = get_admin_stats()
    # You could add more detailed stats fetching here later
    return render_template('stats.html', title='Statistics', stats=stats)

# --- Toy Management Routes ---

@admin_bp.route('/toys')
@admin_required
def manage_toys():
    """List all toys for management."""
    toys = get_all_toys()
    return render_template('toys.html', title='Manage Toys', toys=toys)

@admin_bp.route('/toys/add', methods=['GET', 'POST'])
@admin_required
def add_new_toy():
    """Form to add a new toy."""
    form = ToyForm()
    if form.validate_on_submit():
        toy_id = add_toy(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            image_url=form.image_url.data,
            stock=form.stock.data
        )
        if toy_id:
            flash('New toy added successfully!', 'success')
            return redirect(url_for('admin.manage_toys'))
        else:
            flash('Error adding toy.', 'danger')
    return render_template('add_toy.html', title='Add New Toy', form=form)

@admin_bp.route('/toys/edit/<toy_id>', methods=['GET', 'POST'])
@admin_required
def edit_toy_details(toy_id):
    """Form to edit an existing toy."""
    toy = find_toy_by_id(toy_id)
    if not toy:
        flash('Toy not found.', 'danger')
        return redirect(url_for('admin.manage_toys'))

    form = ToyForm(obj=toy) # Pre-populate form with toy data

    if form.validate_on_submit():
        # Don't use obj= on update, use form data directly
        success = update_toy(
            toy_id=toy_id,
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            image_url=form.image_url.data,
            stock=form.stock.data
        )
        if success:
            flash('Toy updated successfully!', 'success')
            return redirect(url_for('admin.manage_toys'))
        else:
            flash('Error updating toy.', 'danger')
    # Ensure price is pre-filled correctly even on GET
    if request.method == 'GET':
         form.price.data = toy.get('price')

    return render_template('edit_toy.html', title='Edit Toy', form=form, toy_id=toy_id)

@admin_bp.route('/toys/delete/<toy_id>', methods=['POST']) # Use POST for delete actions
@admin_required
def delete_toy_item(toy_id):
    """Deletes a toy."""
    # Add CSRF protection check if needed, Flask-WTF handles it for forms
    # For simple POST links, ensure CSRF token is included and validated if protection is strict
    success = delete_toy(toy_id)
    if success:
        flash('Toy deleted successfully!', 'success')
    else:
        flash('Error deleting toy. It might be part of an order or not found.', 'danger')
    return redirect(url_for('admin.manage_toys'))


# --- Order Management Routes ---

@admin_bp.route('/orders')
@admin_required
def manage_orders():
    """List all orders for management."""
    status_filter = request.args.get('status')
    orders_data = get_all_orders() # Fetch raw order data

    orders_with_users = []
    for order in orders_data:
        user = find_user_by_id(order.get('user_id'))
        order['user_email'] = user['email'] if user else 'Unknown User'
        order['user_username'] = user['username'] if user else 'Unknown User'
        # Apply filter
        if status_filter and order.get('status') != status_filter:
             continue
        orders_with_users.append(order)


    return render_template('orders.html', title='Manage Orders', orders=orders_with_users, current_filter=status_filter)


@admin_bp.route('/orders/view/<order_id>')
@admin_required
def view_order(order_id):
    """View details of a specific order."""
    order = find_order_by_id(order_id)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('admin.manage_orders'))

    user = find_user_by_id(order.get('user_id'))
    order['user_email'] = user['email'] if user else 'Unknown User'
    order['user_username'] = user['username'] if user else 'Unknown User'

    # Ensure items have necessary details (like name, though stored now)
    # for item in order.get('items', []):
    #     toy = find_toy_by_id(item['toy_id'])
    #     item['name'] = toy['name'] if toy else 'Toy Not Found'
        # Price at time of order is already stored in item['price']

    valid_statuses = ['Pending', 'Accepted', 'Shipped', 'Delivered', 'Cancelled'] # For dropdown

    return render_template('order_detail.html', title='Order Details', order=order, valid_statuses=valid_statuses)


@admin_bp.route('/orders/update_status/<order_id>', methods=['POST'])
@admin_required
def update_order_status_route(order_id):
    """Updates the status of an order."""
    new_status = request.form.get('status')
    if not new_status:
        flash('No status provided.', 'warning')
        return redirect(request.referrer or url_for('admin.manage_orders'))

    success = update_order_status(order_id, new_status)
    if success:
        flash(f'Order status updated to {new_status}.', 'success')
         # Add logic here: e.g., if status changed to 'Shipped', maybe send email notification
    else:
        flash('Failed to update order status.', 'danger')

    return redirect(url_for('admin.view_order', order_id=order_id))


# --- User Management Routes ---

@admin_bp.route('/users')
@admin_required
def manage_users():
    """List users, separating pending and approved."""
    pending = get_pending_users()
    approved = get_approved_users()
    return render_template('users.html', title='Manage Users', pending_users=pending, approved_users=approved)


@admin_bp.route('/users/approve/<user_id>', methods=['POST'])
@admin_required
def approve_user_route(user_id):
    """Approves a pending user."""
    success = approve_user(user_id)
    if success:
        flash('User approved successfully!', 'success')
        # Optional: Send notification email to user
    else:
        flash('Error approving user.', 'danger')
    return redirect(url_for('admin.manage_users'))

# Optional: Route to view user details or disable users could be added here.