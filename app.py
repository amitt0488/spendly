import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, abort, session
from database.db import get_db, init_db, seed_db, get_user_by_email, create_user
from database.queries import get_user_by_id, get_summary_stats, get_recent_transactions, get_category_breakdown
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

with app.app_context():
    init_db()
    seed_db()


def _month_offset(ref_date, months):
    """Return the first day of the month `months` before ref_date's month."""
    month = ref_date.month - months
    year = ref_date.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return date(year, month, 1)


def _parse_date_filter(raw_from, raw_to, preset):
    """Validate date filter query params; return (df_str, dt_str, raw_from, raw_to, active_preset, error)."""
    filter_error = None
    date_from = None
    date_to = None

    try:
        if raw_from:
            date_from = datetime.strptime(raw_from, "%Y-%m-%d").date()
    except ValueError:
        date_from = None
        raw_from = ""

    try:
        if raw_to:
            date_to = datetime.strptime(raw_to, "%Y-%m-%d").date()
    except ValueError:
        date_to = None
        raw_to = ""

    if date_from and date_to and date_from > date_to:
        filter_error = "Start date must be before end date."
        date_from = date_to = None
        raw_from = raw_to = ""

    df_str = date_from.isoformat() if date_from else None
    dt_str = date_to.isoformat() if date_to else None
    active_preset = preset or ("custom" if (df_str or dt_str) else "all")

    return df_str, dt_str, raw_from, raw_to, active_preset, filter_error


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

    user = get_user_by_id(session["user_id"])
    if user is None:
        abort(404)

    df_str, dt_str, raw_from, raw_to, active_preset, filter_error = _parse_date_filter(
        request.args.get("date_from", ""),
        request.args.get("date_to", ""),
        request.args.get("preset", ""),
    )

    today = date.today()
    first_of_month = today.replace(day=1)
    preset_urls = {
        "this_month": url_for("profile", preset="this_month",
                              date_from=first_of_month.isoformat(),
                              date_to=today.isoformat()),
        "last_3_months": url_for("profile", preset="last_3_months",
                                 date_from=_month_offset(today, 3).isoformat(),
                                 date_to=today.isoformat()),
        "last_6_months": url_for("profile", preset="last_6_months",
                                 date_from=_month_offset(today, 6).isoformat(),
                                 date_to=today.isoformat()),
        "all": url_for("profile"),
    }

    stats = get_summary_stats(session["user_id"], df_str, dt_str)
    transactions = get_recent_transactions(session["user_id"], date_from=df_str, date_to=dt_str)
    categories = get_category_breakdown(session["user_id"], df_str, dt_str)

    return render_template(
        "profile.html",
        user=user, stats=stats, transactions=transactions, categories=categories,
        date_from=raw_from, date_to=raw_to,
        active_preset=active_preset,
        preset_urls=preset_urls,
        filter_error=filter_error,
    )


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
