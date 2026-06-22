import os
from datetime import datetime, date
from functools import wraps
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
UPLOAD_FOLDER = os.path.join(STATIC_FOLDER, 'uploads')

# Render may fail if a previous upload created a file named static or uploads.
# This block guarantees both paths are valid directories before Flask starts.
for path in (STATIC_FOLDER, UPLOAD_FOLDER):
    if os.path.isfile(path):
        os.remove(path)
    os.makedirs(path, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key')
raw_db_url = os.environ.get('DATABASE_URL')
if raw_db_url and raw_db_url.startswith('postgres://'):
    raw_db_url = raw_db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url or 'sqlite:///' + os.path.join(BASE_DIR, 'rufa_gold.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default='employee')
    salary = db.Column(db.Numeric(12, 2), default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, index=True)
    project_name = db.Column(db.String(200), nullable=False)
    property_type = db.Column(db.String(80), nullable=False)
    district = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(14, 2), default=0)
    specs = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='available')
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship('PropertyImage', backref='property', cascade='all, delete-orphan', lazy=True)
    creator = db.relationship('User', foreign_keys=[created_by_id], backref='created_properties')

class PropertyImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, default='')
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(30), default='open')
    note = db.Column(db.Text, default='')
    attachment = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

class Deal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    commission_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    company_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    sold_at = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    property = db.relationship('Property', backref='deals')

class DealShare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey('deal.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    percent = db.Column(db.Numeric(7, 2), nullable=False, default=0)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    user = db.relationship('User', backref='deal_shares')

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), default='general')
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    expense_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SalaryPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    pay_date = db.Column(db.Date, default=date.today)
    note = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='salary_payments')


def money(value):
    try:
        return f"{float(value):,.2f} ريال"
    except Exception:
        return "0.00 ريال"

app.jinja_env.filters['money'] = money


def role_label(role):
    return {'manager': 'مدير تنفيذي', 'employee': 'موظف', 'field': 'ميداني'}.get(role, role)


def status_label(status):
    return {'available': 'متاح', 'reserved': 'محجوز', 'sold': 'مباع', 'open': 'مفتوحة', 'done': 'مكتملة'}.get(status, status)

app.jinja_env.filters['role_label'] = role_label
app.jinja_env.filters['status_label'] = status_label


def current_user():
    uid = session.get('user_id')
    return User.query.get(uid) if uid else None

@app.context_processor
def inject_user():
    return {'current_user': current_user()}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def manager_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user.role != 'manager':
            flash('هذه الصفحة للمدير التنفيذي فقط.', 'danger')
            return redirect(url_for('dashboard'))
        return fn(*args, **kwargs)
    return wrapper


def decimal_value(value):
    try:
        return Decimal(str(value or '0').replace(',', ''))
    except Exception:
        return Decimal('0')


def next_property_code():
    last_id = db.session.query(db.func.max(Property.id)).scalar() or 0
    return f"RG-{last_id + 1:04d}"


def save_files(files, prop_id=None, task_prefix='file'):
    saved = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = secure_filename(file.filename)
        stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        final_name = f"{task_prefix}_{stamp}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], final_name))
        saved.append(final_name)
    return saved

@app.before_request
def setup_database():
    if getattr(app, '_db_ready', False):
        return
    db.create_all()
    admin = User.query.filter_by(username='ROFA').first()
    if not admin:
        admin = User(
            name='المدير التنفيذي',
            username='ROFA',
            password_hash=generate_password_hash('1122334400'),
            role='manager',
            salary=0,
            active=True,
        )
        db.session.add(admin)
        db.session.commit()
    app._db_ready = True

@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username, active=True).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('dashboard'))
        flash('بيانات الدخول غير صحيحة.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    q_props = Property.query
    props_count = q_props.count()
    sold_count = Property.query.filter_by(status='sold').count()
    open_tasks = Task.query.filter_by(status='open').count() if user.role == 'manager' else Task.query.filter_by(assigned_to_id=user.id, status='open').count()
    company_income = db.session.query(db.func.coalesce(db.func.sum(Deal.company_amount), 0)).scalar()
    expenses = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).scalar()
    salaries = db.session.query(db.func.coalesce(db.func.sum(SalaryPayment.amount), 0)).scalar()
    net = decimal_value(company_income) - decimal_value(expenses) - decimal_value(salaries)
    recent_props = Property.query.order_by(Property.created_at.desc()).limit(5).all()
    return render_template('dashboard.html', props_count=props_count, sold_count=sold_count, open_tasks=open_tasks, company_income=company_income, expenses=expenses, salaries=salaries, net=net, recent_props=recent_props)

@app.route('/properties')
@login_required
def properties():
    query = request.args.get('q', '').strip()
    status = request.args.get('status', '').strip()
    base = Property.query
    if query:
        like = f"%{query}%"
        base = base.filter(db.or_(Property.project_name.ilike(like), Property.district.ilike(like), Property.property_type.ilike(like), Property.code.ilike(like), db.cast(Property.price, db.String).ilike(like)))
    if status:
        base = base.filter_by(status=status)
    items = base.order_by(Property.created_at.desc()).all()
    return render_template('properties.html', items=items, query=query, status=status)

@app.route('/properties/add', methods=['GET', 'POST'])
@login_required
def add_property():
    user = current_user()
    if user.role == 'field':
        flash('الميداني يشاهد العقارات ولا يضيفها.', 'danger')
        return redirect(url_for('properties'))
    if request.method == 'POST':
        prop = Property(
            code=next_property_code(),
            project_name=request.form.get('project_name', '').strip(),
            property_type=request.form.get('property_type', '').strip(),
            district=request.form.get('district', '').strip(),
            price=decimal_value(request.form.get('price')),
            specs=request.form.get('specs', '').strip(),
            status=request.form.get('status', 'available'),
            created_by_id=user.id,
        )
        db.session.add(prop)
        db.session.commit()
        for filename in save_files(request.files.getlist('images'), task_prefix='property'):
            db.session.add(PropertyImage(property_id=prop.id, filename=filename))
        db.session.commit()
        flash('تم حفظ العقار تلقائياً.', 'success')
        return redirect(url_for('properties'))
    return render_template('property_form.html', prop=None)

@app.route('/properties/<int:property_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_property(property_id):
    user = current_user()
    if user.role == 'field':
        flash('الميداني لا يستطيع تعديل العقارات.', 'danger')
        return redirect(url_for('properties'))
    prop = Property.query.get_or_404(property_id)
    if request.method == 'POST':
        prop.project_name = request.form.get('project_name', '').strip()
        prop.property_type = request.form.get('property_type', '').strip()
        prop.district = request.form.get('district', '').strip()
        prop.price = decimal_value(request.form.get('price'))
        prop.specs = request.form.get('specs', '').strip()
        prop.status = request.form.get('status', 'available')
        for filename in save_files(request.files.getlist('images'), task_prefix='property'):
            db.session.add(PropertyImage(property_id=prop.id, filename=filename))
        db.session.commit()
        flash('تم تحديث العقار وحفظه.', 'success')
        return redirect(url_for('properties'))
    return render_template('property_form.html', prop=prop)

@app.route('/properties/<int:property_id>/delete', methods=['POST'])
@login_required
@manager_required
def delete_property(property_id):
    prop = Property.query.get_or_404(property_id)
    PropertyImage.query.filter_by(property_id=prop.id).delete()
    db.session.delete(prop)
    db.session.commit()
    flash('تم حذف العقار.', 'success')
    return redirect(url_for('properties'))

@app.route('/properties/<int:property_id>/sell', methods=['GET', 'POST'])
@login_required
@manager_required
def sell_property(property_id):
    prop = Property.query.get_or_404(property_id)
    users = User.query.filter(User.role.in_(['employee', 'field']), User.active == True).order_by(User.name).all()
    if request.method == 'POST':
        commission_amount = decimal_value(request.form.get('commission_amount'))
        user_ids = request.form.getlist('user_id')
        percents = request.form.getlist('percent')
        total_percent = sum(decimal_value(p) for p in percents if p)
        if total_percent > Decimal('100'):
            flash('مجموع النسب لا يجب أن يتجاوز 100%.', 'danger')
            return redirect(url_for('sell_property', property_id=property_id))
        company_percent = Decimal('100') - total_percent
        company_amount = commission_amount * company_percent / Decimal('100')
        prop.status = 'sold'
        deal = Deal(property_id=prop.id, commission_amount=commission_amount, company_amount=company_amount)
        db.session.add(deal)
        db.session.flush()
        for uid, pct in zip(user_ids, percents):
            pct_dec = decimal_value(pct)
            if uid and pct_dec > 0:
                amount = commission_amount * pct_dec / Decimal('100')
                db.session.add(DealShare(deal_id=deal.id, user_id=int(uid), percent=pct_dec, amount=amount))
        db.session.commit()
        flash('تم تسجيل البيع وتوزيع السعي.', 'success')
        return redirect(url_for('finance'))
    return render_template('sell_property.html', prop=prop, users=users)

@app.route('/users', methods=['GET', 'POST'])
@login_required
@manager_required
def users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً.', 'danger')
        elif not username or not password:
            flash('اسم المستخدم وكلمة المرور مطلوبة.', 'danger')
        else:
            user = User(
                name=request.form.get('name', '').strip(),
                username=username,
                password_hash=generate_password_hash(password),
                role=request.form.get('role', 'employee'),
                salary=decimal_value(request.form.get('salary')),
                active=True,
            )
            db.session.add(user)
            db.session.commit()
            flash('تم إضافة الحساب.', 'success')
        return redirect(url_for('users'))
    items = User.query.order_by(User.created_at.desc()).all()
    return render_template('users.html', items=items)

@app.route('/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    user = current_user()
    if request.method == 'POST':
        if user.role != 'manager':
            flash('إنشاء المهام للمدير فقط.', 'danger')
            return redirect(url_for('tasks'))
        task = Task(
            title=request.form.get('title', '').strip(),
            details=request.form.get('details', '').strip(),
            assigned_to_id=int(request.form.get('assigned_to_id')),
            created_by_id=user.id,
        )
        db.session.add(task)
        db.session.commit()
        flash('تم إرسال المهمة.', 'success')
        return redirect(url_for('tasks'))
    if user.role == 'manager':
        items = Task.query.order_by(Task.created_at.desc()).all()
        assignees = User.query.filter(User.role.in_(['employee', 'field']), User.active == True).all()
    else:
        items = Task.query.filter_by(assigned_to_id=user.id).order_by(Task.created_at.desc()).all()
        assignees = []
    return render_template('tasks.html', items=items, assignees=assignees)

@app.route('/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    user = current_user()
    task = Task.query.get_or_404(task_id)
    if user.role != 'manager' and task.assigned_to_id != user.id:
        flash('لا تملك صلاحية هذه المهمة.', 'danger')
        return redirect(url_for('tasks'))
    task.note = request.form.get('note', '').strip()
    files = save_files(request.files.getlist('attachment'), task_prefix='task')
    if files:
        task.attachment = files[0]
    task.status = 'done'
    task.completed_at = datetime.utcnow()
    db.session.commit()
    flash('تم تنفيذ المهمة وإرسالها للمدير.', 'success')
    return redirect(url_for('tasks'))

@app.route('/finance', methods=['GET', 'POST'])
@login_required
@manager_required
def finance():
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'expense':
            db.session.add(Expense(title=request.form.get('title','').strip(), category=request.form.get('category','general'), amount=decimal_value(request.form.get('amount')), expense_date=date.today()))
        elif form_type == 'salary':
            db.session.add(SalaryPayment(user_id=int(request.form.get('user_id')), amount=decimal_value(request.form.get('amount')), note=request.form.get('note','').strip(), pay_date=date.today()))
        db.session.commit()
        flash('تم الحفظ في الحسابات.', 'success')
        return redirect(url_for('finance'))
    deals = Deal.query.order_by(Deal.created_at.desc()).all()
    shares = DealShare.query.all()
    expenses = Expense.query.order_by(Expense.created_at.desc()).all()
    salary_payments = SalaryPayment.query.order_by(SalaryPayment.created_at.desc()).all()
    users_list = User.query.filter(User.role.in_(['employee','field']), User.active == True).all()
    total_commission = db.session.query(db.func.coalesce(db.func.sum(Deal.commission_amount), 0)).scalar()
    company_income = db.session.query(db.func.coalesce(db.func.sum(Deal.company_amount), 0)).scalar()
    total_expenses = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).scalar()
    total_salaries = db.session.query(db.func.coalesce(db.func.sum(SalaryPayment.amount), 0)).scalar()
    net = decimal_value(company_income) - decimal_value(total_expenses) - decimal_value(total_salaries)
    return render_template('finance.html', deals=deals, shares=shares, expenses=expenses, salary_payments=salary_payments, users_list=users_list, total_commission=total_commission, company_income=company_income, total_expenses=total_expenses, total_salaries=total_salaries, net=net)

if __name__ == '__main__':
    app.run(debug=True)
