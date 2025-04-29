# File: app/routes/admin.py

from flask import render_template, redirect, url_for, flash, request, session, abort, current_app
from flask_login import login_required, current_user
from functools import wraps
from bson import ObjectId
# --- File Handling Imports ---
import os
from werkzeug.utils import secure_filename
from datetime import datetime
# --- End File Handling Imports ---

from . import admin_bp
from ..forms import ToyForm # Make sure forms are imported
# Use get_db helper function
from ..models import (
    get_admin_stats, get_all_toys, add_toy, find_toy_by_id, update_toy, delete_toy,
    get_all_orders, find_order_by_id, update_order_status,
    get_pending_users, get_approved_users, approve_user, find_user_by_id, get_db
)

# --- Decorator for Admin Routes ---
def admin_required(f):
    @wraps(f)
    @login_required # Ensure user is logged in first
    def decorated_function(*args, **kwargs):
        is_admin_user = session.get('is_admin', False) and \
                        current_user.is_authenticated and \
                        hasattr(current_user, 'is_admin') and \
                        current_user.is_admin()
        if not is_admin_user:
            flash("Admin access required for this page.", "danger")
            if current_user.is_authenticated:
                return redirect(url_for('customer.dashboard'))
            else:
                 return redirect(url_for('auth.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Function for Saving Image ---
def save_toy_image(file_storage):
    """Saves the uploaded image file and returns the relative path for DB storage."""
    if not file_storage or not file_storage.filename:
        return None

    try:
        # Secure the filename and add timestamp to prevent collisions
        original_filename = secure_filename(file_storage.filename)
        base, ext = os.path.splitext(original_filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # Sanitize base filename further if needed
        base = base[:50] # Limit length
        filename = f"{timestamp}_{base}{ext}"

        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        if not upload_folder:
             current_app.logger.error("UPLOAD_FOLDER is not configured.")
             flash("Server configuration error: Upload folder not set.", "danger")
             return None

        save_path = os.path.join(upload_folder, filename)

        # Save the file
        file_storage.save(save_path)
        current_app.logger.info(f"Saved new toy image: {save_path}")

        # Return the path relative to the static folder for url_for()
        # Assumes UPLOAD_FOLDER is '.../app/static/uploads/toys'
        relative_path = os.path.join('uploads', 'toys', filename).replace('\\', '/') # Ensure forward slashes
        return relative_path
    except Exception as e:
        current_app.logger.error(f"Failed to save toy image '{original_filename}': {e}", exc_info=True)
        flash("Error saving uploaded image.", "danger")
        return None

# --- Helper Function for Deleting Image ---
def delete_toy_image(relative_image_path):
    """Deletes an image file given its path relative to the static folder."""
    if not relative_image_path:
        return False
    try:
        # Construct the absolute path based on the app's static folder
        base_static_path = current_app.static_folder # Usually app/static
        if not base_static_path:
             current_app.logger.error("Cannot determine static folder path for image deletion.")
             return False

        full_path = os.path.join(base_static_path, relative_image_path)

        if os.path.exists(full_path):
            os.remove(full_path)
            current_app.logger.info(f"Deleted old toy image: {full_path}")
            return True
        else:
            current_app.logger.warning(f"Attempted to delete non-existent image: {full_path}")
            return False # Not an error if file doesn't exist
    except Exception as e:
        current_app.logger.error(f"Error deleting image file {relative_image_path}: {e}", exc_info=True)
        return False


# --- Admin Dashboard Routes ---
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    stats = get_admin_stats()
    return render_template('dashboard.html', title='Admin Dashboard', stats=stats)

@admin_bp.route('/stats')
@admin_required
def stats():
    stats = get_admin_stats()
    return render_template('stats.html', title='Statistics', stats=stats)


# --- Toy Management Routes ---

@admin_bp.route('/toys')
@admin_required
def manage_toys():
    toys = get_all_toys()
    return render_template('toys.html', title='Manage Toys', toys=toys)

@admin_bp.route('/toys/add', methods=['GET', 'POST'])
@admin_required
def add_new_toy():
    form = ToyForm()
    if form.validate_on_submit():
        image_file = form.image.data
        # --- Image is required for adding ---
        if not image_file:
            flash('Toy image is required.', 'danger')
            # Return the template again, keeping other entered data
            return render_template('add_toy.html', title='Add New Toy', form=form)

        relative_image_path = save_toy_image(image_file)
        if not relative_image_path:
            # Error flashed within save_toy_image
             return render_template('add_toy.html', title='Add New Toy', form=form)

        # Call model function with the saved image path
        toy_id = add_toy(
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            image_path=relative_image_path, # Pass path
            stock=form.stock.data
        )
        if toy_id:
            flash('New toy added successfully!', 'success')
            return redirect(url_for('admin.manage_toys'))
        else:
            delete_toy_image(relative_image_path) # Clean up uploaded image if DB save fails
            flash('Error adding toy to database.', 'danger')
    elif request.method == 'POST' and form.errors:
         current_app.logger.warning(f"Add toy form validation errors: {form.errors}")
         flash('Please correct the errors below.', 'warning')


    return render_template('add_toy.html', title='Add New Toy', form=form)

@admin_bp.route('/toys/edit/<toy_id>', methods=['GET', 'POST'])
@admin_required
def edit_toy_details(toy_id):
    # Find existing toy first
    toy = find_toy_by_id(toy_id)
    if not toy:
        flash('Toy not found.', 'danger')
        return redirect(url_for('admin.manage_toys'))

    # Populate form, excluding file field
    form = ToyForm(obj=toy)

    if form.validate_on_submit():
        current_image_path = toy.get('image_path')
        new_relative_image_path = current_image_path # Default to existing path

        # --- Handle Optional New File Upload ---
        if form.image.data: # Check if a new file was uploaded
            new_relative_image_path_candidate = save_toy_image(form.image.data)
            if new_relative_image_path_candidate:
                # Successfully saved new image, update the path for DB
                new_relative_image_path = new_relative_image_path_candidate
                # Attempt to delete the old image *after* saving the new one
                if current_image_path and current_image_path != new_relative_image_path:
                    delete_toy_image(current_image_path)
            else:
                 # Failed to save new image, flash error and render form again
                 # Error message already flashed by save_toy_image
                 return render_template('edit_toy.html', title='Edit Toy', form=form, toy_id=toy_id, toy=toy)
        # --- End File Upload Handling ---

        # Update database with potentially new image path
        success = update_toy(
            toy_id=toy_id,
            name=form.name.data,
            description=form.description.data,
            price=form.price.data,
            image_path=new_relative_image_path, # Pass potentially updated path
            stock=form.stock.data
        )
        if success:
            flash('Toy updated successfully!', 'success')
            return redirect(url_for('admin.manage_toys'))
        else:
            flash('Error updating toy in database.', 'danger')
            # If DB update failed but we saved a new image, should we delete it?
            # If new_relative_image_path != current_image_path: delete_toy_image(new_relative_image_path) ?
            # Safer to leave it for manual cleanup in this case.
    elif request.method == 'POST' and form.errors:
        current_app.logger.warning(f"Edit toy form validation errors: {form.errors}")
        flash('Please correct the errors below.', 'warning')

    # For GET request, pre-fill price field if needed (obj= should handle it)
    if request.method == 'GET' and not form.price.data:
         form.price.data = toy.get('price')

    # Pass toy data to template for displaying current image etc.
    return render_template('edit_toy.html', title='Edit Toy', form=form, toy_id=toy_id, toy=toy)


@admin_bp.route('/toys/delete/<toy_id>', methods=['POST'])
@admin_required
def delete_toy_item(toy_id):
    # Find the toy to get its image path *before* deleting from DB
    toy_to_delete = find_toy_by_id(toy_id)
    image_path_to_delete = None
    if toy_to_delete:
        image_path_to_delete = toy_to_delete.get('image_path')

    # Attempt to delete from DB
    db_delete_success = delete_toy(toy_id)

    if db_delete_success:
        flash('Toy deleted successfully!', 'success')
        # If DB delete was successful, attempt to delete the image file
        if image_path_to_delete:
            delete_toy_image(image_path_to_delete)
        else:
             current_app.logger.info(f"No image path found for deleted toy {toy_id}.")
    else:
        flash('Error deleting toy from database.', 'danger')

    return redirect(url_for('admin.manage_toys'))


# --- Order Management Routes ---
# (Order routes remain the same)
@admin_bp.route('/orders')
@admin_required
def manage_orders():
    status_filter = request.args.get('status')
    orders_data = get_all_orders()
    orders_with_users = []
    for order in orders_data:
        user = find_user_by_id(order.get('user_id'))
        order['user_email'] = user['email'] if user else 'Unknown'
        order['user_username'] = user['username'] if user else 'Unknown'
        if status_filter and order.get('status') != status_filter: continue
        orders_with_users.append(order)
    return render_template('orders.html', title='Manage Orders', orders=orders_with_users, current_filter=status_filter)

@admin_bp.route('/orders/view/<order_id>')
@admin_required
def view_order(order_id):
    order = find_order_by_id(order_id)
    if not order: flash('Order not found.', 'danger'); return redirect(url_for('admin.manage_orders'))
    user = find_user_by_id(order.get('user_id'))
    order['user_email'] = user['email'] if user else 'Unknown'
    order['user_username'] = user['username'] if user else 'Unknown'
    valid_statuses = ['Pending', 'Accepted', 'Shipped', 'Delivered', 'Cancelled']
    return render_template('order_detail.html', title='Order Details', order=order, valid_statuses=valid_statuses)

@admin_bp.route('/orders/update_status/<order_id>', methods=['POST'])
@admin_required
def update_order_status_route(order_id):
    new_status = request.form.get('status')
    if not new_status: flash('No status provided.', 'warning'); return redirect(request.referrer or url_for('admin.manage_orders'))
    success = update_order_status(order_id, new_status)
    if success: flash(f'Order status updated to {new_status}.', 'success')
    else: flash('Failed to update order status.', 'danger')
    return redirect(url_for('admin.view_order', order_id=order_id))


# --- User Management Routes ---
# (User routes remain the same)
@admin_bp.route('/users')
@admin_required
def manage_users():
    pending = get_pending_users(); approved = get_approved_users()
    return render_template('users.html', title='Manage Users', pending_users=pending, approved_users=approved)

@admin_bp.route('/users/approve/<user_id>', methods=['POST'])
@admin_required
def approve_user_route(user_id):
    success = approve_user(user_id)
    if success: flash('User approved successfully!', 'success')
    else: flash('Error approving user.', 'danger')
    return redirect(url_for('admin.manage_users'))