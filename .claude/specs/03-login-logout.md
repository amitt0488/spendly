# Spec: Login and Logout

## Overview
Step 3 implements session-based login and logout for Spendly. When a registered user submits the login form with valid credentials, Flask's signed cookie session is populated with their `user_id` and they are redirected to their dashboard (stub for now, redirects to `/`). Invalid credentials re-render the login form with a generic error to avoid user enumeration. Logout clears the session and redirects to the landing page. This step makes the app aware of who is currently signed in, which all subsequent steps depend on.

## Depends on
- Step 1 — Database Setup (`users` table, `get_db()` must be in place)
- Step 2 — Registration (`get_user_by_email()` must exist in `database/db.py`)

## Routes
- `POST /login` — process login form submission — public
- `GET /logout` — clear session and redirect to landing — public (currently a stub)

## Database changes
No new tables or columns. One new helper function added to `database/db.py`:

- `get_user_by_id(user_id)` — returns the user row for a given id, or `None` if not found; used to load the current user from the session

## Templates
- **Modify:** `templates/login.html` — confirm the form posts to `url_for('login')` with `method="POST"`; add rendering of `{{ error }}` if not already present
- **Modify:** `templates/base.html` — add conditional nav links: show "Logout" when `session.user_id` is set, show "Login" and "Register" when not

## Files to change
- `app.py` — convert `GET /login` stub to `GET`+`POST` handler; implement `GET /logout` stub
- `database/db.py` — add `get_user_by_id()`

## Files to create
None.

## New dependencies
No new dependencies. `flask.session` and `werkzeug.security.check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic stays in `database/db.py` — route functions only call helpers, never execute SQL directly
- Use `abort()` for unexpected server errors, not bare string returns
- Use `url_for()` for all redirects — never hardcode paths
- On failed login, use a **generic** error message ("Invalid email or password.") — do not distinguish between "email not found" and "wrong password" to prevent user enumeration
- `app.secret_key` is already set via `os.environ.get("SECRET_KEY", "dev-secret-change-in-production")` — do not change it
- Session key must be `user_id` (integer) — consistent naming for all future steps

## Validation rules
| Field | Rule |
|-------|------|
| `email` | Required; normalise to lowercase before lookup |
| `password` | Required |

On missing field: re-render `login.html` with `error="Email and password are required."`.  
On bad credentials: re-render `login.html` with `error="Invalid email or password."`.  
On success: `session['user_id'] = user.id` then `redirect(url_for('landing'))`.

## Definition of done
- [ ] Submitting the login form with valid credentials sets `session['user_id']` and redirects to `/`
- [ ] Submitting with an incorrect password re-renders the login form with a generic error and does **not** set the session
- [ ] Submitting with an email that does not exist re-renders the login form with the same generic error
- [ ] Submitting with a blank email or password re-renders the form with a required-fields error
- [ ] Visiting `/logout` clears `session['user_id']` and redirects to `/`
- [ ] After logout, visiting `/logout` again does not raise an error (session pop is safe on empty session)
- [ ] The nav in `base.html` shows "Logout" when logged in and "Login"/"Register" when logged out
- [ ] No SQL is executed directly inside `app.py` — all queries go through `database/db.py`
- [ ] `pytest` passes with no errors after implementation
