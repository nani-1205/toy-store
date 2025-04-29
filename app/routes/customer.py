from flask import render_template, redirect, url_for, flash, request, session, abort, current_app
from flask_login import login_required, current_user
from bson import ObjectId
import datetime

from . import customer_bp
# Corrected import to directly access mongo client via get_db
from ..models import (
    find_toy_by_id, update_stock, create_order, get_orders_by_user,
    find_user_by_id, update_user_profile, get_all_toys, get_db # Import get_db
)
from ..forms import AddressPhoneForm, UpdateProfileForm, CartUpdateForm

# --- Customer Dashboard ---
@customer_bp.route('/dashboard')
@login_required
def dashboard():
    """Customer dashboard - shows profile info and links."""
    user_data = find_user_by_id(current_user.get_id()) # Reload data if needed
    # Use the renamed customer dashboard template
    return render_template('customer_dashboard.html', title='My Dashboard', user_data=user_data)

@customer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Allow customer to view/update their address and phone."""
    user_data = find_user_by_id(current_user.get_id())
    if not user_data:
        flash("Could not load your profile data.", "danger")
        return redirect(url_for('customer.dashboard')) # Redirect using the correct endpoint name

    form = UpdateProfileForm(obj=user_data)

    if form.validate_on_submit():
        success = update_user_profile(
            user_id=current_user.get_id(),
            address=form.address.data,
            phone=form.phone.data
        )
        if success:
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('customer.profile')) # Redirect to profile page
        else:
            flash('Error updating profile.', 'danger')
    elif request.method == 'GET':
         form.address.data = user_data.get('address', '')
         form.phone.data = user_data.get('phone', '')

    # Assumes template name is profile.html in customer folder
    return render_template('profile.html', title='My Profile', form=form)


# --- Toy Browsing ---
@customer_bp.route('/toys')
def list_toys():
    """Show all available toys to the customer."""
    toys = get_all_toys(in_stock_only=True)
    # Assumes template name is toy_list.html in customer folder
    return render_template('toy_list.html', title='Our Toys', toys=toys)

@customer_bp.route('/toy/<toy_id>')
def toy_detail(toy_id):
    """Show details of a single toy."""
    toy = find_toy_by_id(toy_id)
    if not toy or toy.get('stock', 0) <= 0:
        flash('Toy not found or unavailable.', 'warning')
        return redirect(url_for('main.index'))
    # Assumes template name is toy_detail.html in customer folder
    return render_template('toy_detail.html', title=toy['name'], toy=toy)


# --- Cart Management ---
@customer_bp.route('/cart')
@login_required
def view_cart():
    """Displays the contents of the shopping cart."""
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0.0

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

    # Assumes template name is cart.html in customer folder
    return render_template('cart.html', title='Shopping Cart', cart_items=cart_items, total_price=total_price, update_form=update_form)


@customer_bp.route('/cart/add/<toy_id>', methods=['POST'])
@login_required
def add_to_cart(toy_id):
    toy = find_toy_by_id(toy_id)
    if not toy:
        flash('Toy not found.', 'danger')
        return redirect(request.referrer or url_for('main.index'))

    quantity = int(request.form.get('quantity', 1))
    if quantity <= 0: quantity = 1

    if toy.get('stock', 0) < quantity:
         flash(f"Not enough stock for {toy['name']}. Only {toy['stock']} available.", 'warning')
         return redirect(request.referrer or url_for('customer.toy_detail', toy_id=toy_id))

    cart = session.get('cart', {})
    cart_item = {
        'name': toy['name'],
        'price': toy['price'],
        'image_url': toy.get('image_url', url_for('static', filename='images/default_toy.png')),
        'quantity': cart.get(toy_id, {}).get('quantity', 0) + quantity
    }

    if toy.get('stock', 0) < cart_item['quantity']:
        flash(f"Cannot add {quantity} more. Total requested exceeds stock for {toy['name']}.", 'warning')
        if toy_id not in cart:
             cart_item['quantity'] = toy.get('stock', 0)
             if cart_item['quantity'] <= 0:
                flash(f"{toy['name']} is now out of stock.", 'warning')
                return redirect(request.referrer or url_for('main.index'))
        else:
            return redirect(request.referrer or url_for('customer.view_cart'))

    cart[toy_id] = cart_item
    session['cart'] = cart
    session.modified = True

    flash(f"{toy['name']} (x{quantity}) added to cart.", 'success')
    return redirect(request.referrer or url_for('customer.view_cart'))


@customer_bp.route('/cart/update/<toy_id>', methods=['POST'])
@login_required
def update_cart_item(toy_id):
    cart = session.get('cart', {})
    if toy_id not in cart:
        flash('Item not found in cart.', 'danger')
        return redirect(url_for('customer.view_cart'))

    form = CartUpdateForm()
    if form.validate_on_submit():
        new_quantity = form.quantity.data
        if new_quantity <= 0:
            return redirect(url_for('customer.remove_from_cart', toy_id=toy_id))

        toy = find_toy_by_id(toy_id)
        if not toy or toy.get('stock', 0) < new_quantity:
            stock_available = toy.get('stock', 0) if toy else 0
            flash(f"Cannot update quantity. Only {stock_available} of {cart[toy_id]['name']} in stock.", 'warning')
            return redirect(url_for('customer.view_cart'))

        cart[toy_id]['quantity'] = new_quantity
        session['cart'] = cart
        session.modified = True
        flash('Cart updated.', 'success')
    else:
        current_app.logger.warning(f"Cart update validation failed for toy {toy_id}: {form.errors}")
        flash('Invalid quantity submitted.', 'danger')

    return redirect(url_for('customer.view_cart'))


@customer_bp.route('/cart/remove/<toy_id>')
@login_required
def remove_from_cart(toy_id):
    cart = session.get('cart', {})
    if toy_id in cart:
        removed_item_name = cart[toy_id]['name']
        del cart[toy_id]
        session['cart'] = cart
        session.modified = True
        flash(f'{removed_item_name} removed from cart.', 'success')
    else:
        flash('Item not found in cart.', 'warning')
    return redirect(url_for('customer.view_cart'))


# --- Checkout Process ---
@customer_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('main.index'))

    user_data = find_user_by_id(current_user.get_id())
    if not user_data:
         flash('Error loading your profile. Please try again.', 'danger')
         return redirect(url_for('customer.view_cart'))

    form = AddressPhoneForm()

    if request.method == 'GET':
        form.address.data = user_data.get('address', '')
        form.phone.data = user_data.get('phone', '')
        if not form.address.data or not form.phone.data:
             flash('Please provide your shipping address and phone number.', 'info')

    if form.validate_on_submit():
        shipping_address = form.address.data
        phone = form.phone.data

        if user_data.get('address') != shipping_address or user_data.get('phone') != phone:
             update_user_profile(current_user.get_id(), shipping_address, phone)

        order_items = []
        total_amount = 0.0
        stock_ok = True

        for toy_id_str, item_data in cart.items():
            toy = find_toy_by_id(toy_id_str)
            if not toy or toy.get('stock', 0) < item_data['quantity']:
                stock_ok = False
                flash(f"Sorry, stock for '{item_data['name']}' changed. Only {toy.get('stock', 0) if toy else 0} available.", 'danger')
                break

            order_items.append({
                'toy_id': ObjectId(toy_id_str),
                'name': item_data['name'],
                'quantity': item_data['quantity'],
                'price': item_data['price']
            })
            total_amount += item_data['price'] * item_data['quantity']

        if not stock_ok:
            return redirect(url_for('customer.view_cart'))

        order_id = create_order(
            user_id=current_user.get_id(),
            items=order_items,
            total_amount=total_amount,
            shipping_address=shipping_address,
            phone=phone
        )

        if order_id:
             stock_deduction_failed = False
             for item in order_items:
                 if not update_stock(item['toy_id'], -item['quantity']):
                      stock_deduction_failed = True
                      current_app.logger.error(f"CRITICAL ERROR: Failed to deduct stock for toy {item['toy_id']} in order {order_id}")
                      flash(f"Error updating stock for {item['name']}. Please contact support regarding order {order_id}.", 'danger')

             if not stock_deduction_failed:
                 session.pop('cart', None)
                 session.modified = True
                 flash('Order placed successfully! Payment via Cash on Delivery.', 'success')
                 return redirect(url_for('customer.order_confirmation', order_id=order_id))
        else:
            flash('There was an error placing your order. Please try again.', 'danger')

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

    # Assumes template name is checkout.html in customer folder
    return render_template('checkout.html',
                           title='Checkout',
                           form=form,
                           cart_items=cart_items_display,
                           total_price=total_price_display)


@customer_bp.route('/order_confirmation/<order_id>')
@login_required
def order_confirmation(order_id):
    """Show a confirmation page after successful checkout."""
    # Assumes template name is order_confirmation.html in customer folder
    return render_template('order_confirmation.html', title='Order Confirmed', order_id=order_id)


# --- Order History ---
@customer_bp.route('/orders') # URL remains /customer/orders
@login_required
def order_history():
    """Displays the customer's past orders."""
    orders = get_orders_by_user(current_user.get_id())
    # --- RENDER THE CORRECT CUSTOMER TEMPLATE ---
    # Uses order_history.html located in app/templates/customer/
    # **Ensure this file exists or change to 'orders.html' if that's your file**
    return render_template('order_history.html', title='My Orders', orders=orders)