from flask import current_app # Import current_app to access config within functions
from bson import ObjectId
# Keep mongo import for mongo.cx, but we won't use mongo.db directly
from app import mongo, bcrypt
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# Helper function to get the database handle reliably
def get_db():
    """Gets the MongoDB database handle using mongo.cx and configured DB name."""
    # Use current_app to access config within request context or app context
    db_name = current_app.config.get('MONGO_DBNAME')
    if not db_name:
        # This should not happen if __init__.py setup is correct, but good practice
        raise RuntimeError("MONGO_DBNAME not configured in Flask app.")
    # Access the database directly via the client connection 'cx'
    # mongo.cx should be valid if startup succeeded
    if not hasattr(mongo, 'cx') or mongo.cx is None:
         raise RuntimeError("MongoDB client connection (mongo.cx) not available.")
    return mongo.cx[db_name]

# --- User Functions ---
def create_user(username, email, password, address=None, phone=None):
    """Creates a new user, initially not approved."""
    db = get_db() # Get DB handle
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    user_data = {
        'username': username.lower(),
        'email': email.lower(),
        'password_hash': hashed_password,
        'address': address,
        'phone': phone,
        'is_approved': False, # Requires admin approval
        'created_at': datetime.now(IST)
    }
    try:
        result = db.users.insert_one(user_data) # Use db.users
        return result.inserted_id
    except Exception as e:
        current_app.logger.error(f"Error creating user: {e}") # Log error
        return None

def find_user_by_email(email):
    db = get_db() # Get DB handle
    return db.users.find_one({'email': email.lower()})

def find_user_by_username(username):
    db = get_db() # Get DB handle
    return db.users.find_one({'username': username.lower()})

def find_user_by_id(user_id):
    db = get_db() # Get DB handle
    try:
        return db.users.find_one({'_id': ObjectId(user_id)})
    except Exception:
        return None

def get_pending_users():
    db = get_db() # Get DB handle
    return list(db.users.find({'is_approved': False}).sort('created_at', 1))

def get_approved_users():
    db = get_db() # Get DB handle
    return list(db.users.find({'is_approved': True}).sort('created_at', 1))

def approve_user(user_id):
    db = get_db() # Get DB handle
    try:
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_approved': True}}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error approving user {user_id}: {e}")
        return False

def update_user_profile(user_id, address, phone):
    db = get_db() # Get DB handle
    try:
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'address': address, 'phone': phone, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating profile for user {user_id}: {e}")
        return False

# --- Toy Functions ---
def add_toy(name, description, price, image_url, stock):
    db = get_db() # Get DB handle
    toy_data = {
        'name': name,
        'description': description,
        'price': float(price), # Store price as float
        'image_url': image_url,
        'stock': int(stock),
        'created_at': datetime.now(IST),
        'updated_at': datetime.now(IST)
    }
    result = db.toys.insert_one(toy_data) # Use db.toys
    return result.inserted_id

def get_all_toys(in_stock_only=False):
    db = get_db() # Get DB handle
    query = {}
    if in_stock_only:
        query['stock'] = {'$gt': 0}
    return list(db.toys.find(query).sort('name', 1)) # Use db.toys

def find_toy_by_id(toy_id):
    db = get_db() # Get DB handle
    try:
        return db.toys.find_one({'_id': ObjectId(toy_id)})
    except Exception:
        return None

def update_toy(toy_id, name, description, price, image_url, stock):
    db = get_db() # Get DB handle
    try:
        result = db.toys.update_one(
            {'_id': ObjectId(toy_id)},
            {'$set': {
                'name': name,
                'description': description,
                'price': float(price),
                'image_url': image_url,
                'stock': int(stock),
                'updated_at': datetime.now(IST)
            }}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating toy {toy_id}: {e}")
        return False

def delete_toy(toy_id):
    db = get_db() # Get DB handle
    try:
        result = db.toys.delete_one({'_id': ObjectId(toy_id)})
        return result.deleted_count > 0
    except Exception as e:
        current_app.logger.error(f"Error deleting toy {toy_id}: {e}")
        return False

def update_stock(toy_id, quantity_change):
    db = get_db() # Get DB handle
    try:
        # Ensure enough stock if decreasing (quantity_change is negative)
        # Check needs to happen *before* the update if possible, or handle error
        # Simple atomic update:
        result = db.toys.update_one(
            {'_id': ObjectId(toy_id), 'stock': {'$gte': -quantity_change}}, # Condition ensures stock doesn't go below zero
            {'$inc': {'stock': quantity_change}}
        )
        if result.matched_count == 0 and quantity_change < 0:
             # This means update didn't happen, likely due to insufficient stock
             current_app.logger.warning(f"Stock update failed for toy {toy_id}, likely insufficient stock for change {quantity_change}")
             return False
        return result.modified_count > 0 # Returns true if stock was changed
    except Exception as e:
        current_app.logger.error(f"Error updating stock for toy {toy_id}: {e}")
        return False

# --- Order Functions ---
def create_order(user_id, items, total_amount, shipping_address, phone):
    db = get_db() # Get DB handle
    order_data = {
        'user_id': ObjectId(user_id),
        'items': items, # List of dicts: {'toy_id': ObjectId, 'name': str, 'quantity': int, 'price': float}
        'total_amount': total_amount,
        'shipping_address': shipping_address,
        'phone': phone,
        'status': 'Pending', # Initial status
        'payment_method': 'Cash on Delivery',
        'created_at': datetime.now(IST)
    }
    result = db.orders.insert_one(order_data) # Use db.orders
    return result.inserted_id

def get_all_orders(sort_by='created_at', ascending=False):
    db = get_db() # Get DB handle
    direction = -1 if not ascending else 1
    return list(db.orders.find().sort(sort_by, direction)) # Use db.orders

def get_orders_by_user(user_id, sort_by='created_at', ascending=False):
    db = get_db() # Get DB handle
    direction = -1 if not ascending else 1
    try:
        return list(db.orders.find({'user_id': ObjectId(user_id)}).sort(sort_by, direction))
    except Exception:
        return []

def find_order_by_id(order_id):
    db = get_db() # Get DB handle
    try:
        return db.orders.find_one({'_id': ObjectId(order_id)})
    except Exception:
        return None

def update_order_status(order_id, new_status):
    db = get_db() # Get DB handle
    valid_statuses = ['Pending', 'Accepted', 'Shipped', 'Delivered', 'Cancelled']
    if new_status not in valid_statuses:
        return False # Invalid status

    try:
        result = db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating status for order {order_id}: {e}")
        return False

# --- Statistics ---
def get_admin_stats():
    db = get_db() # Get DB handle
    try:
        stats = {
            'total_toys': db.toys.count_documents({}),
            'total_customers': db.users.count_documents({'is_approved': True}),
            'pending_approvals': db.users.count_documents({'is_approved': False}),
            'total_orders': db.orders.count_documents({}),
            'pending_orders': db.orders.count_documents({'status': 'Pending'}),
            'accepted_orders': db.orders.count_documents({'status': 'Accepted'}),
        }
        return stats
    except Exception as e:
         current_app.logger.error(f"Error getting admin stats: {e}")
         # Return zeros or None if stats cannot be retrieved
         return {k: 0 for k in ['total_toys', 'total_customers', 'pending_approvals', 'total_orders', 'pending_orders', 'accepted_orders']}