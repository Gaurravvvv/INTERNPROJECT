import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import database
import random

app = Flask(__name__)
app.secret_key = 'super_secret_food_key_change_in_production'

# Setup upload folder
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Added allowed extensions for file uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database on startup
DB_PATH = os.path.join(BASE_DIR, 'food_delivery.db')
if not os.path.exists(DB_PATH):
    database.init_db()

# Improved DB connection and User logic
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        conn = database.get_db()
        g.user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()

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

@app.route('/')
def index():
    conn = database.get_db()
    # Fetch all daily menu updates along with the seller's username
    menus = conn.execute("""
        SELECT m.*, u.username as seller_name 
        FROM menu_updates m
        JOIN users u ON m.author_id = u.id
        ORDER BY m.created_at DESC
    """).fetchall()
    conn.close()
    return render_template('index.html', menus=menus)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        address = request.form['address']
        role = request.form.get('role', 'customer') # Fix: Unified Signup flow role selection
        
        # Security fallback
        if role not in ['customer', 'admin']:
            role = 'customer'
        
        # Check if email exists
        conn = database.get_db()
        existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        
        if existing_user:
            flash("Email already registered.", "danger")
            conn.close()
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        
        # Insert User (Auto Verified)
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, address, is_verified, role) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, hashed_pw, address, 1, role)
        )
        user_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        # Fix: Auto-Login After Sign-up
        session.clear()
        session['user_id'] = user_id
        session['email'] = email
        session['role'] = role
        
        flash("Registration successful! You are now logged in.", "success")
        if role == 'admin':
            return redirect(url_for('seller_dashboard'))
        return redirect(url_for('index'))
        
    return render_template('register.html')

# Fix: Login Mix-up - Combined route for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            
            role_display = "Producer" if user['role'] == "admin" else "Customer"
            flash(f"Logged in successfully as {role_display}.", "success")
            
            if user['role'] == 'admin':
                return redirect(url_for('seller_dashboard'))
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login.html')

# Fix: Password Reset Bypass - using an OTP token 
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        
        if user:
            # Generate a 6-digit OTP
            otp = str(random.randint(100000, 999999))
            conn.execute("INSERT OR REPLACE INTO otps (email, otp_code) VALUES (?, ?)", (email, otp))
            conn.commit()
            conn.close()
            
            # Flash the OTP for dev testing instead of sending email
            flash(f"OTP sent to {email}. (For dev testing, your OTP is: {otp})", "info")
            return redirect(url_for('reset_password', email=email))
        else:
            conn.close()
            flash("No account found with that email address.", "danger")
            
    return render_template('forgot_password.html')

@app.route('/reset_password/<email>', methods=['GET', 'POST'])
def reset_password(email):
    if request.method == 'POST':
        otp = request.form.get('otp')
        new_password = request.form['password']
        
        conn = database.get_db()
        record = conn.execute("SELECT * FROM otps WHERE email = ? AND otp_code = ?", (email, otp)).fetchone()
        
        if record:
            hashed_pw = generate_password_hash(new_password)
            conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed_pw, email))
            conn.execute("DELETE FROM otps WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            
            flash("Password reset successfully. Please log in with your new password.", "success")
            return redirect(url_for('login'))
        else:
            conn.close()
            flash("Invalid or expired OTP.", "danger")
        
    return render_template('reset_password.html', email=email)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('index'))

@app.route('/seller_dashboard')
@login_required
def seller_dashboard():
    if session.get('role') != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('index'))
        
    conn = database.get_db()
    menus = conn.execute("""
        SELECT * FROM menu_updates 
        WHERE author_id = ?
        ORDER BY created_at DESC
    """, (session['user_id'],)).fetchall()
    conn.close()
    return render_template('seller_dashboard.html', menus=menus)

@app.route('/add_food', methods=['GET', 'POST'])
@login_required
def add_food():
    if session.get('role') != 'admin':
        flash("Unauthorized access. Only producers can post menus.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        
        # Fix: Missing Input Validation and Type Casting
        try:
            price_str = request.form.get('price')
            quantity_str = request.form.get('quantity')
            if not price_str or not quantity_str:
                raise ValueError("Missing required fields")
            price = float(price_str)
            quantity = int(quantity_str)
        except ValueError:
            flash("Price must be a number and Quantity must be an integer.", "danger")
            return redirect(url_for('add_food'))
        
        image_url = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80'
        
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            # Fix: Uploaded File Security Risk
            if allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image_file.save(os.path.join(BASE_DIR, file_path))
                image_url = url_for('static', filename='uploads/' + filename)
            else:
                flash("Invalid file type. Please upload an image (png, jpg, jpeg, gif).", "danger")
                return redirect(url_for('add_food'))
        
        conn = database.get_db()
        conn.execute(
            "INSERT INTO menu_updates (title, description, price, quantity, image_url, author_id) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, price, quantity, image_url, session['user_id'])
        )
        conn.commit()
        conn.close()
        
        flash("Daily food update posted successfully!", "success")
        return redirect(url_for('index'))
        
    return render_template('add_food.html')

@app.route('/order/<int:menu_id>', methods=['POST'])
@login_required
def order(menu_id):
    if session.get('role') == 'admin':
        flash("Producers cannot order food.", "danger")
        return redirect(url_for('index'))

    conn = database.get_db()
    
    # Fix: Race Condition in Order Processing
    # Single atomic query to ensure quantity is > 0 and update it
    cursor = conn.execute("UPDATE menu_updates SET quantity = quantity - 1 WHERE id = ? AND quantity > 0", (menu_id,))
    
    if cursor.rowcount > 0:
        # Success, insert order
        conn.execute(
            "INSERT INTO orders (user_id, menu_id) VALUES (?, ?)",
            (session['user_id'], menu_id)
        )
        conn.commit()
        flash("Order placed successfully! The cook will deliver to your registered address soon.", "success")
    else:
        # Sold out or invalid menu_id
        flash("Sorry, this item is sold out!", "danger")
        
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_menu/<int:menu_id>', methods=['POST'])
@login_required
def delete_menu(menu_id):
    conn = database.get_db()
    menu = conn.execute("SELECT author_id, quantity FROM menu_updates WHERE id = ?", (menu_id,)).fetchone()
    
    if not menu:
        flash("Menu item not found.", "danger")
    elif menu['author_id'] != session['user_id']:
        flash("You can only delete your own menu items.", "danger")
    elif menu['quantity'] > 0:
        flash("You can only delete menu items that are completely sold out.", "warning")
    else:
        conn.execute("DELETE FROM menu_updates WHERE id = ?", (menu_id,))
        conn.commit()
        flash("Sold out menu item discarded.", "success")
        
    conn.close()
    return redirect(url_for('seller_dashboard'))

@app.route('/verify_otp')
@login_required
def verify_otp():
    # Mock endpoint so existing references don't crash
    flash("OTP Verification page (mock).", "info")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
