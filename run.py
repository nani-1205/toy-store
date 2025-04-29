import os
from dotenv import load_dotenv

# Load environment variables from .env file first
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print("Warning: .env file not found. Using system environment variables.")

# Import the app factory AFTER loading .env
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Use host='0.0.0.0' to make it accessible on your network
    app.run(host='0.0.0.0', port=5000)