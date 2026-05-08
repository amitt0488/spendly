import os
from flask import Flask, render_template, request, redirect, url_for, abort, session
from database.db import get_db, init_db, seed_db, get_user_by_email, create_user, get_user_by_id
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name:
        return render_template("register.html", error="Name is required.")
    if len(name) > 100:
        return render_template("register.html", error="Name must be 100 characters or fewer.")

    if not email:
        return render_template("register.html", error="Email address is required.")
    if "@" not in email:
        return render_template("register.html", error="Enter a valid email address.")

    if not password:
        return render_template("register.html", error="Password is required.")
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.")

    if get_user_by_email(email):
        return render_template("register.html", error="An account with that email already exists.")

    create_user(name, email, generate_password_hash(password))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("login.html", error="Email and password are required.")

    user = get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.")

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Nitish Kumar",
        "email": "nitish@example.com",
        "initials": "NK",
        "member_since": "January 2026",
    }
    stats = {
        "total_spent": "24,340",
        "transaction_count": 12,
        "top_category": "Food",
    }
    transactions = [
        {"date": "08 May 2026", "description": "Groceries at DMart",    "category": "Shopping",      "amount": "2,200"},
        {"date": "07 May 2026", "description": "Movie tickets — PVR",    "category": "Entertainment", "amount": "350"},
        {"date": "05 May 2026", "description": "Pharmacy — vitamins",    "category": "Health",        "amount": "800"},
        {"date": "03 May 2026", "description": "Electricity bill",        "category": "Bills",         "amount": "1,500"},
        {"date": "02 May 2026", "description": "Uber to airport",         "category": "Transport",     "amount": "120"},
        {"date": "01 May 2026", "description": "Lunch at café",           "category": "Food",          "amount": "450"},
    ]
    categories = [
        {"name": "Food",          "amount": "7,840", "percent": 72},
        {"name": "Shopping",      "amount": "6,200", "percent": 57},
        {"name": "Bills",         "amount": "4,500", "percent": 41},
        {"name": "Health",        "amount": "3,200", "percent": 29},
        {"name": "Entertainment", "amount": "1,600", "percent": 15},
        {"name": "Transport",     "amount": "1,000", "percent": 9},
    ]
    return render_template("profile.html", user=user, stats=stats,
                           transactions=transactions, categories=categories)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
