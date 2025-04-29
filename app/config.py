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
    MONGO_AUTH_SOURCE = os.environ.get('MONGO_AUTH_SOURCE') # Optional, depends on your MongoDB setup

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'password' # Default if not set

    # Basic sanity checks
    if not SECRET_KEY or SECRET_KEY == 'a_very_strong_random_secret_key_please_change_me':
        raise ValueError("No SECRET_KEY set or default key used. Set a strong SECRET_KEY in your .env file.")
    if not MONGO_URI:
        raise ValueError("No MONGO_URI set. Set MONGO_URI in your .env file.")
    if not MONGO_DB_NAME:
        raise ValueError("No MONGO_DB_NAME set. Set MONGO_DB_NAME in your .env file.")
    if not ADMIN_PASSWORD or ADMIN_PASSWORD == 'your_secure_admin_password':
         print("Warning: Default or example ADMIN_PASSWORD used. Set a strong ADMIN_PASSWORD in your .env file.")