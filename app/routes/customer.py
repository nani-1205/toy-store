from flask import render_template, redirect, url_for, flash, request, session, abort
from flask_login import login_required, current_user
from bson import ObjectId
import datetime

from . import customer_bp
from .. import mongo
from ..models import (find_toy_by_id, update_stock, create_order, get_orders_by_user,
                    find_user_by_id, update_user_profile, get_all_toys)
from ..forms import AddressPhoneForm, UpdateProfileForm, CartUpdateForm

# --- Customer Dashboard ---
@customer_bp.route('/dashboard')
@login_required
def dashboard():
    """Customer dashboard - can show profile info and link to orders."""
    # No specific dashboard content required by prompt other than orders
    # You could add profile view/edit here later or link to it.
    user_data = find_user_by_id(current_user.get_id()) # Reload data if needed
    return render_template('dashboard.html', title='My Dashboard', user_data=user_data)

@customer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Allow customer to view/update their address and phone."""
    user_data = find_user_by_id(current_user.get_id())
    if not user_data:
        flash("Could not load your profile data.", "danger")
        return redirect(url_for('customer.dashboard'))

    # Create form, pre-populate with current user data
    form = UpdateProfileForm(obj=user_data) # Use obj for GET pre-population

    if form.validate_on_submit():
        # Update using form data
        success = update_user_profile(
            user_id=current_user.get_id(),
            address=form.address.data,
            phone=form.phone.data
        )
        if success:
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('customer.profile'))
        else:
            flash('Error updating profile.', 'danger')
    elif request.method == 'GET':
         # Ensure fields are filled on initial load if obj didn't cover everything
         form.address.data = user_data.get('address', '')
         form.phone.data = user_data.get('phone', '')


    return render_template('profile.html', title='My Profile', form=form)


# --- Toy Browsing ---
@customer_bp.route('/toys')
def list_toys():
    """Show all available toys to the customer."""
    toys = get_all_toys(in_stock_only=True)
    return render_template('toy_list.html', title='Our Toys', toys=toys)

@customer_bp.route('/toy/<toy_id>')
def toy_detail(toy_id):
    """Show details of a single toy."""
    toy = find_toy_by_id(toy_id)
    if not toy or toy.get('stock', 0) <= 0: # Also hide if out of stock
        flash('Toy not found or unavailable.', 'warning')
        return redirect(url_for('main.index'))
    return render_template('toy_detail.html', title=toy['name'], toy=toy)


# --- Cart Management ---
@customer_bp.route('/cart/add/<toy_id>', methods=['POST'])
@login_required # Require login to add to cart
def add_to_cart(toy_id):
    """Adds an item to the session cart."""
    toy = find_toy_by_id(toy_id)
    if not toy:
        flash('Toy not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    quantity = int(request.form.get('quantity', 1)) # Get quantity from form if available
    if quantity <= 0:
         quantity = 1

    if toy.get('stock', 0) < quantity:
         flash(f"Not enough stock for {toy['name']}. Only {toy['stock']} available.", 'warning')
         return redirect(request.referrer or url_for('customer.toy_detail', toy_id=toy_id))


    cart = session.get('cart', {}) # Get cart from session or initialize empty dict

    # Store essential info in cart
    cart_item = {
        'name': toy['name'],
        'price': toy['price'],
        'image_url': toy.get('image_url', url_for('static', filename='images/default_toy.png')), # Default image if none
        'quantity': cart.get(toy_id, {}).get('quantity', 0) + quantity # Add to existing quantity
    }

    # Check stock again for cumulative quantity
    if toy.get('stock', 0) < cart_item['quantity']:
        flash(f"Cannot add {quantity} more. Total requested exceeds stock for {toy['name']}.", 'warning')
        # Adjust quantity to max available if adding for the first time
        if toy_id not in cart:
             cart_item['quantity'] = toy.get('stock', 0)
             if cart_item['quantity'] <= 0: # If somehow stock became 0
                flash(f"{toy['name']} is now out of stock.", 'warning')
                return redirect(request.referrer or url_for('main.index'))
        else: # If item was already in cart, don't change existing quantity on error
            return redirect(request.referrer or url_for('customer.cart'))


    cart[toy_id] = cart_item # Add/update item in cart dict using toy_id as key
    session['cart'] = cart # Save cart back to session
    session.modified = True # Mark session as modified

    flash(f"{toy['name']} (x{quantity}) added to cart.", 'success')
    return redirect(request.referrer or url_for('customer.cart'))


@customer_bp.route('/cart')
@login_required
def view_cart():
    """Displays the contents of the shopping cart."""
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0.0

    # Create list of items with calculated subtotal for the template
    for toy_id, item_data in cart.items():
        subtotal = item_data['price'] * item_data['quantity']
        cart_items.append({
            'id': toy_id,
            'name': item_data['name'],
            'price': item_data['price'],
            'quantity': item_data['quantity'],
            'image_url': item_data.get('image_url', ''),
            'subtotal': subtotal
        })
        total_price += subtotal

    update_form = CartUpdateForm() # For inline updates

    return render_template('cart.html', title='Shopping Cart', cart_items=cart_items, total_price=total_price, update_form=update_form)


@customer_bp.route('/cart/update/<toy_id>', methods=['POST'])
@login_required
def update_cart_item(toy_id):
    """Updates the quantity of an item in the cart."""
    cart = session.get('cart', {})
    if toy_id not in cart:
        flash('Item not found in cart.', 'danger')
        return redirect(url_for('customer.cart'))

    form = CartUpdateForm() # Use form for validation
    if form.validate_on_submit():
        new_quantity = form.quantity.data
        if new_quantity <= 0: # Treat 0 or less as removal
            return redirect(url_for('customer.remove_from_cart', toy_id=toy_id))

        # Check stock before updating
        toy = find_toy_by_id(toy_id)
        if not toy or toy.get('stock', 0) < new_quantity:
            stock_available = toy.get('stock', 0) if toy else 0
            flash(f"Cannot update quantity. Only {stock_available} of {cart[toy_id]['name']} in stock.", 'warning')
            return redirect(url_for('customer.cart'))

        cart[toy_id]['quantity'] = new_quantity
        session['cart'] = cart
        session.modified = True
        flash('Cart updated.', 'success')
    else:
        flash('Invalid quantity.', 'danger') # Or show form errors

    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/remove/<toy_id>')
@login_required
def remove_from_cart(toy_id):
    """Removes an item from the cart."""
    cart = session.get('cart', {})
    if toy_id in cart:
        removed_item_name = cart[toy_id]['name']
        del cart[toy_id]
        session['cart'] = cart
        session.modified = True
        flash(f'{removed_item_name} removed from cart.', 'success')
    else:
        flash('Item not found in cart.', 'warning')
    return redirect(url_for('customer.cart'))


# --- Checkout Process ---
@customer_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Handles the checkout process: address confirmation and order placement."""
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('main.index'))

    user_data = find_user_by_id(current_user.get_id())
    if not user_data:
         flash('Error loading your profile. Please try again.', 'danger')
         return redirect(url_for('customer.cart'))

    form = AddressPhoneForm()

    # Pre-populate form with user's saved details if available
    if request.method == 'GET':
        form.address.data = user_data.get('address', '')
        form.phone.data = user_data.get('phone', '')
        # Check if address or phone is missing
        if not form.address.data or not form.phone.data:
             flash('Please provide your shipping address and phone number.', 'info')


    if form.validate_on_submit():
        shipping_address = form.address.data
        phone = form.phone.data

        # Optional: Update user profile with entered details if they differ
        if user_data.get('address') != shipping_address or user_data.get('phone') != phone:
             update_user_profile(current_user.get_id(), shipping_address, phone)
             # Don't flash message here, success is placing the order

        # --- Prepare order details ---
        order_items = []
        total_amount = 0.0
        stock_ok = True

        # Critical Section: Re-check stock and prepare items list
        # In a high-traffic site, you might need DB-level locking here
        for toy_id_str, item_data in cart.items():
            toy = find_toy_by_id(toy_id_str)
            if not toy or toy.get('stock', 0) < item_data['quantity']:
                stock_ok = False
                flash(f"Sorry, stock for '{item_data['name']}' changed. Only {toy.get('stock', 0) if toy else 0} available.", 'danger')
                break # Stop processing order

            order_items.append({
                'toy_id': ObjectId(toy_id_str), # Store ObjectId in order
                'name': item_data['name'],
                'quantity': item_data['quantity'],
                'price': item_data['price'] # Price at time of order
            })
            total_amount += item_data['price'] * item_data['quantity']

        if not stock_ok:
            # Redirect back to cart if stock check failed
            return redirect(url_for('customer.cart'))

        # --- If stock is OK, create order and deduct stock ---
        order_id = create_order(
            user_id=current_user.get_id(),
            items=order_items,
            total_amount=total_amount,
            shipping_address=shipping_address,
            phone=phone
        )

        if order_id:
             # Deduct stock for each item AFTER order is successfully created
             stock_deduction_failed = False
             for item in order_items:
                 if not update_stock(item['toy_id'], -item['quantity']):
                      # This is problematic - order created but stock not deducted.
                      # Needs robust handling (e.g., mark order for review, log error)
                      stock_deduction_failed = True
                      print(f"CRITICAL ERROR: Failed to deduct stock for toy {item['toy_id']} in order {order_id}")
                      flash(f"Error updating stock for {item['name']}. Please contact support regarding order {order_id}.", 'danger')
                      # Maybe cancel the order automatically? update_order_status(order_id, 'Cancelled - Stock Error')

             if stock_deduction_failed:
                 # Decide how to proceed - maybe don't clear cart yet
                 pass # Keep cart for now, let user see the error message
             else:
                 # Clear the cart on successful order placement and stock deduction
                 session.pop('cart', None)
                 session.modified = True
                 flash('Order placed successfully! Payment via Cash on Delivery.', 'success')
                 return redirect(url_for('customer.order_confirmation', order_id=order_id))
        else:
            flash('There was an error placing your order. Please try again.', 'danger')
            # Don't clear cart if order creation failed

    # --- Render checkout page for GET or failed POST validation ---
    # Recalculate cart details for display
    cart_items_display = []
    total_price_display = 0.0
    for toy_id, item_data in cart.items():
        subtotal = item_data['price'] * item_data['quantity']
        cart_items_display.append({
            'id': toy_id,
            'name': item_data['name'],
            'price': item_data['price'],
            'quantity': item_data['quantity'],
            'subtotal': subtotal
        })
        total_price_display += subtotal

    return render_template('checkout.html',
                           title='Checkout',
                           form=form,
                           cart_items=cart_items_display,
                           total_price=total_price_display)


@customer_bp.route('/order_confirmation/<order_id>')
@login_required
def order_confirmation(order_id):
    """Show a confirmation page after successful checkout."""
    # Optional: Fetch order details again to display summary
    # order = find_order_by_id(order_id)
    # if not order or str(order.get('user_id')) != current_user.get_id():
    #     flash("Order not found or access denied.", "warning")
    #     return redirect(url_for('customer.order_history'))
    return render_template('order_confirmation.html', title='Order Confirmed', order_id=order_id)


# --- Order History ---
@customer_bp.route('/orders')
@login_required
def order_history():
    """Displays the customer's past orders."""
    orders = get_orders_by_user(current_user.get_id())
    return render_template('orders.html', title='My Orders', orders=orders)