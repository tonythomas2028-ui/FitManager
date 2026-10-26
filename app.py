import os
from datetime import date, datetime, timedelta
from functools import wraps
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Development-only fallbacks keep local setup convenient. Production must be configured explicitly.
secret_key = os.getenv("SECRET_KEY")
admin_user = os.getenv("ADMIN_USERNAME")
admin_pass = os.getenv("ADMIN_PASSWORD")
if IS_PRODUCTION:
    missing = [name for name, value in {
        "SECRET_KEY": secret_key,
        "ADMIN_USERNAME": admin_user,
        "ADMIN_PASSWORD": admin_pass,
    }.items() if not value]
    if missing:
        raise RuntimeError("Missing required production environment variable(s): " + ", ".join(missing))
else:
    secret_key = secret_key or "development-only-change-me"
    admin_user = admin_user or "admin"
    admin_pass = admin_pass or "admin-dev-only"

app.config["SECRET_KEY"] = secret_key
app.config["APP_VERSION"] = APP_VERSION

db_url = os.getenv("DATABASE_URL", "sqlite:///fitmanager.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)
ADMIN_USER = admin_user
ADMIN_PASS = admin_pass

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    plan = db.Column(db.String(40), nullable=False, default="Monthly")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    payments = db.relationship("Payment", backref="member", cascade="all, delete-orphan")
    visits = db.relationship("Visit", backref="member", cascade="all, delete-orphan")
    @property
    def status(self):
        return "Active" if self.end_date >= date.today() else "Expired"

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    checked_in = db.Column(db.DateTime, default=datetime.now, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("member.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, default=date.today, nullable=False)
    method = db.Column(db.String(30), default="Cash", nullable=False)
    note = db.Column(db.String(200))

def signed_in(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper

@app.template_filter("money")
def money(value):
    return f"₹{float(value or 0):,.2f}"

@app.context_processor
def globals_for_templates():
    return {"today": date.today()}

@app.route("/health")
def health():
    # Liveness only: deliberately does not depend on the database.
    return {
        "status": "ok",
        "app": "FitManager",
        "version": app.config["APP_VERSION"],
        "instance": os.getenv("HOSTNAME") or __import__("socket").gethostname(),
    }, 200


@app.route("/ready")
def ready():
    # Readiness requires a working database connection, but never returns internal error details.
    try:
        db.session.execute(text("SELECT 1"))
        db.session.rollback()
        return {"status": "ready", "app": "FitManager"}, 200
    except SQLAlchemyError:
        db.session.rollback()
        return {"status": "not_ready", "app": "FitManager"}, 503


@app.cli.command("init-db")
def init_db_command():
    """Create database tables once before starting application replicas."""
    db.create_all()
    print("Database tables created or already present.")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username", "").strip() == ADMIN_USER and request.form.get("password", "") == ADMIN_PASS:
            session["logged_in"] = True
            session["username"] = ADMIN_USER
            flash("Welcome back!", "success")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@signed_in
def dashboard():
    total = Member.query.count()
    active = Member.query.filter(Member.end_date >= date.today()).count()
    visits_today = Visit.query.filter(func.date(Visit.checked_in) == date.today().isoformat()).count()
    revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    recent = Member.query.order_by(Member.created_at.desc()).limit(6).all()
    payments = Payment.query.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(5).all()
    expiring = Member.query.filter(Member.end_date >= date.today(), Member.end_date <= date.today()+timedelta(days=7)).order_by(Member.end_date).limit(5).all()
    return render_template("dashboard.html", total=total, active=active, expired=total-active,
        visits_today=visits_today, revenue=revenue, recent=recent, payments=payments, expiring=expiring)

@app.route("/members")
@signed_in
def members():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    query = Member.query
    if q:
        query = query.filter((Member.name.ilike(f"%{q}%")) | (Member.phone.ilike(f"%{q}%")) | (Member.email.ilike(f"%{q}%")))
    if status == "active": query = query.filter(Member.end_date >= date.today())
    if status == "expired": query = query.filter(Member.end_date < date.today())
    return render_template("members.html", members=query.order_by(Member.created_at.desc()).all(), q=q, status=status)

@app.route("/members/new", methods=["GET", "POST"])
@signed_in
def new_member():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            start = date.fromisoformat(request.form.get("start_date", ""))
            end = date.fromisoformat(request.form.get("end_date", ""))
            if not name or not phone: raise ValueError("Name and phone are required.")
            if end < start: raise ValueError("End date cannot be before start date.")
            m = Member(name=name, phone=phone, email=request.form.get("email", "").strip() or None,
                       plan=request.form.get("plan", "Monthly"), start_date=start, end_date=end)
            db.session.add(m); db.session.commit()
            flash("Member added successfully.", "success")
            return redirect(url_for("members"))
        except (ValueError, TypeError) as e:
            flash(str(e) or "Please enter valid details.", "error")
    return render_template("member_form.html", start_default=date.today().isoformat(),
                           end_default=(date.today()+timedelta(days=30)).isoformat())

@app.route("/members/<int:mid>")
@signed_in
def member_detail(mid):
    m = db.get_or_404(Member, mid)
    return render_template("member_detail.html", m=m,
        visits=Visit.query.filter_by(member_id=mid).order_by(Visit.checked_in.desc()).limit(10).all(),
        payments=Payment.query.filter_by(member_id=mid).order_by(Payment.payment_date.desc()).all())

@app.route("/members/<int:mid>/delete", methods=["POST"])
@signed_in
def delete_member(mid):
    db.session.delete(db.get_or_404(Member, mid)); db.session.commit()
    flash("Member and related records deleted.", "success")
    return redirect(url_for("members"))

@app.route("/attendance", methods=["GET", "POST"])
@signed_in
def attendance():
    if request.method == "POST":
        m = db.session.get(Member, request.form.get("member_id", type=int))
        if not m: flash("Choose a valid member.", "error")
        elif m.status != "Active": flash("Membership expired; check-in blocked.", "error")
        else:
            db.session.add(Visit(member_id=m.id)); db.session.commit()
            flash(f"Check-in recorded for {m.name}.", "success")
        return redirect(url_for("attendance"))
    active = Member.query.filter(Member.end_date >= date.today()).order_by(Member.name).all()
    visits = Visit.query.order_by(Visit.checked_in.desc()).limit(30).all()
    return render_template("attendance.html", active=active, visits=visits)

@app.route("/payments", methods=["GET", "POST"])
@signed_in
def payments_page():
    if request.method == "POST":
        try:
            m = db.session.get(Member, request.form.get("member_id", type=int))
            amount = Decimal(request.form.get("amount", "0"))
            if not m: raise ValueError("Choose a member.")
            if amount <= 0: raise ValueError("Amount must be greater than zero.")
            payment = Payment(member_id=m.id, amount=amount,
                payment_date=date.fromisoformat(request.form.get("payment_date", "")),
                method=request.form.get("method", "Cash"),
                note=request.form.get("note", "").strip() or None)
            db.session.add(payment); db.session.commit()
            flash("Payment recorded.", "success")
            return redirect(url_for("payments_page"))
        except (ValueError, InvalidOperation, TypeError) as e:
            flash(str(e) or "Enter valid payment details.", "error")
    rows = Payment.query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    total = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    return render_template("payments.html", payments=rows, members=Member.query.order_by(Member.name).all(),
                           total=total, default_date=date.today().isoformat())

if __name__ == "__main__":
    # Local development only. Initialize the database separately with `flask --app app init-db`.
    app.run(debug=(APP_ENV != "production"))
