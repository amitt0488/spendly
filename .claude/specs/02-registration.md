# Spec: Registration

## Overview
Step 2 implements user registration for Spendly. When a visitor submits the registration form, the app validates their input, checks for duplicate emails, hashes the password, and inserts a new user row. On success the user is redirected to the login page with a flash message; on failure the form re-renders with a clear error. This step wires the already-rendered `register.html` form to a real `POST /register` backend, making new account creation fully functional.

## Depends on
- Step 1 — Database Setup (`users` table, `get_db()`, `init_db()`, `seed_db()` must be in place)

## Routes
- `POST /register` — process registration form submission — public

## Database changes
No new tables or columns. Two new helper functions are added to `database/db.py`:

- `get_user_by_email(email)` — returns the user row for a given email, or `None` if not found; used to detect duplicate emails before insert
- `create_user(name, email, password_hash)` — inserts a new row into `users` and returns the new `id`

## Templates
- **Modify:** `templates/register.html` — no structural changes needed; the form already posts to `/register` and renders `{{ error }}`. Confirm `action` attribute uses `url_for('register')` and the three field `name` attributes are exactly `name`, `email`, `password`.

## Files to change
- `app.py` — add `POST /register` route (merge with existing `GET /register` into one function using `methods=['GET', 'POST']`)
- `database/db.py` — add `get_user_by_email()` and `create_user()`

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` — never stored in plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic stays in `database/db.py` — the route function only calls helpers, never executes SQL directly
- Use `abort()` for unexpected server errors, not bare string returns
- Use `url_for()` for all redirects — never hardcode paths
- Validation must run server-side even if the browser already enforces `required`/`type="email"`

## Validation rules
| Field | Rule |
|-------|------|
| `name` | Required; strip whitespace; 1–100 characters |
| `email` | Required; must contain `@`; normalise to lowercase |
| `password` | Required; minimum 8 characters |

On duplicate email: re-render `register.html` with `error="An account with that email already exists."`.  
On validation failure: re-render `register.html` with a specific `error` message per field.  
On success: `redirect(url_for('login'))`.

## Definition of done
- [ ] Submitting the form with all valid, unique credentials creates a new row in `users` and redirects to `/login`
- [ ] Submitting with a duplicate email re-renders the registration form with an error message and does **not** insert a row
- [ ] Submitting with a missing name, email, or password re-renders the form with a field-specific error
- [ ] Submitting with a password shorter than 8 characters re-renders the form with an error
- [ ] The stored `password_hash` is not the plaintext password (verify in DB browser or `sqlite3` CLI)
- [ ] No SQL is executed directly inside `app.py` — all queries go through `database/db.py`
- [ ] `pytest` passes with no errors after implementation
