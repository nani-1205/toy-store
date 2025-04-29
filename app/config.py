# File: app/config.py

import os
from dotenv import load_dotenv

# Load .env file from the parent directory relative to this file
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
dotenv_path = os.path.join(basedir, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print("Warning: .env file not found in project root. Relying on system environment variables.")

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    MONGO_URI = os.environ.get('MONGO_URI')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME')
    MONGO_AUTH_SOURCE = os.environ.get('MONGO_AUTH_SOURCE') # Optional

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'password'

    # --- >>> Upload Folder Configuration <<< ---
    # Store uploads inside the static folder relative to the app's root path
    # Example: kondapalli_toys/app/static/uploads/toys
    UPLOAD_FOLDER = os.path.join(basedir, 'app', 'static', 'uploads', 'toys')

    # Optional: Max upload size (e.g., 5MB) - Flask default is unlimited
    # MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    # --- >>> End Upload Folder Configuration <<< ---


    # Basic sanity checks
    if not SECRET_KEY or SECRET_KEY == 'a_very_strong_random_secret_key_please_change_me':
        raise ValueError("No SECRET_KEY set or default key used. Set a strong SECRET_KEY in your .env file.")
    if not MONGO_URI:
        raise ValueError("No MONGO_URI set. Set MONGO_URI in your .env file.")
    if not MONGO_DB_NAME:
        raise ValueError("No MONGO_DB_NAME set. Set MONGO_DB_NAME in your .env file.")
    if not ADMIN_PASSWORD or ADMIN_PASSWORD == 'your_secure_admin_password':
         print("Warning: Default or example ADMIN_PASSWORD used. Set a strong ADMIN_PASSWORD in your .env file.")
    if not os.path.exists(basedir): # Check if base path calculation is valid
         print(f"Warning: Calculated base directory '{basedir}' does not exist.")