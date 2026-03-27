from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Product, Cart, Order, LoginHistory
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from sqlalchemy import func

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    category = request.args.get('category', '')
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if category:
        query = query.filter(Product.category.ilike(f'%{category}%'))
    products = query.paginate(page=page, per_page=10)
    return render_template('index.html', products=products, search=search, min_price=min_price, max_price=max_price, category=category)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        user = User(name=name, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            # Record login activity
            user.last_login = datetime.utcnow()
            login_record = LoginHistory(user_id=user.id, ip_address=request.remote_addr)
            db.session.add(login_record)
            db.session.commit()
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    quantity = int(request.form.get('quantity', 1))
    cart_item = Cart.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = Cart(user_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(cart_item)
    db.session.commit()
    flash('Added to cart')
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def cart():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart/<int:cart_id>', methods=['POST'])
@login_required
def update_cart(cart_id):
    cart_item = Cart.query.get_or_404(cart_id)
    if cart_item.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('cart'))
    quantity = int(request.form['quantity'])
    if quantity > 0:
        cart_item.quantity = quantity
    else:
        db.session.delete(cart_item)
    db.session.commit()
    flash('Cart updated')
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:cart_id>')
@login_required
def remove_from_cart(cart_id):
    cart_item = Cart.query.get_or_404(cart_id)
    if cart_item.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('cart'))
    db.session.delete(cart_item)
    db.session.commit()
    flash('Removed from cart')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Cart is empty')
        return redirect(url_for('cart'))
    total = sum(item.product.price * item.quantity for item in cart_items)
    if request.method == 'POST':
        order = Order(user_id=current_user.id, total_price=total)
        db.session.add(order)
        db.session.commit()
        # Clear cart
        for item in cart_items:
            db.session.delete(item)
        db.session.commit()
        flash('Order placed successfully')
        return redirect(url_for('orders'))
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('orders.html', orders=orders)

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('index'))
    products = Product.query.all()
    return render_template('admin.html', products=products)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('index'))
    
    # Get total users
    total_users = User.query.count()
    
    # Get total logins
    total_logins = LoginHistory.query.count()
    
    # Get users who logged in today
    today = datetime.utcnow().date()
    today_logins = LoginHistory.query.filter(
        func.date(LoginHistory.login_time) == today
    ).count()
    
    # Get login stats by user
    user_login_stats = db.session.query(
        User.id,
        User.name,
        User.email,
        User.last_login,
        func.count(LoginHistory.id).label('login_count')
    ).outerjoin(LoginHistory).group_by(User.id).all()
    
    # Get recent logins
    recent_logins = LoginHistory.query.order_by(LoginHistory.login_time.desc()).limit(20).all()
    
    # Get login stats for last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_logins = db.session.query(
        func.date(LoginHistory.login_time).label('date'),
        func.count(LoginHistory.id).label('count')
    ).filter(LoginHistory.login_time >= seven_days_ago).group_by(
        func.date(LoginHistory.login_time)
    ).order_by(func.date(LoginHistory.login_time)).all()
    
    return render_template('admin_dashboard.html',
                         total_users=total_users,
                         total_logins=total_logins,
                         today_logins=today_logins,
                         user_login_stats=user_login_stats,
                         recent_logins=recent_logins,
                         daily_logins=daily_logins)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        category = request.form.get('category', '')
        image = request.files.get('image')
        image_filename = None
        if image and image.filename:
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename
        product = Product(name=name, price=price, description=description, category=category, image=image_filename)
        db.session.add(product)
        db.session.commit()
        flash('Product added')
        return redirect(url_for('admin'))
    return render_template('add_product.html')

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.price = float(request.form['price'])
        product.description = request.form['description']
        product.category = request.form.get('category', '')
        image = request.files.get('image')
        if image and image.filename:
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            product.image = filename
        db.session.commit()
        flash('Product updated')
        return redirect(url_for('admin'))
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete_product/<int:product_id>')
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        flash('Unauthorized')
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Sample data
        if not User.query.filter_by(email='admin@example.com').first():
            admin = User(name='Admin', email='admin@example.com', password=generate_password_hash('admin', method='pbkdf2:sha256'), is_admin=True)
            db.session.add(admin)
        if not Product.query.first():
            product1 = Product(name='Laptop', price=999.99, description='A powerful laptop', category='Electronics')
            product2 = Product(name='Book', price=19.99, description='An interesting book', category='Books')
            db.session.add(product1)
            db.session.add(product2)
        db.session.commit()
    app.run(debug=True)