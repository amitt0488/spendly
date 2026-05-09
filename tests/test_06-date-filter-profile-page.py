"""
Tests for Step 6: Date Filter for Profile Page (GET /profile)

Covers the full Definition of Done from
.claude/specs/06-date-filter-profile-page.md plus the additional
requirements stated in the task brief:
  - auth guard
  - malformed date string does not crash
  - date_from > date_to shows error and falls back to unfiltered
  - user with no expenses in range sees 0 total and empty categories
  - ₹ symbol present regardless of filter
  - "All Time" preset link is a clean /profile URL (no query params)
"""

import pytest
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

from app import app as flask_app
import database.db as db_module
import database.queries as q_module
from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _month_offset(ref: date, months: int) -> date:
    """Mirror of app.py _month_offset — first day of month `months` before ref."""
    month = ref.month - months
    year = ref.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return date(year, month, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path, monkeypatch):
    """
    Isolated Flask app backed by a per-test temp SQLite file.
    The DB_PATH monkeypatch ensures no writes reach the real spendly.db.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))
    # Ensure queries.py uses the patched get_db
    monkeypatch.setattr(q_module, "get_db", db_module.get_db)

    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret"

    with flask_app.app_context():
        db_module.init_db()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _insert_user(conn, name="Test User", email="test@spendly.com", password="pass1234"):
    """Insert a user row and return its id."""
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_expenses(conn, user_id, rows):
    """
    rows: list of (amount, category, date_str, description)
    """
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [(user_id, *r) for r in rows],
    )
    conn.commit()


@pytest.fixture
def user_with_expenses(app):
    """
    User with a spread of expenses across multiple months so date-filter
    tests can isolate specific windows.

    Expense dates:
      2026-01-15  Food         500.00
      2026-02-10  Transport    200.00
      2026-03-05  Bills       1000.00
      2026-04-20  Health       750.00
      2026-05-01  Food         450.00
      2026-05-08  Shopping    2200.00
      2026-05-09  Other        100.00   <- "today" in seeded data context
    """
    conn = db_module.get_db()
    user_id = _insert_user(conn)
    _insert_expenses(conn, user_id, [
        (500.00,  "Food",      "2026-01-15", "January lunch"),
        (200.00,  "Transport", "2026-02-10", "February ride"),
        (1000.00, "Bills",     "2026-03-05", "March electricity"),
        (750.00,  "Health",    "2026-04-20", "April pharmacy"),
        (450.00,  "Food",      "2026-05-01", "May lunch"),
        (2200.00, "Shopping",  "2026-05-08", "May groceries"),
        (100.00,  "Other",     "2026-05-09", "May misc"),
    ])
    conn.close()
    return user_id


@pytest.fixture
def user_no_expenses(app):
    """User with absolutely no expense rows."""
    conn = db_module.get_db()
    user_id = _insert_user(conn, name="Empty User", email="empty@spendly.com")
    conn.close()
    return user_id


@pytest.fixture
def auth_client(client, user_with_expenses):
    """Test client pre-authenticated as the user_with_expenses user."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_with_expenses
    return client


@pytest.fixture
def auth_client_no_expenses(client, user_no_expenses):
    """Test client pre-authenticated as the user with no expenses."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_no_expenses
    return client


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Expected redirect for unauthenticated user"
        assert "/login" in response.headers["Location"], (
            "Redirect should point to /login"
        )

    def test_unauthenticated_with_date_params_still_redirects(self, client):
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-12-31")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Baseline: no query params — behaves identically to Step 5 (unfiltered)
# ---------------------------------------------------------------------------

class TestUnfilteredBaseline:
    def test_profile_returns_200(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200

    def test_profile_shows_all_expenses_unfiltered(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        # All 7 expenses should appear in the transaction count stat
        assert "7" in html, "Transaction count should be 7 when unfiltered"

    def test_rupee_symbol_present_unfiltered(self, auth_client):
        response = auth_client.get("/profile")
        assert "₹" in response.data.decode(), (
            "₹ symbol must be present in unfiltered profile page"
        )

    def test_profile_shows_filter_bar(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "This Month" in html, "Filter bar must contain 'This Month' preset"
        assert "Last 3 Months" in html, "Filter bar must contain 'Last 3 Months' preset"
        assert "Last 6 Months" in html, "Filter bar must contain 'Last 6 Months' preset"
        assert "All Time" in html, "Filter bar must contain 'All Time' preset"

    def test_profile_shows_date_inputs(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert 'name="date_from"' in html, "date_from input must be rendered"
        assert 'name="date_to"' in html, "date_to input must be rendered"

    def test_profile_shows_apply_button(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "Apply" in html, "Apply submit button must appear in the filter bar"

    def test_no_filter_error_shown_by_default(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "Start date must be before end date" not in html

    def test_all_time_preset_is_active_by_default(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        # The "All Time" button must carry the active CSS class
        assert "profile-preset-btn--active" in html, (
            "An active preset class must be rendered"
        )
        # Confirm 'All Time' text is near the active class
        import re
        active_block = re.search(
            r'profile-preset-btn--active[^>]*>([^<]+)<', html
        )
        assert active_block is not None, "Active preset anchor must have text"
        assert "All Time" in active_block.group(1), (
            "'All Time' should be the active preset when no filter params given"
        )


# ---------------------------------------------------------------------------
# All Time preset link — must be a clean /profile URL
# ---------------------------------------------------------------------------

class TestAllTimePreset:
    def test_all_time_link_has_no_query_params(self, auth_client):
        """
        The 'All Time' preset anchor href must be /profile with no query string.
        url_for('profile') produces exactly this.
        """
        response = auth_client.get("/profile")
        html = response.data.decode()
        import re
        # Find all hrefs that contain /profile
        hrefs = re.findall(r'href="([^"]*)"', html)
        # The All Time link should exist and equal /profile (no query params)
        profile_clean = [h for h in hrefs if h == "/profile"]
        assert len(profile_clean) >= 1, (
            "At least one link to clean /profile (no query params) must exist — "
            "this is the 'All Time' preset link"
        )

    def test_all_time_link_removes_filter_when_clicked(self, auth_client):
        """
        Following the clean /profile link when a filter is active must show
        all expenses (unfiltered) again.
        """
        # First apply a narrow filter
        filtered = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-09")
        assert filtered.status_code == 200
        # Then visit the clean /profile (All Time)
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "7" in html, "All Time should show all 7 expenses"


# ---------------------------------------------------------------------------
# Custom date range — happy path
# ---------------------------------------------------------------------------

class TestCustomDateRange:
    def test_custom_range_filters_summary_stats(self, auth_client):
        """Only expenses within the range appear in total spent and count."""
        # May 2026 only: 450 + 2200 + 100 = 2750
        response = auth_client.get(
            "/profile?date_from=2026-05-01&date_to=2026-05-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "2,750.00" in html, (
            "Total spent for May 2026 should be ₹2,750.00"
        )

    def test_custom_range_filters_transaction_count(self, auth_client):
        """Transaction count stat reflects only in-range expenses."""
        # Jan + Feb 2026: 2 expenses
        response = auth_client.get(
            "/profile?date_from=2026-01-01&date_to=2026-02-28"
        )
        html = response.data.decode()
        assert "2" in html, "Only 2 transactions exist in Jan–Feb 2026"

    def test_custom_range_filters_transactions_table(self, auth_client):
        """Only in-range transactions appear in the transactions table."""
        response = auth_client.get(
            "/profile?date_from=2026-01-01&date_to=2026-01-31"
        )
        html = response.data.decode()
        assert "January lunch" in html, "Jan expense description should appear"
        assert "February ride" not in html, "Feb expense must not appear in Jan filter"

    def test_custom_range_filters_category_breakdown(self, auth_client):
        """Category breakdown only lists categories present in the date range."""
        # Only Jan 2026: one expense, Food category; Transport has no Jan expenses
        response = auth_client.get(
            "/profile?date_from=2026-01-01&date_to=2026-01-31"
        )
        html = response.data.decode()
        assert "Food" in html, "Food should appear in Jan filter"
        # "February ride" is the only Transport description; if it is absent,
        # Transport was correctly excluded from the breakdown.
        assert "February ride" not in html, (
            "Transport expense description must not appear when filtered to Jan only"
        )

    def test_custom_range_active_preset_is_custom(self, auth_client):
        """When custom dates are provided without a preset param, active is 'custom'."""
        response = auth_client.get(
            "/profile?date_from=2026-01-01&date_to=2026-03-31"
        )
        html = response.data.decode()
        # The date inputs should be pre-filled with the submitted values
        assert 'value="2026-01-01"' in html, "date_from input must reflect the submitted value"
        assert 'value="2026-03-31"' in html, "date_to input must reflect the submitted value"

    def test_custom_range_rupee_symbol_present(self, auth_client):
        """₹ must appear in filtered output regardless of filter state."""
        response = auth_client.get(
            "/profile?date_from=2026-05-01&date_to=2026-05-31"
        )
        assert "₹" in response.data.decode(), (
            "₹ symbol must appear in filtered output"
        )

    def test_single_day_range(self, auth_client):
        """date_from == date_to is a valid single-day filter."""
        response = auth_client.get(
            "/profile?date_from=2026-05-01&date_to=2026-05-01"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "May lunch" in html, "Single-day range should include that day's expense"
        assert "May groceries" not in html, "Expense on a different day must not appear"


# ---------------------------------------------------------------------------
# Preset buttons
# ---------------------------------------------------------------------------

class TestPresetButtons:
    def test_this_month_preset_sets_active_class(self, auth_client):
        today = date.today()
        first = today.replace(day=1)
        response = auth_client.get(
            f"/profile?preset=this_month&date_from={first.isoformat()}&date_to={today.isoformat()}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        import re
        active_links = re.findall(
            r'class="profile-preset-btn profile-preset-btn--active"[^>]*>([^<]+)<', html
        )
        labels = [lbl.strip() for lbl in active_links]
        assert "This Month" in labels, (
            "'This Month' button must carry the active CSS class when preset=this_month"
        )

    def test_last_3_months_preset_sets_active_class(self, auth_client):
        today = date.today()
        start = _month_offset(today, 3)
        response = auth_client.get(
            f"/profile?preset=last_3_months&date_from={start.isoformat()}&date_to={today.isoformat()}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        import re
        active_links = re.findall(
            r'class="profile-preset-btn profile-preset-btn--active"[^>]*>([^<]+)<', html
        )
        labels = [lbl.strip() for lbl in active_links]
        assert "Last 3 Months" in labels, (
            "'Last 3 Months' button must carry the active CSS class"
        )

    def test_last_6_months_preset_sets_active_class(self, auth_client):
        today = date.today()
        start = _month_offset(today, 6)
        response = auth_client.get(
            f"/profile?preset=last_6_months&date_from={start.isoformat()}&date_to={today.isoformat()}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        import re
        active_links = re.findall(
            r'class="profile-preset-btn profile-preset-btn--active"[^>]*>([^<]+)<', html
        )
        labels = [lbl.strip() for lbl in active_links]
        assert "Last 6 Months" in labels, (
            "'Last 6 Months' button must carry the active CSS class"
        )

    def test_all_time_preset_sets_active_class(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        import re
        active_links = re.findall(
            r'class="profile-preset-btn profile-preset-btn--active"[^>]*>([^<]+)<', html
        )
        labels = [lbl.strip() for lbl in active_links]
        assert "All Time" in labels, (
            "'All Time' button must carry the active CSS class when no filter is active"
        )


# ---------------------------------------------------------------------------
# date_from > date_to — error message + fallback to unfiltered
# ---------------------------------------------------------------------------

class TestInvertedDateRange:
    def test_inverted_range_returns_200(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01"
        )
        assert response.status_code == 200, "Inverted date range must not crash (500)"

    def test_inverted_range_shows_flash_error(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01"
        )
        html = response.data.decode()
        assert "Start date must be before end date" in html, (
            "Error message must be shown when date_from > date_to"
        )

    def test_inverted_range_falls_back_to_unfiltered(self, auth_client):
        """
        After the error, all expenses are still shown (unfiltered behaviour).
        Our dataset has 7 expenses total.
        """
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01"
        )
        html = response.data.decode()
        # transaction_count of 7 must appear in the stats
        assert "7" in html, (
            "Unfiltered count (7) must appear after invalid range is discarded"
        )

    def test_inverted_range_date_inputs_cleared(self, auth_client):
        """
        Template receives empty raw_from / raw_to so the date inputs are blank
        after the error (the user sees a clean form, not the bad values).
        """
        response = auth_client.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01"
        )
        html = response.data.decode()
        # The inputs should NOT contain the bad values
        assert 'value="2026-12-31"' not in html, (
            "date_from input must be cleared after inverted-range error"
        )
        assert 'value="2026-01-01"' not in html, (
            "date_to input must be cleared after inverted-range error"
        )

    def test_same_day_is_valid(self, auth_client):
        """date_from == date_to is a boundary case — must NOT trigger the error."""
        response = auth_client.get(
            "/profile?date_from=2026-05-08&date_to=2026-05-08"
        )
        html = response.data.decode()
        assert "Start date must be before end date" not in html, (
            "Equal date_from and date_to must not trigger the error"
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Malformed date strings — silent fallback, no crash
# ---------------------------------------------------------------------------

class TestMalformedDates:
    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date", "2026-05-31"),
        ("2026-01-01", "not-a-date"),
        ("not-a-date", "not-a-date"),
        ("2026-13-01", "2026-05-31"),   # month 13 is invalid
        ("2026-00-01", "2026-05-31"),   # month 00 is invalid
        ("abcdefgh",  "ijklmnop"),
        ("",          ""),
        ("2026/01/01", "2026/05/31"),   # wrong separator
        ("01-01-2026", "31-05-2026"),   # wrong order
    ])
    def test_malformed_date_does_not_crash(self, auth_client, bad_from, bad_to):
        """Any malformed date string must silently fall back — never return 500."""
        url = f"/profile?date_from={bad_from}&date_to={bad_to}"
        response = auth_client.get(url)
        assert response.status_code == 200, (
            f"Malformed dates ({bad_from!r}, {bad_to!r}) must not crash the app"
        )

    @pytest.mark.parametrize("bad_from,bad_to", [
        ("not-a-date", "2026-05-31"),
        ("2026-13-01", "2026-05-31"),
        ("2026/01/01", "2026/05/31"),
    ])
    def test_malformed_date_falls_back_to_unfiltered(self, auth_client, bad_from, bad_to):
        """
        When one or both date params are malformed, the page shows all
        expenses (unfiltered). Our dataset has 7 expenses.
        """
        url = f"/profile?date_from={bad_from}&date_to={bad_to}"
        response = auth_client.get(url)
        html = response.data.decode()
        assert "7" in html, (
            f"Malformed date ({bad_from!r}, {bad_to!r}) should fall back to unfiltered (7 txs)"
        )

    def test_malformed_date_no_error_message_shown(self, auth_client):
        """Malformed dates are silently ignored — no error message should appear."""
        response = auth_client.get(
            "/profile?date_from=not-a-date&date_to=also-bad"
        )
        html = response.data.decode()
        assert "Start date must be before end date" not in html, (
            "Malformed date should not trigger the date-order error message"
        )


# ---------------------------------------------------------------------------
# User with no expenses in selected range
# ---------------------------------------------------------------------------

class TestNoExpensesInRange:
    def test_user_with_no_expenses_at_all(self, auth_client_no_expenses):
        """A user with zero expenses should not crash the profile page."""
        response = auth_client_no_expenses.get("/profile")
        assert response.status_code == 200

    def test_user_with_no_expenses_shows_zero_total(self, auth_client_no_expenses):
        response = auth_client_no_expenses.get("/profile")
        html = response.data.decode()
        assert "0.00" in html, "Zero total spent must display as 0.00"

    def test_user_with_no_expenses_shows_zero_transactions(self, auth_client_no_expenses):
        response = auth_client_no_expenses.get("/profile")
        html = response.data.decode()
        # The summary stats section renders transaction_count; 0 is returned by the query
        assert "Transactions" in html, "Transactions label must be rendered in stats section"
        assert "0.00" in html, "With no expenses, total spent must be 0.00"

    def test_user_with_expenses_but_none_in_range(self, auth_client):
        """
        A user has expenses, but none fall within the requested date window.
        All three sections must gracefully show empty/zero state.
        """
        response = auth_client.get(
            "/profile?date_from=2020-01-01&date_to=2020-12-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "0.00" in html, "Total spent must be 0.00 when no expenses in range"

    def test_no_expenses_in_range_rupee_symbol_still_present(self, auth_client):
        """₹ must still render even when filtered result is empty."""
        response = auth_client.get(
            "/profile?date_from=2020-01-01&date_to=2020-12-31"
        )
        assert "₹" in response.data.decode(), (
            "₹ symbol must appear even when no expenses fall in the selected range"
        )

    def test_no_expenses_in_range_no_category_rows(self, auth_client):
        """Category breakdown should be empty (no <li> rows) when no expenses in range."""
        response = auth_client.get(
            "/profile?date_from=2020-01-01&date_to=2020-12-31"
        )
        html = response.data.decode()
        # No category name from the dataset should appear in a breakdown context
        assert "profile-category-row" not in html, (
            "No category rows should be rendered when no expenses are in the range"
        )


# ---------------------------------------------------------------------------
# Unit tests: query helpers with date filter params
# ---------------------------------------------------------------------------

class TestQueryHelperDateFilter:
    """
    Direct unit tests of the three query functions with date_from / date_to.
    These are isolated from the HTTP layer.
    """

    # --- get_summary_stats ---

    def test_get_summary_stats_filtered_by_date(self, user_with_expenses):
        """May 2026: 450 + 2200 + 100 = 2750, 3 transactions."""
        stats = get_summary_stats(user_with_expenses, "2026-05-01", "2026-05-31")
        assert stats["transaction_count"] == 3
        total = float(stats["total_spent"].replace(",", ""))
        assert abs(total - 2750.00) < 0.01

    def test_get_summary_stats_no_expenses_in_range(self, user_with_expenses):
        """Date range with no matching expenses returns zero stats."""
        stats = get_summary_stats(user_with_expenses, "2020-01-01", "2020-12-31")
        assert stats["transaction_count"] == 0
        assert stats["total_spent"] == "0.00"
        assert stats["top_category"] == "—"

    def test_get_summary_stats_without_date_filter(self, user_with_expenses):
        """No date params returns all 7 expenses."""
        stats = get_summary_stats(user_with_expenses)
        assert stats["transaction_count"] == 7

    def test_get_summary_stats_date_from_only_ignored(self, user_with_expenses):
        """
        Per spec: when only one param is provided (not both), the filter is
        not applied — falls back to unfiltered.
        """
        stats = get_summary_stats(user_with_expenses, date_from="2026-05-01", date_to=None)
        assert stats["transaction_count"] == 7, (
            "Only date_from without date_to should not apply any filter"
        )

    def test_get_summary_stats_date_to_only_ignored(self, user_with_expenses):
        stats = get_summary_stats(user_with_expenses, date_from=None, date_to="2026-05-31")
        assert stats["transaction_count"] == 7, (
            "Only date_to without date_from should not apply any filter"
        )

    def test_get_summary_stats_inclusive_bounds(self, user_with_expenses):
        """BETWEEN is inclusive — expenses exactly on boundary dates must be counted."""
        # 2026-01-15 is in dataset
        stats = get_summary_stats(user_with_expenses, "2026-01-15", "2026-01-15")
        assert stats["transaction_count"] == 1
        assert float(stats["total_spent"].replace(",", "")) == pytest.approx(500.00)

    # --- get_recent_transactions ---

    def test_get_recent_transactions_filtered_by_date(self, user_with_expenses):
        """Jan–Feb 2026: 2 transactions, ordered newest first."""
        txs = get_recent_transactions(user_with_expenses, date_from="2026-01-01", date_to="2026-02-28")
        assert len(txs) == 2
        # newest first: February before January
        assert txs[0]["date"] == "10 Feb 2026"
        assert txs[1]["date"] == "15 Jan 2026"

    def test_get_recent_transactions_no_results_in_range(self, user_with_expenses):
        txs = get_recent_transactions(user_with_expenses, date_from="2020-01-01", date_to="2020-12-31")
        assert txs == [], "Empty list expected when no expenses fall in range"

    def test_get_recent_transactions_without_filter(self, user_with_expenses):
        txs = get_recent_transactions(user_with_expenses)
        assert len(txs) == 7, "All 7 expenses should be returned with no filter"

    def test_get_recent_transactions_limit_respected_within_range(self, user_with_expenses):
        """Limit still applies even when date filter is active."""
        # May 2026 has 3 expenses; limit=2 should return only 2
        txs = get_recent_transactions(
            user_with_expenses, limit=2,
            date_from="2026-05-01", date_to="2026-05-31"
        )
        assert len(txs) == 2

    def test_get_recent_transactions_fields_present(self, user_with_expenses):
        """Each transaction dict must have required keys."""
        txs = get_recent_transactions(
            user_with_expenses, date_from="2026-05-01", date_to="2026-05-31"
        )
        for tx in txs:
            assert "date" in tx
            assert "description" in tx
            assert "category" in tx
            assert "amount" in tx

    def test_get_recent_transactions_inclusive_bounds(self, user_with_expenses):
        """Expense exactly on the boundary date must be included."""
        txs = get_recent_transactions(
            user_with_expenses, date_from="2026-05-08", date_to="2026-05-08"
        )
        assert len(txs) == 1
        assert txs[0]["description"] == "May groceries"

    # --- get_category_breakdown ---

    def test_get_category_breakdown_filtered_by_date(self, user_with_expenses):
        """
        May 2026 expenses:
          Food       450.00
          Shopping  2200.00
          Other      100.00
        Expect 3 categories, ordered by total desc.
        """
        cats = get_category_breakdown(user_with_expenses, "2026-05-01", "2026-05-31")
        assert len(cats) == 3
        names = [c["name"] for c in cats]
        assert "Shopping" in names
        assert "Food" in names
        assert "Other" in names
        # Ordered desc by total — Shopping is largest
        assert cats[0]["name"] == "Shopping"

    def test_get_category_breakdown_no_results_in_range(self, user_with_expenses):
        cats = get_category_breakdown(user_with_expenses, "2020-01-01", "2020-12-31")
        assert cats == [], "Empty list expected when no expenses fall in range"

    def test_get_category_breakdown_percentages_sum_to_100(self, user_with_expenses):
        cats = get_category_breakdown(user_with_expenses, "2026-05-01", "2026-05-31")
        assert len(cats) > 0
        total_pct = sum(c["percent"] for c in cats)
        assert total_pct == 100, (
            f"Category percentages must sum to 100, got {total_pct}"
        )

    def test_get_category_breakdown_without_filter(self, user_with_expenses):
        """No date params returns all categories (6 distinct ones in our fixture)."""
        cats = get_category_breakdown(user_with_expenses)
        assert len(cats) == 6, "6 distinct categories exist across all expenses"

    def test_get_category_breakdown_date_from_only_ignored(self, user_with_expenses):
        """Only date_from without date_to — no filter applied."""
        cats = get_category_breakdown(user_with_expenses, date_from="2026-05-01", date_to=None)
        assert len(cats) == 6, (
            "Only date_from without date_to must not apply any filter"
        )


# ---------------------------------------------------------------------------
# ₹ symbol rendering across all filter states
# ---------------------------------------------------------------------------

class TestRupeeSymbol:
    @pytest.mark.parametrize("query_string", [
        "",
        "?date_from=2026-05-01&date_to=2026-05-31",
        "?date_from=2026-01-01&date_to=2026-01-31",
        "?date_from=2020-01-01&date_to=2020-12-31",   # no results range
        "?preset=this_month",
    ])
    def test_rupee_symbol_present_in_all_filter_states(self, auth_client, query_string):
        response = auth_client.get(f"/profile{query_string}")
        assert response.status_code == 200
        assert "₹" in response.data.decode(), (
            f"₹ must be present for query_string={query_string!r}"
        )

    def test_rupee_symbol_present_for_user_with_no_expenses(self, auth_client_no_expenses):
        response = auth_client_no_expenses.get("/profile")
        assert "₹" in response.data.decode(), (
            "₹ must be present even when the user has no expenses at all"
        )


# ---------------------------------------------------------------------------
# Template structure / HTML landmarks
# ---------------------------------------------------------------------------

class TestTemplateStructure:
    def test_filter_bar_section_exists(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "profile-filter-bar" in html, (
            "profile-filter-bar CSS class must be present in the rendered HTML"
        )

    def test_preset_links_rendered(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "profile-preset-btn" in html, (
            "profile-preset-btn CSS class must be used for preset buttons"
        )

    def test_stats_row_rendered(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "Total Spent" in html
        assert "Transactions" in html
        assert "Top Category" in html

    def test_recent_transactions_section_rendered(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "Recent Transactions" in html

    def test_category_breakdown_section_rendered(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "Spending by Category" in html

    def test_filter_error_div_not_shown_when_no_error(self, auth_client):
        response = auth_client.get("/profile")
        html = response.data.decode()
        assert "profile-filter-error" not in html, (
            "Error div must not appear when there is no filter error"
        )

    def test_filter_error_div_shown_on_inverted_range(self, auth_client):
        response = auth_client.get(
            "/profile?date_from=2026-12-01&date_to=2026-01-01"
        )
        html = response.data.decode()
        assert "profile-filter-error" in html, (
            "Error div must appear when date_from > date_to"
        )
