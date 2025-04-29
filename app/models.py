from bson import ObjectId
from app import mongo, bcrypt
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# --- User Functions ---
def create_user(username, email, password, address=None, phone=None):
    """Creates a new user, initially not approved."""
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
        result = mongo.db.users.insert_one(user_data)
        return result.inserted_id
    except Exception as e: # Handle potential duplicate key errors etc.
        print(f"Error creating user: {e}")
        return None

def find_user_by_email(email):
    return mongo.db.users.find_one({'email': email.lower()})

def find_user_by_username(username):
     return mongo.db.users.find_one({'username': username.lower()})

def find_user_by_id(user_id):
    try:
        return mongo.db.users.find_one({'_id': ObjectId(user_id)})
    except Exception:
        return None

def get_pending_users():
    return list(mongo.db.users.find({'is_approved': False}).sort('created_at', 1))

def get_approved_users():
    return list(mongo.db.users.find({'is_approved': True}).sort('created_at', 1))

def approve_user(user_id):
    try:
        result = mongo.db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_approved': True}}
        )
        return result.modified_count > 0
    except Exception:
        return False

def update_user_profile(user_id, address, phone):
     try:
        result = mongo.db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'address': address, 'phone': phone, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
     except Exception:
        return False


# --- Toy Functions ---
def add_toy(name, description, price, image_url, stock):
    toy_data = {
        'name': name,
        'description': description,
        'price': float(price), # Store price as float
        'image_url': image_url,
        'stock': int(stock),
        'created_at': datetime.now(IST),
        'updated_at': datetime.now(IST)
    }
    result = mongo.db.toys.insert_one(toy_data)
    return result.inserted_id

def get_all_toys(in_stock_only=False):
    query = {}
    if in_stock_only:
        query['stock'] = {'$gt': 0}
    return list(mongo.db.toys.find(query).sort('name', 1))

def find_toy_by_id(toy_id):
    try:
        return mongo.db.toys.find_one({'_id': ObjectId(toy_id)})
    except Exception:
        return None

def update_toy(toy_id, name, description, price, image_url, stock):
    try:
        result = mongo.db.toys.update_one(
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
    except Exception:
        return False

def delete_toy(toy_id):
    try:
        result = mongo.db.toys.delete_one({'_id': ObjectId(toy_id)})
        return result.deleted_count > 0
    except Exception:
        return False

def update_stock(toy_id, quantity_change):
    """ Atomically updates stock. quantity_change is negative for sales. """
    try:
        result = mongo.db.toys.update_one(
            {'_id': ObjectId(toy_id), 'stock': {'$gte': -quantity_change}}, # Ensure enough stock if decreasing
            {'$inc': {'stock': quantity_change}}
        )
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating stock for toy {toy_id}: {e}")
        return False

# --- Order Functions ---
def create_order(user_id, items, total_amount, shipping_address, phone):
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
    result = mongo.db.orders.insert_one(order_data)
    return result.inserted_id

def get_all_orders(sort_by='created_at', ascending=False):
    direction = -1 if not ascending else 1
    return list(mongo.db.orders.find().sort(sort_by, direction))

def get_orders_by_user(user_id, sort_by='created_at', ascending=False):
    direction = -1 if not ascending else 1
    try:
        return list(mongo.db.orders.find({'user_id': ObjectId(user_id)}).sort(sort_by, direction))
    except Exception:
        return []

def find_order_by_id(order_id):
    try:
        return mongo.db.orders.find_one({'_id': ObjectId(order_id)})
    except Exception:
        return None

def update_order_status(order_id, new_status):
    valid_statuses = ['Pending', 'Accepted', 'Shipped', 'Delivered', 'Cancelled']
    if new_status not in valid_statuses:
        return False # Invalid status

    # Add logic here if stock needs adjustment on cancellation (e.g., put items back)
    # This can get complex depending on when stock was initially decremented.
    # Assuming stock was decremented at checkout confirmation.
    # If cancelling an 'Accepted' or 'Shipped' order, consider adding stock back.

    try:
        result = mongo.db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': new_status, 'updated_at': datetime.now(IST)}}
        )
        return result.modified_count > 0
    except Exception:
        return False

# --- Statistics ---
def get_admin_stats():
    stats = {
        'total_toys': mongo.db.toys.count_documents({}),
        'total_customers': mongo.db.users.count_documents({'is_approved': True}),
        'pending_approvals': mongo.db.users.count_documents({'is_approved': False}),
        'total_orders': mongo.db.orders.count_documents({}),
        'pending_orders': mongo.db.orders.count_documents({'status': 'Pending'}),
        'accepted_orders': mongo.db.orders.count_documents({'status': 'Accepted'}),
    }
    return stats