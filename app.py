import os
from datetime import datetime, date
from functools import wraps
from decimal import Decimal, InvalidOperation

from flask import Flask, request, redirect, url_for, session, flash, render_template_string
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_FOLDER = os.path.join(STATIC_DIR, "uploads")


def ensure_dir(path):
    if os.path.exists(path) and not os.path.isdir(path):
        os.remove(path)
    os.makedirs(path, exist_ok=True)


ensure_dir(STATIC_DIR)
ensure_dir(UPLOAD_FOLDER)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "rufa-gold-change-secret")
raw_db_url = os.environ.get("DATABASE_URL")
if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url or "sqlite:///" + os.path.join(BASE_DIR, "rufa_gold.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "pdf", "doc", "docx"}

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="employee")
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
    specs = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="available")
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PropertyImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, default="")
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    status = db.Column(db.String(30), default="open")
    note = db.Column(db.Text, default="")
    attachment = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)


class Deal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey("property.id"), nullable=False)
    commission_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    company_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    sold_at = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DealShare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey("deal.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    percent = db.Column(db.Numeric(7, 2), nullable=False, default=0)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80), default="other")
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    expense_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def money(value):
    try:
        return f"{Decimal(value or 0):,.0f} ر.س"
    except Exception:
        return "0 ر.س"


def dec(value, default="0"):
    try:
        txt = str(value or default).replace(",", "").strip()
        return Decimal(txt or default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file_obj):
    if not file_obj or not file_obj.filename or not allowed_file(file_obj.filename):
        return None
    ensure_dir(UPLOAD_FOLDER)
    base = secure_filename(file_obj.filename)
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{base}"
    file_obj.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.template_filter("role_name")
def role_name(role):
    return {"admin": "مدير تنفيذي", "employee": "موظف", "field": "ميداني"}.get(role, role)


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user.role != "admin":
            flash("هذه الصفحة للمدير التنفيذي فقط", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper


def init_db():
    db.create_all()
    admin = User.query.filter_by(username="ROFA").first()
    if not admin:
        admin = User(name="ROFA", username="ROFA", role="admin", salary=0, active=True)
        admin.password_hash = generate_password_hash("1122334400")
        db.session.add(admin)
        db.session.commit()


@app.before_request
def before_request():
    init_db()


STYLE = """
<style>
:root{--gold:#d4a72c;--gold2:#f2c94c;--dark:#101820;--dark2:#16212d;--line:#243241;--bg:#f6f7fb;--text:#101828;--muted:#667085;--red:#e5484d;--green:#16a34a;--blue:#2563eb}
*{box-sizing:border-box}body{margin:0;font-family:Tahoma,Arial,sans-serif;background:var(--bg);color:var(--text);direction:rtl}.auth-body{min-height:100vh;background:linear-gradient(135deg,#0d1622,#1c2938);display:flex;align-items:center;justify-content:center;padding:20px}.login-card{width:420px;background:#fff;border-radius:24px;padding:34px;box-shadow:0 25px 70px #0005}.brand{font-size:30px;font-weight:900;color:var(--gold);letter-spacing:1px}.small{color:var(--muted);font-size:13px}.form-control,.form-select,textarea{width:100%;border:1px solid #d0d5dd;border-radius:12px;padding:12px 14px;font-family:inherit;background:#fff}.btn{border:0;border-radius:12px;padding:11px 18px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-block}.btn-gold{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#111}.btn-dark{background:var(--dark);color:#fff}.btn-light{background:#eef2f6;color:#111}.btn-red{background:#ef4444;color:white}.layout{display:grid;grid-template-columns:280px 1fr;min-height:100vh}.sidebar{background:linear-gradient(180deg,#0e1724,#111d2b);color:#fff;padding:22px;position:sticky;top:0;height:100vh;overflow:auto}.side-logo{display:flex;gap:12px;align-items:center;margin-bottom:22px}.logo-mark{width:52px;height:52px;border-radius:16px;background:linear-gradient(135deg,var(--gold),var(--gold2));display:flex;align-items:center;justify-content:center;color:#111;font-weight:900;font-size:26px}.side-title{font-size:24px;font-weight:900;color:var(--gold2)}.side-sub{font-size:13px;color:#cbd5e1}.nav-section{margin:22px 0 8px;color:#94a3b8;font-size:13px;border-top:1px solid #253445;padding-top:16px}.nav a{display:flex;justify-content:space-between;align-items:center;color:#e5e7eb;text-decoration:none;padding:13px 14px;border-radius:12px;margin:4px 0}.nav a:hover,.nav a.active{background:linear-gradient(135deg,var(--gold),var(--gold2));color:#111}.logout{color:#ff6b6b!important}.main{padding:24px}.topbar{height:70px;background:#fff;border-bottom:1px solid #e5e7eb;display:flex;align-items:center;justify-content:space-between;padding:0 24px;margin:-24px -24px 24px -24px}.userbox{display:flex;align-items:center;gap:12px}.avatar{width:42px;height:42px;border-radius:50%;background:#eef2f7;display:flex;align-items:center;justify-content:center}.page-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.page-title h1{margin:0;font-size:28px}.grid{display:grid;gap:18px}.cards{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:#fff;border:1px solid #e5e7eb;border-radius:18px;padding:20px;box-shadow:0 8px 25px #10182810}.stat{display:flex;justify-content:space-between;gap:15px;align-items:center}.stat-icon{width:54px;height:54px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;color:#fff}.green{background:#22c55e}.red{background:#ef4444}.yellow{background:#eab308}.blue{background:#3b82f6}.stat-value{font-size:22px;font-weight:900}.stat-label{color:#475467}.two{grid-template-columns:1.1fr .9fr}.three{grid-template-columns:repeat(3,1fr)}table{width:100%;border-collapse:collapse}th,td{padding:13px;border-bottom:1px solid #edf0f3;text-align:right}th{color:#667085;font-size:13px}.badge{padding:6px 10px;border-radius:999px;font-size:12px;font-weight:800}.ok{background:#dcfce7;color:#166534}.wait{background:#fef3c7;color:#92400e}.sold{background:#fee2e2;color:#991b1b}.flash{padding:12px 15px;border-radius:12px;margin-bottom:15px}.flash.success{background:#dcfce7;color:#166534}.flash.danger{background:#fee2e2;color:#991b1b}.flash.info{background:#dbeafe;color:#1e40af}.form-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.full{grid-column:1/-1}.actions{display:flex;gap:8px;flex-wrap:wrap}.searchbar{display:flex;gap:10px;margin-bottom:15px}.image-thumb{width:60px;height:45px;object-fit:cover;border-radius:8px;border:1px solid #e5e7eb}.dark-note{background:#111827;color:#fff;border-radius:16px;padding:18px}@media(max-width:950px){.layout{grid-template-columns:1fr}.sidebar{position:relative;height:auto}.cards,.two,.three,.form-grid{grid-template-columns:1fr}.topbar{margin:0 0 20px 0}.main{padding:16px}.page-title{display:block}.searchbar{display:block}.searchbar .btn{margin-top:8px;width:100%}}
</style>
"""


def page(content, title="RUFA GOLD ERP"):
    user = current_user()
    if not user:
        return render_template_string(STYLE + content)
    def active(endpoint):
        return "active" if request.endpoint == endpoint else ""
    shell = """
<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title>""" + STYLE + """</head><body>
<div class="layout">
<aside class="sidebar">
<div class="side-logo"><div class="logo-mark">R</div><div><div class="side-title">RUFA GOLD</div><div class="side-sub">ERP</div></div></div>
<nav class="nav">
<a class="{{ active('dashboard') }}" href="{{ url_for('dashboard') }}"><span>لوحة التحكم</span><span>⌂</span></a>
<div class="nav-section">العقارات</div>
<a class="{{ active('properties') }}" href="{{ url_for('properties') }}"><span>إدارة العقارات</span><span>▦</span></a>
{% if user.role == 'admin' %}<a href="{{ url_for('property_new') }}"><span>إضافة عقار</span><span>＋</span></a>{% endif %}
{% if user.role == 'admin' %}
<div class="nav-section">الموظفون والميدانيون</div>
<a class="{{ active('users') }}" href="{{ url_for('users') }}"><span>الموظفون والميدانيون</span><span>👥</span></a>
<div class="nav-section">المهام</div>
<a class="{{ active('tasks') }}" href="{{ url_for('tasks') }}"><span>المهام</span><span>☑</span></a>
<div class="nav-section">المالية</div>
<a class="{{ active('finance') }}" href="{{ url_for('finance') }}"><span>السعي والحسابات</span><span>▥</span></a>
{% else %}
<div class="nav-section">المهام</div>
<a class="{{ active('tasks') }}" href="{{ url_for('tasks') }}"><span>مهامي</span><span>☑</span></a>
{% endif %}
<div class="nav-section">الحساب</div>
<a class="logout" href="{{ url_for('logout') }}"><span>تسجيل خروج</span><span>⇥</span></a>
</nav>
</aside>
<main class="main">
<div class="topbar"><div class="userbox"><div class="avatar">👤</div><div><b>{{ user.name }}</b><div class="small">{{ user.role|role_name }}</div></div></div><div class="small">{{ now }}</div></div>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}{% endif %}{% endwith %}
{{ content|safe }}
</main></div></body></html>
"""
    return render_template_string(shell, content=content, title=title, user=user, now=datetime.now().strftime("%Y-%m-%d %H:%M"), active=active)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username, active=True).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))
        flash("بيانات الدخول غير صحيحة", "danger")
    html = """
<body class="auth-body"><div class="login-card"><div class="brand">RUFA GOLD ERP</div><p class="small">نظام إدارة شركة تسويق عقاري</p>
<form method="post"><label>اسم الموظف</label><input class="form-control" name="username" value="ROFA" required><br><label>كلمة المرور</label><input class="form-control" type="password" name="password" required><br><button class="btn btn-gold" style="width:100%">دخول</button></form></div></body>
"""
    return render_template_string("<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>دخول</title>" + STYLE + "</head>" + html + "</html>")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    props = Property.query.count()
    sold = Property.query.filter_by(status="sold").count()
    tasks_open = Task.query.filter(Task.status != "done").count() if user.role == "admin" else Task.query.filter_by(assigned_to_id=user.id, status="open").count()
    total_commission = db.session.query(db.func.coalesce(db.func.sum(Deal.commission_amount), 0)).scalar()
    total_company = db.session.query(db.func.coalesce(db.func.sum(Deal.company_amount), 0)).scalar()
    total_expenses = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).scalar()
    total_salaries = db.session.query(db.func.coalesce(db.func.sum(User.salary), 0)).scalar()
    net_profit = dec(total_company) - dec(total_expenses) - dec(total_salaries)
    latest = Property.query.order_by(Property.id.desc()).limit(5).all()
    html = """
<div class="page-title"><div><h1>مرحباً بك، {{ user.name }}</h1><div class="small">لوحة التحكم الرئيسية</div></div></div>
<div class="grid cards">
<div class="card stat"><div><div class="stat-label">إجمالي السعي</div><div class="stat-value">{{ total_commission|money }}</div></div><div class="stat-icon blue">💰</div></div>
<div class="card stat"><div><div class="stat-label">نصيب الشركة</div><div class="stat-value">{{ total_company|money }}</div></div><div class="stat-icon yellow">🏢</div></div>
<div class="card stat"><div><div class="stat-label">المصاريف والرواتب</div><div class="stat-value">{{ (total_expenses + total_salaries)|money }}</div></div><div class="stat-icon red">💳</div></div>
<div class="card stat"><div><div class="stat-label">صافي الربح</div><div class="stat-value">{{ net_profit|money }}</div></div><div class="stat-icon green">↗</div></div>
</div>
<br>
<div class="grid two"><div class="card"><h3>إحصائية سريعة</h3><div class="grid three"><div class="dark-note">العقارات<br><b>{{ props }}</b></div><div class="dark-note">المباعة<br><b>{{ sold }}</b></div><div class="dark-note">المهام المفتوحة<br><b>{{ tasks_open }}</b></div></div></div>
<div class="card"><h3>آخر العقارات</h3><table><tr><th>الكود</th><th>المشروع</th><th>الحي</th><th>الحالة</th></tr>{% for p in latest %}<tr><td>{{ p.code }}</td><td>{{ p.project_name }}</td><td>{{ p.district }}</td><td>{{ status_badge(p.status)|safe }}</td></tr>{% endfor %}</table></div></div>
"""
    return page(render_template_string(html, user=user, props=props, sold=sold, tasks_open=tasks_open, total_commission=total_commission, total_company=total_company, total_expenses=total_expenses, total_salaries=total_salaries, net_profit=net_profit, latest=latest, status_badge=status_badge))


def status_badge(status):
    if status == "sold":
        return '<span class="badge sold">مباع</span>'
    if status == "reserved":
        return '<span class="badge wait">محجوز</span>'
    return '<span class="badge ok">متاح</span>'


@app.route("/properties")
@login_required
def properties():
    q = request.args.get("q", "").strip()
    query = Property.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Property.project_name.ilike(like), Property.district.ilike(like), Property.property_type.ilike(like), Property.status.ilike(like), Property.code.ilike(like)))
    rows = query.order_by(Property.id.desc()).all()
    images = {img.property_id: img.filename for img in PropertyImage.query.order_by(PropertyImage.id.asc()).all()}
    user = current_user()
    html = """
<div class="page-title"><h1>إدارة العقارات</h1>{% if user.role == 'admin' %}<a class="btn btn-gold" href="{{ url_for('property_new') }}">إضافة عقار</a>{% endif %}</div>
<form class="searchbar"><input class="form-control" name="q" value="{{ q }}" placeholder="بحث بالحي أو اسم المشروع أو النوع أو الحالة"><button class="btn btn-dark">بحث</button></form>
<div class="card"><table><tr><th>صورة</th><th>الكود</th><th>المشروع</th><th>النوع</th><th>الحي</th><th>السعر</th><th>الحالة</th><th>خيارات</th></tr>
{% for p in rows %}<tr><td>{% if images.get(p.id) %}<img class="image-thumb" src="{{ url_for('static', filename='uploads/' + images.get(p.id)) }}">{% else %}-{% endif %}</td><td>{{ p.code }}</td><td>{{ p.project_name }}</td><td>{{ p.property_type }}</td><td>{{ p.district }}</td><td>{{ p.price|money }}</td><td>{{ status_badge(p.status)|safe }}</td><td class="actions">{% if user.role == 'admin' %}<a class="btn btn-light" href="{{ url_for('property_edit', property_id=p.id) }}">تعديل</a><a class="btn btn-gold" href="{{ url_for('property_sell', property_id=p.id) }}">بيع/سعي</a>{% endif %}</td></tr>{% endfor %}</table></div>
"""
    return page(render_template_string(html, rows=rows, images=images, q=q, user=user, status_badge=status_badge))


def next_code():
    last = Property.query.order_by(Property.id.desc()).first()
    num = (last.id + 1) if last else 1
    return f"RG-{num:04d}"


@app.route("/properties/new", methods=["GET", "POST"])
@login_required
@admin_required
def property_new():
    if request.method == "POST":
        p = Property(code=next_code(), project_name=request.form.get("project_name") or "عقار جديد", property_type=request.form.get("property_type") or "غير محدد", district=request.form.get("district") or "غير محدد", price=dec(request.form.get("price")), specs=request.form.get("specs", ""), status=request.form.get("status", "available"), created_by_id=session.get("user_id"))
        db.session.add(p); db.session.commit()
        for f in request.files.getlist("images"):
            filename = save_upload(f)
            if filename:
                db.session.add(PropertyImage(property_id=p.id, filename=filename))
        db.session.commit(); flash("تم حفظ العقار تلقائياً", "success")
        return redirect(url_for("properties"))
    return property_form()


@app.route("/properties/<int:property_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def property_edit(property_id):
    p = db.session.get(Property, property_id)
    if not p:
        flash("العقار غير موجود", "danger"); return redirect(url_for("properties"))
    if request.method == "POST":
        p.project_name = request.form.get("project_name") or p.project_name
        p.property_type = request.form.get("property_type") or p.property_type
        p.district = request.form.get("district") or p.district
        p.price = dec(request.form.get("price"))
        p.specs = request.form.get("specs", "")
        p.status = request.form.get("status", "available")
        for f in request.files.getlist("images"):
            filename = save_upload(f)
            if filename:
                db.session.add(PropertyImage(property_id=p.id, filename=filename))
        db.session.commit(); flash("تم تحديث العقار", "success")
        return redirect(url_for("properties"))
    return property_form(p)


def property_form(p=None):
    html = """
<div class="page-title"><h1>{{ 'تعديل عقار' if p else 'إضافة عقار' }}</h1></div>
<div class="card"><form method="post" enctype="multipart/form-data" class="form-grid"><div><label>اسم المشروع</label><input class="form-control" name="project_name" value="{{ p.project_name if p else '' }}" required></div><div><label>نوع العقار</label><input class="form-control" name="property_type" value="{{ p.property_type if p else '' }}" placeholder="فيلا، دور، شقة، أرض"></div><div><label>الحي</label><input class="form-control" name="district" value="{{ p.district if p else '' }}"></div><div><label>السعر</label><input class="form-control" name="price" value="{{ p.price if p else '' }}"></div><div><label>الحالة</label><select class="form-select" name="status"><option value="available">متاح</option><option value="reserved">محجوز</option><option value="sold">مباع</option></select></div><div><label>الصور</label><input class="form-control" type="file" name="images" multiple></div><div class="full"><label>المواصفات</label><textarea class="form-control" name="specs" rows="6">{{ p.specs if p else '' }}</textarea></div><div class="full"><button class="btn btn-gold">حفظ</button><a class="btn btn-light" href="{{ url_for('properties') }}">رجوع</a></div></form></div>
"""
    return page(render_template_string(html, p=p))


@app.route("/properties/<int:property_id>/sell", methods=["GET", "POST"])
@login_required
@admin_required
def property_sell(property_id):
    p = db.session.get(Property, property_id)
    if not p:
        flash("العقار غير موجود", "danger"); return redirect(url_for("properties"))
    staff = User.query.filter(User.role.in_(["employee", "field"]), User.active == True).all()
    if request.method == "POST":
        commission = dec(request.form.get("commission_amount"))
        deal = Deal(property_id=p.id, commission_amount=commission, company_amount=commission, sold_at=date.today())
        p.status = "sold"
        db.session.add(deal); db.session.commit()
        total_percent = Decimal("0")
        for u in staff:
            percent = dec(request.form.get(f"percent_{u.id}"))
            if percent > 0:
                amount = (commission * percent / Decimal("100")).quantize(Decimal("0.01"))
                db.session.add(DealShare(deal_id=deal.id, user_id=u.id, percent=percent, amount=amount))
                total_percent += percent
        company_amount = commission - (commission * total_percent / Decimal("100"))
        deal.company_amount = company_amount
        db.session.commit(); flash("تم تسجيل السعي وتوزيعه", "success")
        return redirect(url_for("finance"))
    html = """
<div class="page-title"><h1>بيع العقار وتوزيع السعي</h1></div><div class="card"><h3>{{ p.project_name }} - {{ p.code }}</h3><form method="post"><label>قيمة السعي الفعلية</label><input class="form-control" name="commission_amount" placeholder="مثال: 50000" required><br><h3>توزيع السعي</h3><p class="small">ضع النسبة فقط لمن شارك في الصفقة. الباقي يحسب للشركة تلقائياً.</p><table><tr><th>الاسم</th><th>الدور</th><th>النسبة %</th></tr>{% for u in staff %}<tr><td>{{ u.name }}</td><td>{{ u.role|role_name }}</td><td><input class="form-control" name="percent_{{ u.id }}" placeholder="0"></td></tr>{% endfor %}</table><br><button class="btn btn-gold">حفظ الصفقة</button></form></div>
"""
    return page(render_template_string(html, p=p, staff=staff))


@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if User.query.filter_by(username=username).first():
            flash("اسم المستخدم موجود مسبقاً", "danger")
        else:
            u = User(name=request.form.get("name") or username, username=username, role=request.form.get("role", "employee"), salary=dec(request.form.get("salary")))
            u.password_hash = generate_password_hash(request.form.get("password") or "123456")
            db.session.add(u); db.session.commit(); flash("تمت إضافة المستخدم", "success")
    rows = User.query.order_by(User.id.desc()).all()
    html = """
<div class="page-title"><h1>الموظفون والميدانيون</h1></div><div class="grid two"><div class="card"><h3>إضافة مستخدم</h3><form method="post" class="form-grid"><input class="form-control" name="name" placeholder="الاسم"><input class="form-control" name="username" placeholder="اسم المستخدم" required><input class="form-control" name="password" placeholder="كلمة المرور"><select class="form-select" name="role"><option value="employee">موظف</option><option value="field">ميداني</option><option value="admin">مدير تنفيذي</option></select><input class="form-control" name="salary" placeholder="الراتب"><button class="btn btn-gold full">إضافة</button></form></div><div class="card"><h3>القائمة</h3><table><tr><th>الاسم</th><th>المستخدم</th><th>الدور</th><th>الراتب</th></tr>{% for u in rows %}<tr><td>{{ u.name }}</td><td>{{ u.username }}</td><td>{{ u.role|role_name }}</td><td>{{ u.salary|money }}</td></tr>{% endfor %}</table></div></div>
"""
    return page(render_template_string(html, rows=rows))


@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks():
    user = current_user()
    if request.method == "POST" and user.role == "admin":
        t = Task(title=request.form.get("title") or "مهمة", details=request.form.get("details", ""), assigned_to_id=int(request.form.get("assigned_to_id")), created_by_id=user.id)
        db.session.add(t); db.session.commit(); flash("تم إرسال المهمة", "success")
    if request.method == "POST" and request.form.get("complete_task"):
        t = db.session.get(Task, int(request.form.get("complete_task")))
        if t and (user.role == "admin" or t.assigned_to_id == user.id):
            t.note = request.form.get("note", "")
            filename = save_upload(request.files.get("attachment"))
            if filename: t.attachment = filename
            t.status = "done"; t.completed_at = datetime.utcnow(); db.session.commit(); flash("تم تنفيذ المهمة", "success")
    staff = User.query.filter(User.role.in_(["employee", "field"]), User.active == True).all()
    rows = Task.query.order_by(Task.id.desc()).all() if user.role == "admin" else Task.query.filter_by(assigned_to_id=user.id).order_by(Task.id.desc()).all()
    users_map = {u.id: u for u in User.query.all()}
    html = """
<div class="page-title"><h1>{{ 'المهام' if user.role == 'admin' else 'مهامي' }}</h1></div>{% if user.role == 'admin' %}<div class="card"><h3>إنشاء مهمة</h3><form method="post" class="form-grid"><input class="form-control" name="title" placeholder="عنوان المهمة" required><select class="form-select" name="assigned_to_id">{% for u in staff %}<option value="{{ u.id }}">{{ u.name }} - {{ u.role|role_name }}</option>{% endfor %}</select><textarea class="form-control full" name="details" placeholder="التفاصيل"></textarea><button class="btn btn-gold full">إرسال</button></form></div><br>{% endif %}<div class="card"><table><tr><th>المهمة</th><th>المكلف</th><th>الحالة</th><th>تنفيذ</th></tr>{% for t in rows %}<tr><td><b>{{ t.title }}</b><div class="small">{{ t.details }}</div>{% if t.note %}<div class="small">ملاحظة: {{ t.note }}</div>{% endif %}</td><td>{{ users_map.get(t.assigned_to_id).name if users_map.get(t.assigned_to_id) else '-' }}</td><td>{{ 'تم' if t.status == 'done' else 'مفتوحة' }}</td><td>{% if t.status != 'done' %}<form method="post" enctype="multipart/form-data"><input type="hidden" name="complete_task" value="{{ t.id }}"><input class="form-control" name="note" placeholder="ملاحظة"><input class="form-control" type="file" name="attachment"><button class="btn btn-gold">تم التنفيذ</button></form>{% endif %}</td></tr>{% endfor %}</table></div>
"""
    return page(render_template_string(html, user=user, staff=staff, rows=rows, users_map=users_map))


@app.route("/finance", methods=["GET", "POST"])
@login_required
@admin_required
def finance():
    if request.method == "POST":
        e = Expense(title=request.form.get("title") or "مصروف", category=request.form.get("category", "other"), amount=dec(request.form.get("amount")), expense_date=date.today())
        db.session.add(e); db.session.commit(); flash("تم حفظ المصروف", "success")
    deals = Deal.query.order_by(Deal.id.desc()).all()
    expenses = Expense.query.order_by(Expense.id.desc()).limit(20).all()
    total_commission = db.session.query(db.func.coalesce(db.func.sum(Deal.commission_amount), 0)).scalar()
    total_company = db.session.query(db.func.coalesce(db.func.sum(Deal.company_amount), 0)).scalar()
    total_expenses = db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0)).scalar()
    total_salaries = db.session.query(db.func.coalesce(db.func.sum(User.salary), 0)).scalar()
    net = dec(total_company) - dec(total_expenses) - dec(total_salaries)
    html = """
<div class="page-title"><h1>السعي والحسابات</h1></div><div class="grid cards"><div class="card"><div class="stat-label">إجمالي السعي</div><div class="stat-value">{{ total_commission|money }}</div></div><div class="card"><div class="stat-label">نصيب الشركة من السعي</div><div class="stat-value">{{ total_company|money }}</div></div><div class="card"><div class="stat-label">الرواتب والمصاريف</div><div class="stat-value">{{ (total_expenses + total_salaries)|money }}</div></div><div class="card"><div class="stat-label">صافي الشركة</div><div class="stat-value">{{ net|money }}</div></div></div><br><div class="grid two"><div class="card"><h3>إضافة مصروف شهري</h3><form method="post" class="form-grid"><input class="form-control" name="title" placeholder="اسم المصروف"><select class="form-select" name="category"><option value="ads">إعلانات</option><option value="photo">تصوير</option><option value="office">تشغيل</option><option value="other">أخرى</option></select><input class="form-control full" name="amount" placeholder="المبلغ"><button class="btn btn-gold full">حفظ</button></form></div><div class="card"><h3>آخر المصروفات</h3><table><tr><th>البند</th><th>المبلغ</th></tr>{% for e in expenses %}<tr><td>{{ e.title }}</td><td>{{ e.amount|money }}</td></tr>{% endfor %}</table></div></div><br><div class="card"><h3>الصفقات</h3><table><tr><th>رقم</th><th>إجمالي السعي</th><th>للشركة</th><th>التاريخ</th></tr>{% for d in deals %}<tr><td>{{ d.id }}</td><td>{{ d.commission_amount|money }}</td><td>{{ d.company_amount|money }}</td><td>{{ d.sold_at }}</td></tr>{% endfor %}</table></div>
"""
    return page(render_template_string(html, deals=deals, expenses=expenses, total_commission=total_commission, total_company=total_company, total_expenses=total_expenses, total_salaries=total_salaries, net=net))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
