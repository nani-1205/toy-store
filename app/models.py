# File: app/models.py

from flask import current_app
from bson import ObjectId
from app import mongo, bcrypt # Keep mongo import for get_db() helper
from datetime import datetime
import pytz
import traceback # Import traceback for better exception printing

IST = pytz.timezone('Asia/Kolkata')

# Helper function to get the database handle reliably
def get_db():
    db_name = current_app.config.get('MONGO_DBNAME')
    if not db_name: raise RuntimeError("MONGO_DBNAME not configured.")
    if not hasattr(mongo, 'cx') or mongo.cx is None: raise RuntimeError("mongo.cx not available.")
    return mongo.cx[db_name]

# --- User Functions (Corrected Formatting) ---
def create_user(username, email, password, address=None, phone=None):
    db = get_db()
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    user_data = {
        'username': username.lower(),
        'email': email.lower(),
        'password_hash': hashed_password,
        'address': address,
        'phone': phone,
        'is_approved': False,
        'created_at': datetime.now(IST)
    }
    try:
        result = db.users.insert_one(user_data)
        return result.inserted_id
    except Exception as e:
        current_app.logger.error(f"Error creating user: {e}", exc_info=True)
        return None

def find_user_by_email(email):
    db = get_db()
    return db.users.find_one({'email': email.lower()})

def find_user_by_username(username):
    db = get_db()
    return db.users.find_one({'username': username.lower()})

def find_user_by_id(user_id):
    """Finds a user by their MongoDB ObjectId string."""
    db = get_db()
    try:
        # Ensure user_id is a valid ObjectId before querying
        obj_id = ObjectId(user_id)
        return db.users.find_one({'_id': obj_id})
    except Exception as e:
        # Log if it's an invalid ID format or other error
        current_app.logger.warning(f"Error finding user by ID '{user_id}': {e}")
        return None

def get_pending_users():
    db = get_db()
    return list(db.users.find({'is_approved': False}).sort('created_at', 1))

def get_approved_users():
    db = get_db()
    return list(db.users.find({'is_approved': True}).sort('created_at', 1))

def approve_user(user_id):
    db = get_db()
    try:
        result = db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_approved': True}})
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error approving user {user_id}: {e}", exc_info=True)
        return False

def update_user_profile(user_id, address, phone):
    db = get_db()
    try:
        result = db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'address': address, 'phone': phone, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating profile for user {user_id}: {e}", exc_info=True)
        return False


# --- Toy Functions (Corrected Formatting) ---
def add_toy(name, description, price, image_path, stock):
    db = get_db()
    toy_data = {
        'name': name, 'description': description, 'price': float(price),
        'image_path': image_path, 'stock': int(stock),
        'created_at': datetime.now(IST), 'updated_at': datetime.now(IST)
    }
    try:
        result = db.toys.insert_one(toy_data)
        return result.inserted_id
    except Exception as e:
         current_app.logger.error(f"Error adding toy '{name}': {e}", exc_info=True)
         return None

def get_all_toys(in_stock_only=False):
    db = get_db()
    query = {}
    if in_stock_only:
        query['stock'] = {'$gt': 0}
    return list(db.toys.find(query).sort('name', 1))

def find_toy_by_id(toy_id):
    db = get_db()
    try:
        obj_id = ObjectId(toy_id)
        return db.toys.find_one({'_id': obj_id})
    except Exception as e:
        current_app.logger.warning(f"Error finding toy by ID '{toy_id}': {e}")
        return None

def update_toy(toy_id, name, description, price, image_path, stock):
    db = get_db()
    try:
        result = db.toys.update_one(
            {'_id': ObjectId(toy_id)},
            {'$set': {
                'name': name, 'description': description, 'price': float(price),
                'image_path': image_path, 'stock': int(stock),
                'updated_at': datetime.now(IST)
            }}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating toy {toy_id}: {e}", exc_info=True)
        return False

def delete_toy(toy_id):
    db = get_db()
    try:
        result = db.toys.delete_one({'_id': ObjectId(toy_id)})
        return result.deleted_count > 0
    except Exception as e:
        current_app.logger.error(f"Error deleting toy {toy_id}: {e}", exc_info=True)
        return False

def update_stock(toy_id, quantity_change):
    db = get_db()
    try:
        result = db.toys.update_one(
            {'_id': ObjectId(toy_id), 'stock': {'$gte': -quantity_change}},
            {'$inc': {'stock': quantity_change}}
        )
        if result.matched_count == 0 and quantity_change < 0:
             current_app.logger.warning(f"Stock update failed for toy {toy_id}, likely insufficient stock for change {quantity_change}")
             return False
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating stock for toy {toy_id}: {e}", exc_info=True)
        return False

# --- Order Functions (Corrected Formatting) ---
def create_order(user_id, items, total_amount, shipping_address, phone):
    db = get_db()
    order_data = {
        'user_id': ObjectId(user_id), 'items': items, 'total_amount': total_amount,
        'shipping_address': shipping_address, 'phone': phone, 'status': 'Pending',
        'payment_method': 'Cash on Delivery', 'created_at': datetime.now(IST)
    }
    try:
        result = db.orders.insert_one(order_data)
        return result.inserted_id
    except Exception as e:
        current_app.logger.error(f"Error creating order for user {user_id}: {e}", exc_info=True)
        return None


def get_all_orders(sort_by='created_at', ascending=False):
    db = get_db()
    direction = -1 if not ascending else 1
    return list(db.orders.find().sort(sort_by, direction))

def get_orders_by_user(user_id, sort_by='created_at', ascending=False):
    db = get_db()
    direction = -1 if not ascending else 1
    try:
        obj_id = ObjectId(user_id)
        return list(db.orders.find({'user_id': obj_id}).sort(sort_by, direction))
    except Exception as e:
        current_app.logger.warning(f"Error getting orders for user ID '{user_id}': {e}")
        return []

def find_order_by_id(order_id):
    db = get_db()
    try:
        obj_id = ObjectId(order_id)
        return db.orders.find_one({'_id': obj_id})
    except Exception as e:
        current_app.logger.warning(f"Error finding order by ID '{order_id}': {e}")
        return None

def update_order_status(order_id, new_status):
    db = get_db()
    valid_statuses = ['Pending', 'Accepted', 'Shipped', 'Delivered', 'Cancelled']
    if new_status not in valid_statuses: return False
    try:
        result = db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
    except Exception as e:
        current_app.logger.error(f"Error updating status for order {order_id}: {e}", exc_info=True)
        return False


# --- Statistics (Corrected Formatting) ---
def get_admin_stats():
    db = get_db()
    default_stats = {k: 0 for k in ['total_toys', 'total_customers', 'pending_approvals', 'total_orders', 'pending_orders', 'accepted_orders']}
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
         current_app.logger.error(f"Error getting admin stats: {e}", exc_info=True)
         return default_stats # Return zeros if stats cannot be retrieved