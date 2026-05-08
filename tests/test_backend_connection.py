import pytest
import sqlite3
import os
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import get_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    import database.db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))

    import database.queries as q_module
    monkeypatch.setattr(q_module, "get_db", db_module.get_db)

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"

    with flask_app.app_context():
        db_module.init_db()

    yield flask_app


@pytest.fixture
def db(app, monkeypatch):
    import database.db as db_module
    return db_module.get_db()


@pytest.fixture
def user_with_expenses(app, monkeypatch):
    import database.db as db_module
    conn = db_module.get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )
    user_id = cursor.lastrowid
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 450.00,  "Food",          "2026-05-01", "Lunch at café"),
            (user_id, 120.00,  "Transport",     "2026-05-02", "Uber ride"),
            (user_id, 1500.00, "Bills",         "2026-05-03", "Electricity bill"),
            (user_id, 800.00,  "Health",        "2026-05-05", "Pharmacy"),
            (user_id, 350.00,  "Entertainment", "2026-05-07", "Movie tickets"),
            (user_id, 2200.00, "Shopping",      "2026-05-08", "Groceries"),
            (user_id, 600.00,  "Other",         "2026-05-10", "Miscellaneous"),
            (user_id, 320.00,  "Food",          "2026-05-12", "Dinner"),
        ],
    )
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture
def user_no_expenses(app):
    import database.db as db_module
    conn = db_module.get_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@spendly.com", generate_password_hash("pass1234")),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Unit tests — get_user_by_id
# ---------------------------------------------------------------------------

def test_get_user_by_id_valid(user_with_expenses):
    user = get_user_by_id(user_with_expenses)
    assert user is not None
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["initials"] == "DU"
    assert "member_since" in user


def test_get_user_by_id_nonexistent():
    result = get_user_by_id(99999)
    assert result is None


# ---------------------------------------------------------------------------
# Unit tests — get_summary_stats
# ---------------------------------------------------------------------------

def test_get_summary_stats_with_expenses(user_with_expenses):
    stats = get_summary_stats(user_with_expenses)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"
    total = float(stats["total_spent"].replace(",", ""))
    assert abs(total - 6340.00) < 0.01


def test_get_summary_stats_no_expenses(user_no_expenses):
    stats = get_summary_stats(user_no_expenses)
    assert stats["total_spent"] == "0.00"
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"


# ---------------------------------------------------------------------------
# Unit tests — get_recent_transactions
# ---------------------------------------------------------------------------

def test_get_recent_transactions_with_expenses(user_with_expenses):
    txs = get_recent_transactions(user_with_expenses)
    assert len(txs) == 8
    # newest first
    assert txs[0]["date"] == "12 May 2026"
    assert txs[-1]["date"] == "01 May 2026"
    for tx in txs:
        assert "date" in tx
        assert "description" in tx
        assert "category" in tx
        assert "amount" in tx


def test_get_recent_transactions_no_expenses(user_no_expenses):
    assert get_recent_transactions(user_no_expenses) == []


def test_get_recent_transactions_limit(user_with_expenses):
    txs = get_recent_transactions(user_with_expenses, limit=3)
    assert len(txs) == 3


# ---------------------------------------------------------------------------
# Unit tests — get_category_breakdown
# ---------------------------------------------------------------------------

def test_get_category_breakdown_with_expenses(user_with_expenses):
    cats = get_category_breakdown(user_with_expenses)
    assert len(cats) == 7
    names = [c["name"] for c in cats]
    assert "Shopping" in names
    assert "Food" in names
    # ordered by amount desc — Shopping (2200) is highest
    assert cats[0]["name"] == "Shopping"
    # percents are integers and sum to 100
    assert all(isinstance(c["percent"], int) for c in cats)
    assert sum(c["percent"] for c in cats) == 100


def test_get_category_breakdown_no_expenses(user_no_expenses):
    assert get_category_breakdown(user_no_expenses) == []


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_profile_unauthenticated_redirects(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated(client, user_with_expenses):
    with client.session_transaction() as sess:
        sess["user_id"] = user_with_expenses

    response = client.get("/profile")
    assert response.status_code == 200
    html = response.data.decode()

    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "₹" in html
    assert "Shopping" in html
