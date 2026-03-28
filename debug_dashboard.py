import os
import sys
# Make sure we can import food.app
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), 'food'))
from app import app
import traceback

app.config['TESTING'] = True
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'dummy' # We need a valid ObjectId string
        sess['role'] = 'seller'

    # Actually we just want the error traceback!
    # Wait, the error occurs for a real logged in seller. 
    # Let's use the real seller account.
    from food import database
    db = database.get_db()
    
    # We need to make sure the dummy user exists in the DB so user setup logic passes
    seller_user = db.users.find_one({"username": "seller"})
    if not seller_user:
        print("Seller not found")
        sys.exit(1)
        
    with c.session_transaction() as sess:
        sess['user_id'] = str(seller_user['_id'])
        sess['role'] = 'seller'
        
    try:
        response = c.get('/seller_dashboard')
        print(response.data.decode('utf-8')[:500])
    except Exception as e:
        traceback.print_exc()
