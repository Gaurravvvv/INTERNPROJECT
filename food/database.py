import os
from pymongo import MongoClient

# Fetch environment variables for Docker Mongo setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:adminpassword@localhost:27017/")
DATABASE_NAME = "food_delivery"

# Define global client
client = None
db = None

def get_db():
    global client, db
    if client is None:
        client = MongoClient(MONGO_URI)
        db = client[DATABASE_NAME]
    return db

def init_db():
    """
    Initialize indexes or default collections if needed.
    MongoDB creates collections dynamically, but we can set up unique constraints here.
    """
    database = get_db()
    
    # Create unique index for email in users collection
    database.users.create_index("email", unique=True)
    
if __name__ == '__main__':
    init_db()
    print("MongoDB initialized successfully.")
