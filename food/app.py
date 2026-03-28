import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
import database
import random
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_food_key_change_in_production'

# Setup upload folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Seed Default Users
def seed_default_users():
    db = database.get_db()
    users_col = db.users
    defaults = [
        {"username": "buyer", "password": "buyer", "role": "buyer", "profile_setup": True},
        {"username": "buyer1", "password": "buyer1", "role": "buyer", "profile_setup": True},
        {"username": "seller", "password": "seller", "role": "seller", "profile_setup": True},
        {"username": "seller1", "password": "seller1", "role": "seller", "profile_setup": True}
    ]
    for d in defaults:
        if not users_col.find_one({"username": d["username"]}):
            users_col.insert_one({
                "username": d["username"],
                "email": f"{d['username']}@example.com",
                "password_hash": generate_password_hash(d["password"]),
                "role": d["role"],
                "profile_setup": True,
                "address": "Test Address",
                "restaurant_name": f"{d['username']}'s Kitchen" if d['role'] == 'seller' else None
            })

# Improved DB connection and User logic
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        db = database.get_db()
        try:
            user = db.users.find_one({"_id": ObjectId(str(user_id))})
            if user:
                # Convert ObjectId to string for easy JSON/template usage if needed
                user['_id'] = str(user['_id'])
            g.user = user
        except Exception:
            # Handle old SQLite integer session IDs or invalid ObjectIds
            session.clear()
            g.user = None

@app.context_processor
def inject_user():
    return dict(current_user=g.get('user'))

# Custom decorators for authentication
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.get('user') is None:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def profile_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.get('user') and not g.user.get('profile_setup', False):
            flash("Please complete your profile setup first.", "warning")
            return redirect(url_for('profile_setup'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if g.user is None:
        return redirect(url_for('login'))
        
    db = database.get_db()
    
    if g.user['role'] == 'seller':
        return redirect(url_for('seller_dashboard'))
    
    # Check for search query
    query = request.args.get('q', '')
    filter_query = {}
    if query:
        filter_query = {
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]
        }
    
    # Fetch all menus
    menus = list(db.menu_updates.find(filter_query).sort("created_at", -1))
    for m in menus:
        m['_id'] = str(m['_id'])
        seller = db.users.find_one({"_id": ObjectId(m['author_id'])})
        m['seller_name'] = seller.get('restaurant_name', seller.get('username')) if seller else 'Unknown'
        
    return render_template('index.html', menus=menus)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role', 'buyer')
        
        db = database.get_db()
        existing_user = db.users.find_one({"$or": [{"email": email}, {"username": username}]})
        
        if existing_user:
            flash("Username or Email already registered.", "danger")
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        
        result = db.users.insert_one({
            "username": username,
            "email": email,
            "password_hash": hashed_pw,
            "role": role,
            "profile_setup": False
        })
        
        session.clear()
        session['user_id'] = str(result.inserted_id)
        session['role'] = role
        
        flash("Registration successful! Let's setup your profile.", "success")
        return redirect(url_for('profile_setup'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = database.get_db()
        user = db.users.find_one({"username": username})
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = str(user['_id'])
            session['role'] = user['role']
            
            flash(f"Logged in successfully as {user['role']}.", "success")
            
            if not user.get('profile_setup'):
                return redirect(url_for('profile_setup'))
                
            if user['role'] == 'seller':
                return redirect(url_for('seller_dashboard'))
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login.html')

@app.route('/profile_setup', methods=['GET', 'POST'])
@login_required
def profile_setup():
    if request.method == 'POST':
        db = database.get_db()
        update_data = {"profile_setup": True}
        
        if g.user['role'] == 'seller':
            update_data['restaurant_name'] = request.form.get('restaurant_name')
            update_data['address'] = request.form.get('address')
        else:
            update_data['full_name'] = request.form.get('full_name')
            update_data['address'] = request.form.get('address')
            
        db.users.update_one({"_id": ObjectId(g.user['_id'])}, {"$set": update_data})
        flash("Profile setup complete!", "success")
        return redirect(url_for('index'))
        
    return render_template('profile_setup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/seller_dashboard')
@login_required
@profile_required
def seller_dashboard():
    if session.get('role') != 'seller':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('index'))
        
    db = database.get_db()
    
    # Menus
    menus = list(db.menu_updates.find({"author_id": g.user['_id']}).sort("created_at", -1))
    for m in menus: m['_id'] = str(m['_id'])
    
    # Orders
    orders = list(db.orders.find({"seller_id": g.user['_id']}).sort("created_at", -1))
    for o in orders: o['_id'] = str(o['_id'])
    
    return render_template('seller_dashboard.html', menus=menus, orders=orders)

@app.route('/add_food', methods=['GET', 'POST'])
@login_required
@profile_required
def add_food():
    if session.get('role') != 'seller':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        try:
            price_str = request.form.get('price')
            quantity_str = request.form.get('quantity')
            price = float(price_str)
            quantity = int(quantity_str)
        except (ValueError, TypeError):
            flash("Price and Quantity must be valid numbers.", "danger")
            return redirect(url_for('add_food'))
        
        image_url = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80'
        
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            if allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image_file.save(os.path.join(BASE_DIR, file_path))
                image_url = url_for('static', filename='uploads/' + filename)
            else:
                flash("Invalid file type.", "danger")
                return redirect(url_for('add_food'))
        
        db = database.get_db()
        db.menu_updates.insert_one({
            "title": title,
            "description": description,
            "price": price,
            "quantity": quantity,
            "image_url": image_url,
            "author_id": g.user['_id'],
            "created_at": datetime.utcnow()
        })
        
        flash("Food menu added successfully!", "success")
        return redirect(url_for('seller_dashboard'))
        
    return render_template('add_food.html')

@app.route('/edit_food/<menu_id>', methods=['GET', 'POST'])
@login_required
@profile_required
def edit_food(menu_id):
    if session.get('role') != 'seller':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('index'))

    db = database.get_db()
    try:
        menu = db.menu_updates.find_one({"_id": ObjectId(menu_id), "author_id": g.user['_id']})
    except Exception:
        flash("Invalid menu ID.", "danger")
        return redirect(url_for('seller_dashboard'))
    
    if not menu:
        flash("Menu item not found.", "danger")
        return redirect(url_for('seller_dashboard'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        try:
            price = float(request.form.get('price'))
            quantity = int(request.form.get('quantity'))
        except (ValueError, TypeError):
            flash("Price and Quantity must be valid numbers.", "danger")
            return redirect(url_for('edit_food', menu_id=menu_id))
        
        update_data = {
            "title": title,
            "description": description,
            "price": price,
            "quantity": quantity
        }
        
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            if allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image_file.save(os.path.join(BASE_DIR, file_path))
                update_data['image_url'] = url_for('static', filename='uploads/' + filename)
            else:
                flash("Invalid file type.", "danger")
                return redirect(url_for('edit_food', menu_id=menu_id))
                
        db.menu_updates.update_one({"_id": ObjectId(menu_id)}, {"$set": update_data})
        flash("Food menu updated successfully!", "success")
        return redirect(url_for('seller_dashboard'))
        
    return render_template('edit_food.html', menu=menu)

@app.route('/delete_food/<menu_id>', methods=['POST'])
@login_required
@profile_required
def delete_food(menu_id):
    if session.get('role') != 'seller':
        return redirect(url_for('index'))
        
    db = database.get_db()
    try:
        result = db.menu_updates.delete_one({"_id": ObjectId(menu_id), "author_id": g.user['_id']})
        if result.deleted_count > 0:
            flash("Menu item deleted successfully.", "success")
        else:
            flash("Could not delete item or not found.", "danger")
    except Exception:
        flash("Invalid menu ID.", "danger")
        
    return redirect(url_for('seller_dashboard'))

@app.route('/cart/add/<menu_id>', methods=['POST'])
@login_required
def add_to_cart(menu_id):
    if session.get('role') == 'seller':
        return redirect(url_for('seller_dashboard'))
        
    db = database.get_db()
    menu = db.menu_updates.find_one({"_id": ObjectId(menu_id)})
    
    if not menu or menu['quantity'] < 1:
        flash("Item unavailable.", "danger")
        return redirect(url_for('index'))
        
    cart = session.get('cart', [])
    
    # Check if already in cart
    found = False
    for item in cart:
        if item['menu_id'] == menu_id:
            item['qty'] += 1
            found = True
            break
            
    if not found:
        cart.append({
            "menu_id": menu_id,
            "seller_id": str(menu['author_id']),
            "title": menu['title'],
            "price": menu['price'],
            "qty": 1
        })
        
    session['cart'] = cart
    session.modified = True
    flash("Added to cart!", "success")
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
@profile_required
def cart():
    return render_template('cart.html', cart=session.get('cart', []))

@app.route('/checkout', methods=['POST'])
@login_required
@profile_required
def checkout():
    cart = session.get('cart', [])
    if not cart:
        flash("Your cart is empty.", "danger")
        return redirect(url_for('index'))
        
    db = database.get_db()
    
    # Group items by seller
    items_by_seller = {}
    for item in cart:
        sid = item['seller_id']
        if sid not in items_by_seller:
            items_by_seller[sid] = []
        items_by_seller[sid].append(item)
        
        # Decrement quantity in DB
        db.menu_updates.update_one(
            {"_id": ObjectId(item['menu_id']), "quantity": {"$gte": item['qty']}},
            {"$inc": {"quantity": -item['qty']}}
        )
        # Note: If stock runs out mid-transaction, stricter checking would throw an error here.
        # MVP assumption is sufficient stock.
        
    for seller_id, items in items_by_seller.items():
        total = sum(i['price'] * i['qty'] for i in items)
        db.orders.insert_one({
            "buyer_id": g.user['_id'],
            "buyer_name": g.user.get('full_name', g.user['username']),
            "buyer_address": g.user.get('address'),
            "seller_id": seller_id,
            "items": items,
            "total_price": total,
            "status": "Pending",
            "created_at": datetime.utcnow()
        })
        
    session['cart'] = []
    session.modified = True
    flash("Order placed successfully! Waiting for sellers to accept.", "success")
    return redirect(url_for('index'))

@app.route('/accept_order/<order_id>', methods=['POST'])
@login_required
def accept_order(order_id):
    if g.user['role'] != 'seller':
        return redirect(url_for('index'))
        
    db = database.get_db()
    db.orders.update_one(
        {"_id": ObjectId(order_id), "seller_id": g.user['_id']},
        {"$set": {"status": "Accepted"}}
    )
    flash("Order accepted!", "success")
    return redirect(url_for('seller_dashboard'))

@app.route('/reject_order/<order_id>', methods=['POST'])
@login_required
def reject_order(order_id):
    if g.user['role'] != 'seller':
        return redirect(url_for('index'))
        
    db = database.get_db()
    
    # Logic to restore quantity on reject could go here
    db.orders.update_one(
        {"_id": ObjectId(order_id), "seller_id": g.user['_id']},
        {"$set": {"status": "Rejected"}}
    )
    flash("Order rejected.", "info")
    return redirect(url_for('seller_dashboard'))

@app.route('/my_orders')
@login_required
def my_orders():
    if g.user['role'] != 'buyer':
        return redirect(url_for('index'))
        
    db = database.get_db()
    orders = list(db.orders.find({"buyer_id": g.user['_id']}).sort("created_at", -1))
    for o in orders:
        o['_id'] = str(o['_id'])
        seller = db.users.find_one({"_id": ObjectId(o['seller_id'])})
        o['seller_name'] = seller.get('restaurant_name', 'A Restaurant') if seller else 'Unknown'
        
    return render_template('my_orders.html', orders=orders)

if __name__ == '__main__':
    database.init_db()
    seed_default_users() # ensure users exist on startup
    app.run(debug=True, port=5000)
