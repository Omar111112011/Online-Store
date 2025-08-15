import os
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, Length
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from datetime import datetime
import functools

# ----------------- CONFIGURATION ----------------- #
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_and_complex_key_for_production'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'store.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')
app.config['MAIL_DEFAULT_SENDER'] = ('خضار أونلاين', os.environ.get('EMAIL_USER'))

# ----------------- INITIALIZATIONS ----------------- #
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.login_message = "الرجاء تسجيل الدخول للوصول إلى هذه الصفحة."

# ----------------- DATABASE MODELS ----------------- #
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='customer', lazy=True)

    @property
    def password(self): raise AttributeError('password is not a readable attribute')
    @password.setter
    def password(self, password): self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    def verify_password(self, password): return bcrypt.check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(255), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    customer_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), nullable=False, default='قيد التنفيذ')
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

# Forms and other functions remain the same
class RegistrationForm(FlaskForm):
    name = StringField('الاسم الكامل', validators=[DataRequired(), Length(min=2, max=150)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[DataRequired(), EqualTo('password', message='كلمتا المرور غير متطابقتين')])
    submit = SubmitField('إنشاء حساب')
    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first(): raise ValidationError('هذا البريد الإلكتروني مسجل بالفعل.')

class LoginForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    submit = SubmitField('تسجيل الدخول')

class CheckoutForm(FlaskForm):
    name = StringField('الاسم الكامل', validators=[DataRequired()])
    address = StringField('العنوان بالتفصيل', validators=[DataRequired()])
    phone = StringField('رقم الهاتف', validators=[DataRequired()])
    submit = SubmitField('تأكيد الطلب')

@login_manager.user_loader
def load_user(user_id): return User.query.get(int(user_id))

def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('ليس لديك الصلاحية للوصول لهذه الصفحة.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def send_order_notification_email(order):
    msg = Message(f"طلب جديد #{order.id} من موقع خضار أونلاين", recipients=["gomaataman09@gmail.com"])
    msg.html = render_template('email_template.html', order=order)
    try: mail.send(msg)
    except Exception as e: app.logger.error(f"Failed to send email: {e}")

# Routes remain the same...
@app.route("/")
def home():
    products = Product.query.all()
    return render_template('home.html', products=products)
# ...
# Only init-db is changed
# ...
@app.route("/add_to_cart/<int:product_id>", methods=['POST'])
def add_to_cart(product_id):
    if 'cart' not in session: session['cart'] = {}
    cart = session['cart']
    product_id_str = str(product_id)
    quantity = int(request.form.get('quantity', 1))
    if quantity > 0:
        cart[product_id_str] = cart.get(product_id_str, 0) + quantity
        session.modified = True
        flash(f'تمت إضافة {quantity} كيلو من المنتج إلى السلة!', 'success')
    else: flash('الرجاء إدخال كمية صحيحة.', 'warning')
    return redirect(request.referrer or url_for('home'))

# ... Other routes are unchanged ...
# (register, login, logout, cart, update_cart, remove_from_cart, checkout, order_confirmation, my_orders, admin_dashboard, complete_order)
# The full code for these is omitted for brevity but should be the same as the previous version.
# Let's add them back to be complete.

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(name=form.name.data, email=form.email.data, password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('تم إنشاء حسابك بنجاح! يمكنك الآن تسجيل الدخول.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='إنشاء حساب', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.verify_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash('تم تسجيل الدخول بنجاح.', 'success')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('فشل تسجيل الدخول. يرجى التحقق من البريد الإلكتروني وكلمة المرور.', 'danger')
    return render_template('login.html', title='تسجيل الدخول', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop('cart', None)
    flash('تم تسجيل الخروج.', 'info')
    return redirect(url_for('home'))

@app.route("/cart")
def view_cart():
    cart_items, total_price = [], 0
    if 'cart' in session:
        for product_id, quantity in session['cart'].items():
            product = Product.query.get(product_id)
            if product:
                item_total = product.price * quantity
                cart_items.append({'product': product, 'quantity': quantity, 'total': item_total})
                total_price += item_total
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route("/update_cart/<int:product_id>", methods=['POST'])
def update_cart(product_id):
    if 'cart' in session:
        quantity, product_id_str = int(request.form.get('quantity', 1)), str(product_id)
        if quantity > 0: session['cart'][product_id_str] = quantity
        else: session['cart'].pop(product_id_str, None)
        session.modified = True
    return redirect(url_for('view_cart'))

@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):
    if 'cart' in session:
        session['cart'].pop(str(product_id), None)
        session.modified = True
    return redirect(url_for('view_cart'))
    
@app.route("/checkout", methods=['GET', 'POST'])
@login_required
def checkout():
    if not session.get('cart'): return redirect(url_for('home'))
    form = CheckoutForm()
    if form.validate_on_submit():
        total_price = 0
        order = Order(user_id=current_user.id, total_price=0, customer_name=form.name.data, address=form.address.data, phone=form.phone.data)
        db.session.add(order)
        db.session.commit()
        for product_id, quantity in session['cart'].items():
            product = Product.query.get(product_id)
            if product:
                order_item = OrderItem(order_id=order.id, product_id=product.id, quantity=quantity, price=product.price)
                db.session.add(order_item)
                total_price += product.price * quantity
        order.total_price = total_price
        db.session.commit()
        send_order_notification_email(order)
        session.pop('cart', None)
        return redirect(url_for('order_confirmation', order_id=order.id))
    if request.method == 'GET': form.name.data = current_user.name
    cart_items, total_price = [], 0
    for product_id, quantity in session['cart'].items():
        product = Product.query.get(product_id)
        if product:
            item_total = product.price * quantity
            cart_items.append({'product': product, 'quantity': quantity, 'total': item_total})
            total_price += item_total
    return render_template('checkout.html', form=form, cart_items=cart_items, total_price=total_price)
    
@app.route('/order_confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin: return redirect(url_for('home'))
    return render_template('order_confirmation.html', order=order)

@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
    return render_template('my_orders.html', orders=orders)

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    orders = Order.query.order_by(Order.order_date.desc()).all()
    return render_template('admin_dashboard.html', orders=orders)

@app.route('/admin/complete_order/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def complete_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'تم التوصيل'
    db.session.commit()
    flash(f'تم تحديث حالة الطلب رقم #{order.id} إلى "تم التوصيل".', 'success')
    return redirect(url_for('admin_dashboard'))

@app.cli.command("init-db")
def init_db_command():
    """Creates the database tables and initial data."""
    with app.app_context():
        db.create_all()
        print("Database tables created.")

        if not User.query.filter_by(email="gomaataman09@gmail.com").first():
            admin_user = User(name="Gomaa Taman", email="gomaataman09@gmail.com", password="Gomaa11@()", is_admin=True)
            db.session.add(admin_user)
            print("Admin user created.")
        
        if Product.query.count() == 0:
            # #############################################################
            # ##               THIS IS THE UPDATED SECTION               ##
            # #############################################################
            products_data = [
                {'name': 'طماطم', 'price': 8.50, 'image_url': 'images/tomato.jpg'},
                {'name': 'خيار', 'price': 12.00, 'image_url': 'images/cucumber.jpg'},
                {'name': 'بطاطس', 'price': 10.00, 'image_url': 'images/potato.jpg'},
                {'name': 'بصل', 'price': 7.50, 'image_url': 'images/onion.jpg'},
                {'name': 'تفاح أحمر', 'price': 35.00, 'image_url': 'images/redapple.jpg'},
                {'name': 'موز بلدي', 'price': 15.00, 'image_url': 'images/banana.jpg'},
                {'name': 'برتقال', 'price': 9.00, 'image_url': 'images/orange.jpg'},
                {'name': 'فراولة', 'price': 25.00, 'image_url': 'images/strawberry.jpg'},
            ]
            for p in products_data:
                db.session.add(Product(name=p['name'], price=p['price'], image_url=p['image_url']))
            print("Sample products added.")

        db.session.commit()
        print("Database initialized successfully!")

if __name__ == '__main__':
    app.run(debug=True)