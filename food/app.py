import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
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

# Initialize database on startup
DB_PATH = os.path.join(BASE_DIR, 'food_delivery.db')
if not os.path.exists(DB_PATH):
    database.init_db()

# Custom decorators for authentication
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('login_customer'))
        return f(*args, **kwargs)
    return decorated_function

def current_user():
    if 'user_id' in session:
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None

# Inject current_user into all templates
@app.context_processor
def inject_user():
    return dict(current_user=current_user())

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
        
        # Check if email exists
        conn = database.get_db()
        existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        
        if existing_user:
            flash("Email already registered.", "danger")
            conn.close()
            return redirect(url_for('register'))
            
        hashed_pw = generate_password_hash(password)
        
        # Set first user as admin, others as customer
        role = 'admin' if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0 else 'customer'
        
        # Insert User (Auto Verified)
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, address, is_verified, role) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, hashed_pw, address, 1, role)
        )
        user_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        session['user_id'] = user_id
        session['email'] = email
        session['role'] = role
        
        flash("Registration successful! You are now logged in.", "success")
        if role == 'admin':
            return redirect(url_for('seller_dashboard'))
        return redirect(url_for('index'))
        
    return render_template('register.html')

@app.route('/login/customer', methods=['GET', 'POST'])
def login_customer():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if user['role'] != 'customer':
                flash("This portal is for customers only. Please use the producer login.", "danger")
                return redirect(url_for('login_customer'))

            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            flash("Logged in successfully as Customer.", "success")
            return redirect(url_for('index'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login_customer.html')

@app.route('/login/producer', methods=['GET', 'POST'])
def login_producer():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if user['role'] != 'admin':
                flash("This portal is for producers only. Please use the customer login.", "danger")
                return redirect(url_for('login_producer'))

            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            flash("Logged in successfully as Producer.", "success")
            return redirect(url_for('seller_dashboard'))
        else:
            flash("Invalid credentials.", "danger")
            
    return render_template('login_producer.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        conn = database.get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        
        if user:
            # Simulate sending an email by directing them to the reset link.
            flash(f"Success! Click here to reset your password.", "success")
            return redirect(url_for('reset_password', email=email))
        else:
            flash("No account found with that email address.", "danger")
            
    return render_template('forgot_password.html')

@app.route('/reset_password/<email>', methods=['GET', 'POST'])
def reset_password(email):
    if request.method == 'POST':
        new_password = request.form['password']
        hashed_pw = generate_password_hash(new_password)
        
        conn = database.get_db()
        conn.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed_pw, email))
        conn.commit()
        conn.close()
        
        flash("Password reset successfully. Please log in with your new password.", "success")
        return redirect(url_for('login_customer'))
        
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
        price = request.form['price']
        quantity = request.form['quantity']
        
        image_url = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?ixlib=rb-4.0.3&auto=format&fit=crop&w=800&q=80'
        
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(os.path.join(BASE_DIR, file_path))
            image_url = url_for('static', filename='uploads/' + filename)
        
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
    
    # Check if quantity is available
    menu = conn.execute("SELECT quantity FROM menu_updates WHERE id = ?", (menu_id,)).fetchone()
    if not menu or menu['quantity'] <= 0:
        flash("Sorry, this item is sold out!", "danger")
        conn.close()
        return redirect(url_for('index'))
    
    # Deduct quantity and place order
    conn.execute("UPDATE menu_updates SET quantity = quantity - 1 WHERE id = ?", (menu_id,))
    conn.execute(
        "INSERT INTO orders (user_id, menu_id) VALUES (?, ?)",
        (session['user_id'], menu_id)
    )
    conn.commit()
    conn.close()
    
    flash("Order placed successfully! The cook will deliver to your registered address soon.", "success")
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
