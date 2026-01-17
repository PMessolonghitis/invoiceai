"""
InvoiceAI - AI-Powered Invoice Generator for Freelancers
A complete SaaS application for creating professional invoices
"""

import os
import json
import uuid
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from dateutil.relativedelta import relativedelta

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:////tmp/invoiceai.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# Health check endpoint
@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

# =============================================================================
# DATABASE MODELS
# =============================================================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(100))
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    logo_url = db.Column(db.String(500))


    # Settings
    default_currency = db.Column(db.String(3), default='USD')
    default_payment_terms = db.Column(db.Integer, default=30)
    default_notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    clients = db.relationship('Client', backref='user', lazy=True, cascade='all, delete-orphan')
    invoices = db.relationship('Invoice', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can_create_invoice(self):
        """Check if user can create more invoices - always returns True (free for all)"""
        return True


class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    company_name = db.Column(db.String(100))
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    invoices = db.relationship('Invoice', backref='client', lazy=True)


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    invoice_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, sent, paid, overdue, cancelled

    # Dates
    issue_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    due_date = db.Column(db.Date, nullable=False)
    paid_date = db.Column(db.Date)

    # Financial
    currency = db.Column(db.String(3), default='USD')
    subtotal = db.Column(db.Float, default=0)
    tax_rate = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    # Content
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)

    # Template
    template = db.Column(db.String(20), default='modern')

    # Tracking
    view_count = db.Column(db.Integer, default=0)
    first_viewed_at = db.Column(db.DateTime)
    last_viewed_at = db.Column(db.DateTime)
    public_link = db.Column(db.String(100), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('InvoiceView', backref='invoice', lazy=True, cascade='all, delete-orphan')

    def calculate_totals(self):
        """Recalculate invoice totals"""
        self.subtotal = sum(item.total for item in self.items)
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount - self.discount_amount

    def generate_public_link(self):
        """Generate a unique public link for the invoice"""
        self.public_link = str(uuid.uuid4())


class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)

    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    def calculate_total(self):
        self.total = self.quantity * self.unit_price


class InvoiceView(db.Model):
    """Track when invoices are viewed by clients"""
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)

    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))  # IPv6 max length
    user_agent = db.Column(db.String(500))
    is_notified = db.Column(db.Boolean, default=False)  # Whether user has seen this notification


class Notification(db.Model):
    """User notifications for invoice views and other events"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    type = db.Column(db.String(50), nullable=False)  # invoice_viewed, invoice_paid, etc.
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    link = db.Column(db.String(500))  # URL to related item

    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('notifications', lazy=True, cascade='all, delete-orphan'))


class RecurringInvoice(db.Model):
    """Template for recurring invoices that auto-generate on schedule"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)  # Friendly name for the recurring invoice
    status = db.Column(db.String(20), default='active')  # active, paused, cancelled

    # Schedule
    frequency = db.Column(db.String(20), nullable=False)  # weekly, monthly, quarterly, yearly
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)  # Optional end date
    next_invoice_date = db.Column(db.Date, nullable=False)
    last_generated = db.Column(db.Date)

    # Invoice template data
    currency = db.Column(db.String(3), default='USD')
    tax_rate = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    payment_terms_days = db.Column(db.Integer, default=30)
    template = db.Column(db.String(20), default='modern')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('recurring_invoices', lazy=True, cascade='all, delete-orphan'))
    client = db.relationship('Client', backref=db.backref('recurring_invoices', lazy=True))
    items = db.relationship('RecurringInvoiceItem', backref='recurring_invoice', lazy=True, cascade='all, delete-orphan')

    @property
    def subtotal(self):
        return sum(item.total for item in self.items)

    @property
    def tax_amount(self):
        return self.subtotal * (self.tax_rate / 100)

    @property
    def total(self):
        return self.subtotal + self.tax_amount - self.discount_amount

    def calculate_next_date(self, from_date=None):
        """Calculate the next invoice date based on frequency"""
        base_date = from_date or self.next_invoice_date
        if self.frequency == 'weekly':
            return base_date + timedelta(weeks=1)
        elif self.frequency == 'monthly':
            return base_date + relativedelta(months=1)
        elif self.frequency == 'quarterly':
            return base_date + relativedelta(months=3)
        elif self.frequency == 'yearly':
            return base_date + relativedelta(years=1)
        return base_date + relativedelta(months=1)  # Default to monthly


class RecurringInvoiceItem(db.Model):
    """Line items for recurring invoice template"""
    id = db.Column(db.Integer, primary_key=True)
    recurring_invoice_id = db.Column(db.Integer, db.ForeignKey('recurring_invoice.id'), nullable=False)

    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    def calculate_total(self):
        self.total = self.quantity * self.unit_price


class Estimate(db.Model):
    """Estimates/Quotes that can be converted to invoices"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)

    estimate_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, sent, accepted, declined, expired, converted

    # Dates
    issue_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    valid_until = db.Column(db.Date, nullable=False)

    # Financial
    currency = db.Column(db.String(3), default='USD')
    subtotal = db.Column(db.Float, default=0)
    tax_rate = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    # Content
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)

    # Template
    template = db.Column(db.String(20), default='modern')

    # Tracking
    view_count = db.Column(db.Integer, default=0)
    public_link = db.Column(db.String(100), unique=True)

    # Conversion tracking
    converted_invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('estimates', lazy=True, cascade='all, delete-orphan'))
    client = db.relationship('Client', backref=db.backref('estimates', lazy=True))
    items = db.relationship('EstimateItem', backref='estimate', lazy=True, cascade='all, delete-orphan')
    converted_invoice = db.relationship('Invoice', backref='source_estimate', foreign_keys=[converted_invoice_id])

    def calculate_totals(self):
        """Recalculate estimate totals"""
        self.subtotal = sum(item.total for item in self.items)
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount - self.discount_amount

    def generate_public_link(self):
        """Generate a unique public link for the estimate"""
        self.public_link = str(uuid.uuid4())


class EstimateItem(db.Model):
    """Line items for estimates"""
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)

    description = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    def calculate_total(self):
        self.total = self.quantity * self.unit_price


# =============================================================================
# AUTHENTICATION
# =============================================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        data = request.form

        if User.query.filter_by(email=data['email'].lower()).first():
            flash('Email already registered', 'error')
            return render_template('register.html')

        user = User(
            email=data['email'].lower(),
            name=data['name'],
            company_name=data.get('company_name', '')
        )
        user.set_password(data['password'])

        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Welcome to InvoiceAI!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        data = request.form
        user = User.query.filter_by(email=data['email'].lower()).first()

        if user and user.check_password(data['password']):
            login_user(user, remember=data.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))

        flash('Invalid email or password', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def update_overdue_invoices():
    """Mark sent invoices as overdue if past due date"""
    today = datetime.utcnow().date()
    overdue = Invoice.query.filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'sent',
        Invoice.due_date < today
    ).all()
    for inv in overdue:
        inv.status = 'overdue'
    if overdue:
        db.session.commit()


# =============================================================================
# MAIN PAGES
# =============================================================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/dashboard')
@login_required
def dashboard():
    # Process any due recurring invoices
    generated_count = process_recurring_invoices()
    if generated_count > 0:
        flash(f'{generated_count} recurring invoice(s) auto-generated', 'info')

    # Get statistics
    total_invoices = Invoice.query.filter_by(user_id=current_user.id).count()
    paid_invoices = Invoice.query.filter_by(user_id=current_user.id, status='paid').count()
    pending_amount = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status.in_(['sent', 'overdue'])
    ).scalar() or 0

    # Recurring invoice stats
    active_recurring = RecurringInvoice.query.filter_by(user_id=current_user.id, status='active').count()

    # Recent invoices
    recent_invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(
        Invoice.created_at.desc()
    ).limit(5).all()

    # Check for overdue invoices and update status
    update_overdue_invoices()

    return render_template('dashboard.html',
        total_invoices=total_invoices,
        paid_invoices=paid_invoices,
        pending_amount=pending_amount,
        recent_invoices=recent_invoices,
        active_recurring=active_recurring
    )


# =============================================================================
# CLIENT MANAGEMENT
# =============================================================================

@app.route('/clients')
@login_required
def clients():
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()
    return render_template('clients.html', clients=clients)


@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def new_client():
    if request.method == 'POST':
        data = request.form
        client = Client(
            user_id=current_user.id,
            name=data['name'],
            email=data.get('email', ''),
            company_name=data.get('company_name', ''),
            address=data.get('address', ''),
            phone=data.get('phone', ''),
            notes=data.get('notes', '')
        )
        db.session.add(client)
        db.session.commit()
        flash('Client added successfully', 'success')
        return redirect(url_for('clients'))

    return render_template('client_form.html', client=None)


@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        data = request.form
        client.name = data['name']
        client.email = data.get('email', '')
        client.company_name = data.get('company_name', '')
        client.address = data.get('address', '')
        client.phone = data.get('phone', '')
        client.notes = data.get('notes', '')
        db.session.commit()
        flash('Client updated successfully', 'success')
        return redirect(url_for('clients'))

    return render_template('client_form.html', client=client)


@app.route('/clients/<int:client_id>/delete', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    flash('Client deleted', 'success')
    return redirect(url_for('clients'))


# =============================================================================
# INVOICE MANAGEMENT
# =============================================================================

@app.route('/invoices')
@login_required
def invoices():
    # Auto-update overdue invoices
    update_overdue_invoices()

    status_filter = request.args.get('status', 'all')
    group_by_client = request.args.get('group', 'false') == 'true'

    query = Invoice.query.filter_by(user_id=current_user.id)

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    invoices_list = query.order_by(Invoice.created_at.desc()).all()

    # Group by client if requested
    grouped_invoices = {}
    if group_by_client:
        for invoice in invoices_list:
            client_name = invoice.client.name
            if client_name not in grouped_invoices:
                grouped_invoices[client_name] = []
            grouped_invoices[client_name].append(invoice)

    return render_template('invoices.html',
        invoices=invoices_list,
        grouped_invoices=grouped_invoices,
        group_by_client=group_by_client,
        status_filter=status_filter
    )


def generate_next_invoice_number(user_id):
    """Generate the next auto invoice number for a user"""
    last_invoice = Invoice.query.filter_by(user_id=user_id).order_by(Invoice.id.desc()).first()
    if last_invoice:
        try:
            last_num = int(last_invoice.invoice_number.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    return f"INV-{datetime.utcnow().strftime('%Y%m')}-{new_num:04d}"


@app.route('/invoices/new', methods=['GET', 'POST'])
@login_required
def new_invoice():
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        # Use manual invoice number if provided, otherwise auto-generate
        invoice_number = data.get('invoice_number', '').strip()
        if not invoice_number:
            invoice_number = generate_next_invoice_number(current_user.id)

        invoice = Invoice(
            user_id=current_user.id,
            client_id=int(data['client_id']),
            invoice_number=invoice_number,
            issue_date=datetime.strptime(data['issue_date'], '%Y-%m-%d').date(),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date(),
            currency=data.get('currency', current_user.default_currency),
            tax_rate=float(data.get('tax_rate', 0)),
            discount_amount=float(data.get('discount_amount', 0)),
            notes=data.get('notes', ''),
            terms=data.get('terms', ''),
            template=data.get('template', 'modern')
        )
        invoice.generate_public_link()

        db.session.add(invoice)
        db.session.flush()  # Get the invoice ID

        # Add items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        invoice.calculate_totals()
        db.session.commit()

        flash('Invoice created successfully', 'success')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

    # Default dates
    today = datetime.utcnow().date()
    due_date = today + timedelta(days=current_user.default_payment_terms)

    # Generate next invoice number for placeholder
    next_invoice_number = generate_next_invoice_number(current_user.id)

    return render_template('invoice_form.html',
        invoice=None,
        clients=clients,
        today=today,
        due_date=due_date,
        next_invoice_number=next_invoice_number
    )


@app.route('/invoices/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    return render_template('invoice_view.html', invoice=invoice)


@app.route('/invoices/<int:invoice_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        # Allow updating invoice number
        new_invoice_number = data.get('invoice_number', '').strip()
        if new_invoice_number:
            invoice.invoice_number = new_invoice_number

        invoice.client_id = int(data['client_id'])
        invoice.issue_date = datetime.strptime(data['issue_date'], '%Y-%m-%d').date()
        invoice.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
        invoice.currency = data.get('currency', 'USD')
        invoice.tax_rate = float(data.get('tax_rate', 0))
        invoice.discount_amount = float(data.get('discount_amount', 0))
        invoice.notes = data.get('notes', '')
        invoice.terms = data.get('terms', '')
        invoice.template = data.get('template', 'modern')

        # Remove old items
        InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()

        # Add new items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        invoice.calculate_totals()
        db.session.commit()

        flash('Invoice updated successfully', 'success')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))

    return render_template('invoice_form.html',
        invoice=invoice,
        clients=clients,
        next_invoice_number=invoice.invoice_number
    )


@app.route('/invoices/<int:invoice_id>/delete', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    db.session.delete(invoice)
    db.session.commit()
    flash('Invoice deleted', 'success')
    return redirect(url_for('invoices'))


@app.route('/invoices/<int:invoice_id>/status', methods=['POST'])
@login_required
def update_invoice_status(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    new_status = request.form.get('status')

    if new_status in ['draft', 'sent', 'paid', 'overdue', 'cancelled']:
        invoice.status = new_status
        if new_status == 'paid':
            invoice.paid_date = datetime.utcnow().date()
        db.session.commit()
        flash(f'Invoice marked as {new_status}', 'success')

    return redirect(url_for('view_invoice', invoice_id=invoice.id))


@app.route('/invoices/<int:invoice_id>/duplicate', methods=['POST'])
@login_required
def duplicate_invoice(invoice_id):
    original = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()

    # Generate new invoice number
    last_invoice = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.id.desc()).first()
    new_num = int(last_invoice.invoice_number.split('-')[-1]) + 1 if last_invoice else 1
    invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m')}-{new_num:04d}"

    new_invoice = Invoice(
        user_id=current_user.id,
        client_id=original.client_id,
        invoice_number=invoice_number,
        status='draft',
        issue_date=datetime.utcnow().date(),
        due_date=datetime.utcnow().date() + timedelta(days=current_user.default_payment_terms),
        currency=original.currency,
        tax_rate=original.tax_rate,
        discount_amount=original.discount_amount,
        notes=original.notes,
        terms=original.terms,
        template=original.template
    )
    new_invoice.generate_public_link()

    db.session.add(new_invoice)
    db.session.flush()

    # Copy items
    for item in original.items:
        new_item = InvoiceItem(
            invoice_id=new_invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.total
        )
        db.session.add(new_item)

    new_invoice.calculate_totals()
    db.session.commit()

    flash('Invoice duplicated successfully', 'success')
    return redirect(url_for('edit_invoice', invoice_id=new_invoice.id))


# =============================================================================
# PUBLIC INVOICE VIEW
# =============================================================================

@app.route('/i/<public_link>')
def public_invoice(public_link):
    invoice = Invoice.query.filter_by(public_link=public_link).first_or_404()

    # Track the view
    now = datetime.utcnow()
    is_first_view = invoice.first_viewed_at is None

    invoice.view_count += 1
    invoice.last_viewed_at = now
    if is_first_view:
        invoice.first_viewed_at = now

    # Record detailed view info
    view = InvoiceView(
        invoice_id=invoice.id,
        viewed_at=now,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500] if request.user_agent.string else None
    )
    db.session.add(view)

    # Create notification for invoice owner (only on first view or after 1 hour gap)
    last_view = InvoiceView.query.filter_by(invoice_id=invoice.id).order_by(InvoiceView.viewed_at.desc()).first()
    should_notify = is_first_view or (last_view and (now - last_view.viewed_at).total_seconds() > 3600)

    if should_notify:
        notification = Notification(
            user_id=invoice.user_id,
            type='invoice_viewed',
            title=f'Invoice {invoice.invoice_number} was viewed',
            message=f'Your invoice to {invoice.client.name} for {invoice.currency} {invoice.total:.2f} was just viewed.',
            link=f'/invoices/{invoice.id}'
        )
        db.session.add(notification)

    db.session.commit()
    return render_template('invoice_public.html', invoice=invoice)


# =============================================================================
# PDF GENERATION
# =============================================================================

@app.route('/invoices/<int:invoice_id>/pdf')
@login_required
def download_invoice_pdf(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()

    # Render HTML for PDF
    html = render_template('invoice_pdf.html', invoice=invoice)

    # Generate PDF using xhtml2pdf (works on Windows without extra dependencies)
    try:
        from xhtml2pdf import pisa
        from io import BytesIO

        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

        if pisa_status.err:
            flash('PDF generation failed', 'error')
            return redirect(url_for('view_invoice', invoice_id=invoice.id))

        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{invoice.invoice_number}.pdf'
        )
    except Exception as e:
        flash(f'PDF generation failed: {str(e)}. Please ensure WeasyPrint is properly installed.', 'error')
        return redirect(url_for('view_invoice', invoice_id=invoice.id))


# =============================================================================
# SETTINGS
# =============================================================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        data = request.form

        current_user.name = data['name']
        current_user.company_name = data.get('company_name', '')
        current_user.address = data.get('address', '')
        current_user.phone = data.get('phone', '')
        current_user.default_currency = data.get('default_currency', 'USD')
        current_user.default_payment_terms = int(data.get('default_payment_terms', 30))
        current_user.default_notes = data.get('default_notes', '')

        db.session.commit()
        flash('Settings saved successfully', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html')


# =============================================================================
# ESTIMATES / QUOTES
# =============================================================================

def generate_next_estimate_number(user_id):
    """Generate the next auto estimate number for a user"""
    last_estimate = Estimate.query.filter_by(user_id=user_id).order_by(Estimate.id.desc()).first()
    if last_estimate:
        try:
            last_num = int(last_estimate.estimate_number.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    return f"EST-{datetime.utcnow().strftime('%Y%m')}-{new_num:04d}"


@app.route('/estimates')
@login_required
def estimates():
    """List all estimates"""
    status_filter = request.args.get('status', 'all')

    query = Estimate.query.filter_by(user_id=current_user.id)

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    estimates_list = query.order_by(Estimate.created_at.desc()).all()

    # Check for expired estimates
    today = datetime.utcnow().date()
    for est in estimates_list:
        if est.status in ['draft', 'sent'] and est.valid_until < today:
            est.status = 'expired'
    db.session.commit()

    return render_template('estimates.html', estimates=estimates_list, status_filter=status_filter)


@app.route('/estimates/new', methods=['GET', 'POST'])
@login_required
def new_estimate():
    """Create a new estimate"""
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        estimate_number = data.get('estimate_number', '').strip()
        if not estimate_number:
            estimate_number = generate_next_estimate_number(current_user.id)

        estimate = Estimate(
            user_id=current_user.id,
            client_id=int(data['client_id']),
            estimate_number=estimate_number,
            title=data.get('title', ''),
            issue_date=datetime.strptime(data['issue_date'], '%Y-%m-%d').date(),
            valid_until=datetime.strptime(data['valid_until'], '%Y-%m-%d').date(),
            currency=data.get('currency', current_user.default_currency),
            tax_rate=float(data.get('tax_rate', 0)),
            discount_amount=float(data.get('discount_amount', 0)),
            notes=data.get('notes', ''),
            terms=data.get('terms', ''),
            template=data.get('template', 'modern')
        )
        estimate.generate_public_link()

        db.session.add(estimate)
        db.session.flush()

        # Add items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = EstimateItem(
                    estimate_id=estimate.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        estimate.calculate_totals()
        db.session.commit()

        flash('Estimate created successfully', 'success')
        return redirect(url_for('view_estimate', estimate_id=estimate.id))

    today = datetime.utcnow().date()
    valid_until = today + timedelta(days=30)
    next_estimate_number = generate_next_estimate_number(current_user.id)

    return render_template('estimate_form.html',
        estimate=None,
        clients=clients,
        today=today,
        valid_until=valid_until,
        next_estimate_number=next_estimate_number
    )


@app.route('/estimates/<int:estimate_id>')
@login_required
def view_estimate(estimate_id):
    """View estimate details"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()
    return render_template('estimate_view.html', estimate=estimate)


@app.route('/estimates/<int:estimate_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_estimate(estimate_id):
    """Edit an estimate"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        new_estimate_number = data.get('estimate_number', '').strip()
        if new_estimate_number:
            estimate.estimate_number = new_estimate_number

        estimate.client_id = int(data['client_id'])
        estimate.title = data.get('title', '')
        estimate.issue_date = datetime.strptime(data['issue_date'], '%Y-%m-%d').date()
        estimate.valid_until = datetime.strptime(data['valid_until'], '%Y-%m-%d').date()
        estimate.currency = data.get('currency', 'USD')
        estimate.tax_rate = float(data.get('tax_rate', 0))
        estimate.discount_amount = float(data.get('discount_amount', 0))
        estimate.notes = data.get('notes', '')
        estimate.terms = data.get('terms', '')
        estimate.template = data.get('template', 'modern')

        # Remove old items
        EstimateItem.query.filter_by(estimate_id=estimate.id).delete()

        # Add new items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = EstimateItem(
                    estimate_id=estimate.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        estimate.calculate_totals()
        db.session.commit()

        flash('Estimate updated successfully', 'success')
        return redirect(url_for('view_estimate', estimate_id=estimate.id))

    return render_template('estimate_form.html',
        estimate=estimate,
        clients=clients,
        next_estimate_number=estimate.estimate_number
    )


@app.route('/estimates/<int:estimate_id>/delete', methods=['POST'])
@login_required
def delete_estimate(estimate_id):
    """Delete an estimate"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()
    db.session.delete(estimate)
    db.session.commit()
    flash('Estimate deleted', 'success')
    return redirect(url_for('estimates'))


@app.route('/estimates/<int:estimate_id>/status', methods=['POST'])
@login_required
def update_estimate_status(estimate_id):
    """Update estimate status"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()
    new_status = request.form.get('status')

    if new_status in ['draft', 'sent', 'accepted', 'declined', 'expired']:
        estimate.status = new_status
        db.session.commit()
        flash(f'Estimate marked as {new_status}', 'success')

    return redirect(url_for('view_estimate', estimate_id=estimate.id))


@app.route('/estimates/<int:estimate_id>/convert', methods=['POST'])
@login_required
def convert_estimate_to_invoice(estimate_id):
    """Convert an estimate to an invoice"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()

    if estimate.status == 'converted':
        flash('This estimate has already been converted to an invoice', 'warning')
        return redirect(url_for('view_estimate', estimate_id=estimate.id))

    # Generate invoice number
    invoice_number = generate_next_invoice_number(current_user.id)

    # Create invoice from estimate
    today = datetime.utcnow().date()
    invoice = Invoice(
        user_id=current_user.id,
        client_id=estimate.client_id,
        invoice_number=invoice_number,
        status='draft',
        issue_date=today,
        due_date=today + timedelta(days=current_user.default_payment_terms),
        currency=estimate.currency,
        tax_rate=estimate.tax_rate,
        discount_amount=estimate.discount_amount,
        notes=f'[Converted from Estimate: {estimate.estimate_number}]\n{estimate.notes}' if estimate.notes else f'[Converted from Estimate: {estimate.estimate_number}]',
        terms=estimate.terms,
        template=estimate.template
    )
    invoice.generate_public_link()

    db.session.add(invoice)
    db.session.flush()

    # Copy items
    for item in estimate.items:
        new_item = InvoiceItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.total
        )
        db.session.add(new_item)

    invoice.calculate_totals()

    # Update estimate
    estimate.status = 'converted'
    estimate.converted_invoice_id = invoice.id

    db.session.commit()

    flash(f'Estimate converted to Invoice {invoice.invoice_number}', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


@app.route('/estimates/<int:estimate_id>/duplicate', methods=['POST'])
@login_required
def duplicate_estimate(estimate_id):
    """Duplicate an estimate"""
    original = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()

    estimate_number = generate_next_estimate_number(current_user.id)

    new_estimate = Estimate(
        user_id=current_user.id,
        client_id=original.client_id,
        estimate_number=estimate_number,
        title=original.title,
        status='draft',
        issue_date=datetime.utcnow().date(),
        valid_until=datetime.utcnow().date() + timedelta(days=30),
        currency=original.currency,
        tax_rate=original.tax_rate,
        discount_amount=original.discount_amount,
        notes=original.notes,
        terms=original.terms,
        template=original.template
    )
    new_estimate.generate_public_link()

    db.session.add(new_estimate)
    db.session.flush()

    # Copy items
    for item in original.items:
        new_item = EstimateItem(
            estimate_id=new_estimate.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.total
        )
        db.session.add(new_item)

    new_estimate.calculate_totals()
    db.session.commit()

    flash('Estimate duplicated successfully', 'success')
    return redirect(url_for('edit_estimate', estimate_id=new_estimate.id))


@app.route('/e/<public_link>')
def public_estimate(public_link):
    """Public view of an estimate"""
    estimate = Estimate.query.filter_by(public_link=public_link).first_or_404()
    estimate.view_count += 1
    db.session.commit()
    return render_template('estimate_public.html', estimate=estimate)


@app.route('/estimates/<int:estimate_id>/pdf')
@login_required
def download_estimate_pdf(estimate_id):
    """Download estimate as PDF"""
    estimate = Estimate.query.filter_by(id=estimate_id, user_id=current_user.id).first_or_404()

    html = render_template('estimate_pdf.html', estimate=estimate)

    try:
        from xhtml2pdf import pisa
        from io import BytesIO

        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf_buffer)

        if pisa_status.err:
            flash('PDF generation failed', 'error')
            return redirect(url_for('view_estimate', estimate_id=estimate.id))

        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{estimate.estimate_number}.pdf'
        )
    except Exception as e:
        flash(f'PDF generation failed: {str(e)}', 'error')
        return redirect(url_for('view_estimate', estimate_id=estimate.id))


# =============================================================================
# RECURRING INVOICES
# =============================================================================

@app.route('/recurring')
@login_required
def recurring_invoices():
    """List all recurring invoices"""
    recurring = RecurringInvoice.query.filter_by(user_id=current_user.id).order_by(
        RecurringInvoice.next_invoice_date
    ).all()
    return render_template('recurring_invoices.html', recurring_invoices=recurring)


@app.route('/recurring/new', methods=['GET', 'POST'])
@login_required
def new_recurring_invoice():
    """Create a new recurring invoice"""
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        recurring = RecurringInvoice(
            user_id=current_user.id,
            client_id=int(data['client_id']),
            name=data['name'],
            frequency=data['frequency'],
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            next_invoice_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None,
            currency=data.get('currency', current_user.default_currency),
            tax_rate=float(data.get('tax_rate', 0)),
            discount_amount=float(data.get('discount_amount', 0)),
            notes=data.get('notes', ''),
            terms=data.get('terms', ''),
            payment_terms_days=int(data.get('payment_terms_days', current_user.default_payment_terms)),
            template=data.get('template', 'modern')
        )

        db.session.add(recurring)
        db.session.flush()

        # Add items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = RecurringInvoiceItem(
                    recurring_invoice_id=recurring.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        db.session.commit()
        flash('Recurring invoice created successfully', 'success')
        return redirect(url_for('recurring_invoices'))

    today = datetime.utcnow().date()
    return render_template('recurring_form.html',
        recurring=None,
        clients=clients,
        today=today
    )


@app.route('/recurring/<int:recurring_id>')
@login_required
def view_recurring_invoice(recurring_id):
    """View recurring invoice details"""
    recurring = RecurringInvoice.query.filter_by(id=recurring_id, user_id=current_user.id).first_or_404()
    # Get invoices generated from this recurring template
    generated_invoices = Invoice.query.filter_by(
        user_id=current_user.id,
        client_id=recurring.client_id
    ).filter(
        Invoice.notes.contains(f'[Recurring: {recurring.name}]')
    ).order_by(Invoice.created_at.desc()).limit(10).all()

    return render_template('recurring_view.html', recurring=recurring, generated_invoices=generated_invoices)


@app.route('/recurring/<int:recurring_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_recurring_invoice(recurring_id):
    """Edit a recurring invoice"""
    recurring = RecurringInvoice.query.filter_by(id=recurring_id, user_id=current_user.id).first_or_404()
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all()

    if request.method == 'POST':
        data = request.form

        recurring.client_id = int(data['client_id'])
        recurring.name = data['name']
        recurring.frequency = data['frequency']
        recurring.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        recurring.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else None
        recurring.currency = data.get('currency', 'USD')
        recurring.tax_rate = float(data.get('tax_rate', 0))
        recurring.discount_amount = float(data.get('discount_amount', 0))
        recurring.notes = data.get('notes', '')
        recurring.terms = data.get('terms', '')
        recurring.payment_terms_days = int(data.get('payment_terms_days', 30))
        recurring.template = data.get('template', 'modern')

        # Remove old items
        RecurringInvoiceItem.query.filter_by(recurring_invoice_id=recurring.id).delete()

        # Add new items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        unit_prices = request.form.getlist('item_unit_price[]')

        for i, desc in enumerate(descriptions):
            if desc.strip():
                item = RecurringInvoiceItem(
                    recurring_invoice_id=recurring.id,
                    description=desc,
                    quantity=float(quantities[i]) if quantities[i] else 1,
                    unit_price=float(unit_prices[i]) if unit_prices[i] else 0
                )
                item.calculate_total()
                db.session.add(item)

        db.session.commit()
        flash('Recurring invoice updated successfully', 'success')
        return redirect(url_for('view_recurring_invoice', recurring_id=recurring.id))

    return render_template('recurring_form.html',
        recurring=recurring,
        clients=clients,
        today=datetime.utcnow().date()
    )


@app.route('/recurring/<int:recurring_id>/delete', methods=['POST'])
@login_required
def delete_recurring_invoice(recurring_id):
    """Delete a recurring invoice"""
    recurring = RecurringInvoice.query.filter_by(id=recurring_id, user_id=current_user.id).first_or_404()
    db.session.delete(recurring)
    db.session.commit()
    flash('Recurring invoice deleted', 'success')
    return redirect(url_for('recurring_invoices'))


@app.route('/recurring/<int:recurring_id>/toggle', methods=['POST'])
@login_required
def toggle_recurring_invoice(recurring_id):
    """Pause or resume a recurring invoice"""
    recurring = RecurringInvoice.query.filter_by(id=recurring_id, user_id=current_user.id).first_or_404()

    if recurring.status == 'active':
        recurring.status = 'paused'
        flash('Recurring invoice paused', 'success')
    else:
        recurring.status = 'active'
        flash('Recurring invoice resumed', 'success')

    db.session.commit()
    return redirect(url_for('view_recurring_invoice', recurring_id=recurring.id))


@app.route('/recurring/<int:recurring_id>/generate', methods=['POST'])
@login_required
def generate_invoice_from_recurring(recurring_id):
    """Manually generate an invoice from recurring template"""
    recurring = RecurringInvoice.query.filter_by(id=recurring_id, user_id=current_user.id).first_or_404()

    # Generate invoice number
    invoice_number = generate_next_invoice_number(current_user.id)

    # Create the invoice
    today = datetime.utcnow().date()
    invoice = Invoice(
        user_id=current_user.id,
        client_id=recurring.client_id,
        invoice_number=invoice_number,
        status='draft',
        issue_date=today,
        due_date=today + timedelta(days=recurring.payment_terms_days),
        currency=recurring.currency,
        tax_rate=recurring.tax_rate,
        discount_amount=recurring.discount_amount,
        notes=f'[Recurring: {recurring.name}]\n{recurring.notes}' if recurring.notes else f'[Recurring: {recurring.name}]',
        terms=recurring.terms,
        template=recurring.template
    )
    invoice.generate_public_link()

    db.session.add(invoice)
    db.session.flush()

    # Copy items
    for item in recurring.items:
        new_item = InvoiceItem(
            invoice_id=invoice.id,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total=item.total
        )
        db.session.add(new_item)

    invoice.calculate_totals()

    # Update recurring invoice
    recurring.last_generated = today
    recurring.next_invoice_date = recurring.calculate_next_date(today)

    db.session.commit()

    flash(f'Invoice {invoice.invoice_number} generated successfully', 'success')
    return redirect(url_for('view_invoice', invoice_id=invoice.id))


def process_recurring_invoices():
    """Process all due recurring invoices - called on dashboard load"""
    today = datetime.utcnow().date()

    due_recurring = RecurringInvoice.query.filter(
        RecurringInvoice.status == 'active',
        RecurringInvoice.next_invoice_date <= today,
        db.or_(
            RecurringInvoice.end_date == None,
            RecurringInvoice.end_date >= today
        )
    ).all()

    generated_count = 0
    for recurring in due_recurring:
        # Generate invoice
        invoice_number = generate_next_invoice_number(recurring.user_id)

        invoice = Invoice(
            user_id=recurring.user_id,
            client_id=recurring.client_id,
            invoice_number=invoice_number,
            status='draft',
            issue_date=today,
            due_date=today + timedelta(days=recurring.payment_terms_days),
            currency=recurring.currency,
            tax_rate=recurring.tax_rate,
            discount_amount=recurring.discount_amount,
            notes=f'[Recurring: {recurring.name}]\n{recurring.notes}' if recurring.notes else f'[Recurring: {recurring.name}]',
            terms=recurring.terms,
            template=recurring.template
        )
        invoice.generate_public_link()

        db.session.add(invoice)
        db.session.flush()

        # Copy items
        for item in recurring.items:
            new_item = InvoiceItem(
                invoice_id=invoice.id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=item.total
            )
            db.session.add(new_item)

        invoice.calculate_totals()

        # Update recurring
        recurring.last_generated = today
        recurring.next_invoice_date = recurring.calculate_next_date(today)

        generated_count += 1

    if generated_count > 0:
        db.session.commit()

    return generated_count


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route('/api/clients/search')
@login_required
def api_search_clients():
    query = request.args.get('q', '')
    clients = Client.query.filter(
        Client.user_id == current_user.id,
        Client.name.ilike(f'%{query}%')
    ).limit(10).all()

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'email': c.email,
        'company_name': c.company_name
    } for c in clients])


@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    # Monthly revenue for the last 6 months
    months = []
    for i in range(5, -1, -1):
        date = datetime.utcnow() - relativedelta(months=i)
        month_start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if i == 0:
            month_end = datetime.utcnow()
        else:
            month_end = (month_start + relativedelta(months=1))

        paid_amount = db.session.query(db.func.sum(Invoice.total)).filter(
            Invoice.user_id == current_user.id,
            Invoice.status == 'paid',
            Invoice.paid_date >= month_start.date(),
            Invoice.paid_date < month_end.date()
        ).scalar() or 0

        months.append({
            'month': date.strftime('%b'),
            'amount': round(paid_amount, 2)
        })

    return jsonify(months)


@app.route('/api/notifications')
@login_required
def api_get_notifications():
    """Get user notifications"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(20).all()

    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

    return jsonify({
        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'type': n.type,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat()
        } for n in notifications]
    })


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def api_mark_notification_read(notification_id):
    """Mark a notification as read"""
    notification = Notification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def api_mark_all_notifications_read():
    """Mark all notifications as read"""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@app.route('/notifications')
@login_required
def notifications_page():
    """View all notifications"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()

    # Mark all as read when viewing the page
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()

    return render_template('notifications.html', notifications=notifications)


# =============================================================================
# REPORTS & ANALYTICS
# =============================================================================

@app.route('/reports')
@login_required
def reports():
    """Reports and analytics dashboard"""
    # Date ranges
    today = datetime.utcnow().date()
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - relativedelta(months=1))
    last_month_end = this_month_start - timedelta(days=1)
    this_year_start = today.replace(month=1, day=1)

    # Revenue stats
    total_revenue = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'paid'
    ).scalar() or 0

    this_month_revenue = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'paid',
        Invoice.paid_date >= this_month_start
    ).scalar() or 0

    last_month_revenue = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'paid',
        Invoice.paid_date >= last_month_start,
        Invoice.paid_date <= last_month_end
    ).scalar() or 0

    this_year_revenue = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'paid',
        Invoice.paid_date >= this_year_start
    ).scalar() or 0

    # Outstanding amount
    outstanding_amount = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status.in_(['sent', 'overdue'])
    ).scalar() or 0

    overdue_amount = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'overdue'
    ).scalar() or 0

    # Invoice counts
    total_invoices = Invoice.query.filter_by(user_id=current_user.id).count()
    paid_invoices = Invoice.query.filter_by(user_id=current_user.id, status='paid').count()
    pending_invoices = Invoice.query.filter(
        Invoice.user_id == current_user.id,
        Invoice.status.in_(['sent', 'overdue'])
    ).count()

    # Top clients by revenue
    top_clients = db.session.query(
        Client.name,
        db.func.sum(Invoice.total).label('total_revenue'),
        db.func.count(Invoice.id).label('invoice_count')
    ).join(Invoice).filter(
        Invoice.user_id == current_user.id,
        Invoice.status == 'paid'
    ).group_by(Client.id).order_by(db.desc('total_revenue')).limit(5).all()

    # Monthly revenue for chart (last 12 months)
    monthly_data = []
    for i in range(11, -1, -1):
        date = datetime.utcnow() - relativedelta(months=i)
        month_start = date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_start + relativedelta(months=1))

        revenue = db.session.query(db.func.sum(Invoice.total)).filter(
            Invoice.user_id == current_user.id,
            Invoice.status == 'paid',
            Invoice.paid_date >= month_start.date(),
            Invoice.paid_date < month_end.date()
        ).scalar() or 0

        invoiced = db.session.query(db.func.sum(Invoice.total)).filter(
            Invoice.user_id == current_user.id,
            Invoice.issue_date >= month_start.date(),
            Invoice.issue_date < month_end.date()
        ).scalar() or 0

        monthly_data.append({
            'month': date.strftime('%b %Y'),
            'revenue': round(revenue, 2),
            'invoiced': round(invoiced, 2)
        })

    # Recent activity
    recent_paid = Invoice.query.filter_by(
        user_id=current_user.id,
        status='paid'
    ).order_by(Invoice.paid_date.desc()).limit(5).all()

    return render_template('reports.html',
        total_revenue=total_revenue,
        this_month_revenue=this_month_revenue,
        last_month_revenue=last_month_revenue,
        this_year_revenue=this_year_revenue,
        outstanding_amount=outstanding_amount,
        overdue_amount=overdue_amount,
        total_invoices=total_invoices,
        paid_invoices=paid_invoices,
        pending_invoices=pending_invoices,
        top_clients=top_clients,
        monthly_data=monthly_data,
        recent_paid=recent_paid
    )


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# =============================================================================
# INITIALIZE DATABASE
# =============================================================================

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()

# Initialize on first request
@app.before_request
def before_request():
    if not hasattr(app, '_db_initialized'):
        init_db()
        app._db_initialized = True


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
