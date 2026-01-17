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
from babel.numbers import format_currency
from dateutil.relativedelta import relativedelta

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///invoiceai.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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
    public_link = db.Column(db.String(100), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')

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
    # Get statistics
    total_invoices = Invoice.query.filter_by(user_id=current_user.id).count()
    paid_invoices = Invoice.query.filter_by(user_id=current_user.id, status='paid').count()
    pending_amount = db.session.query(db.func.sum(Invoice.total)).filter(
        Invoice.user_id == current_user.id,
        Invoice.status.in_(['sent', 'overdue'])
    ).scalar() or 0

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
        recent_invoices=recent_invoices
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
    invoice.view_count += 1
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

# Create database tables on startup
with app.app_context():
    db.create_all()


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=5000)
