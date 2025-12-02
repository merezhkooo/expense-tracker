from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from functools import wraps
import os

from flask_pymongo import PyMongo
from config import MONGO_URI as LOCAL_MONGO_URI, SECRET_KEY as LOCAL_SECRET_KEY

app = Flask(__name__)

# ---------- Налаштування Flask + MongoDB ----------

# Для Render значення прийдуть із середовища, локально — з config.py
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", LOCAL_SECRET_KEY)
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", LOCAL_MONGO_URI)

mongo = PyMongo(app)
db = mongo.db  # db.users, db.expenses



# ----------------- Хелпери -----------------


def current_user():
    """Повертає документ користувача з БД, якщо він залогінений, інакше None."""
    email = session.get("user_email")
    if not email:
        return None
    user = db.users.find_one({"email": email})
    return user


def login_required(f):
    """Декоратор для роутів, які вимагають авторизацію."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_email"):
            flash("Спочатку увійдіть у систему", "warning")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


# ----------------- Маршрути -----------------


@app.route("/")
def index():
    user = current_user()
    if user:
        return redirect(url_for("dashboard"))
    # На головній одразу показуємо форму входу
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            flash("Заповніть усі обов'язкові поля", "danger")
            return render_template("register.html")

        # Перевірка чи користувач уже існує в БД
        existing = db.users.find_one({"email": email})
        if existing:
            flash("Користувач з таким email уже існує", "danger")
            return render_template("register.html")

        # Створюємо нового користувача
        db.users.insert_one({
            "name": name,
            "email": email,
            "password": password,  # поки без хешування
            "created_at": datetime.utcnow()
        })

        # Автоматичний вхід після реєстрації
        session["user_email"] = email
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["POST"])
def login():
    # GET /login більше не потрібен, форма входу на головній сторінці
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    if not email or not password:
        flash("Введіть email та пароль", "danger")
        return redirect(url_for("index"))

    # Пошук користувача в БД
    user = db.users.find_one({"email": email, "password": password})

    if not user:
        flash("Невірний email або пароль", "danger")
        return redirect(url_for("index"))

    session["user_email"] = user["email"]
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.pop("user_email", None)
    return redirect(url_for("index"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    user = current_user()

    # -------- POST: додавання нової витрати --------
    if request.method == "POST":
        amount_str = request.form.get("amount", "").replace(",", ".")
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date_str = request.form.get("date", "").strip()

        if not amount_str or not category or not date_str:
            flash("Сума, категорія та дата є обов'язковими", "danger")
        else:
            try:
                amount = float(amount_str)
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                flash("Невірний формат суми або дати", "danger")
            else:
                db.expenses.insert_one({
                    "user_email": user["email"],
                    "amount": amount,
                    "category": category,
                    "description": description,
                    "date": date_str,          # зберігаємо як 'YYYY-MM-DD'
                    "created_at": datetime.utcnow()
                })
                flash("Витрату додано", "success")

        return redirect(url_for("dashboard"))

    # -------- GET: показ дашборду --------

    # Витрати поточного користувача з БД
    cursor = db.expenses.find({"user_email": user["email"]})
    user_expenses = list(cursor)

    # Сортування за датою (рядок 'YYYY-MM-DD')
    user_expenses.sort(key=lambda e: e.get("date", ""), reverse=True)

    total = sum(e.get("amount", 0) for e in user_expenses) if user_expenses else 0

    # Сума по категоріях
    totals_by_category = {}
    for e in user_expenses:
        cat = e.get("category") or "Інше"
        totals_by_category[cat] = totals_by_category.get(cat, 0) + e.get("amount", 0)

    # Форматована дата для відображення
    for e in user_expenses:
        date_str = e.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            e["date_display"] = dt.strftime("%d.%m.%Y")
        except ValueError:
            e["date_display"] = date_str

    # Дані для діаграми
    category_breakdown = []
    if total > 0:
        for cat, value in totals_by_category.items():
            percent = round(value / total * 100)
            category_breakdown.append({
                "name": cat,
                "value": round(value, 2),
                "percent": percent
            })
    else:
        for cat, value in totals_by_category.items():
            category_breakdown.append({
                "name": cat,
                "value": round(value, 2),
                "percent": 0
            })

    return render_template(
        "dashboard.html",
        user=user,
        expenses=user_expenses,
        total=total,
        totals_by_category=totals_by_category,
        category_breakdown=category_breakdown
    )


if __name__ == "__main__":
    app.run(debug=True)
