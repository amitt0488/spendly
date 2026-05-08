from database.db import get_db
from datetime import datetime


def get_user_by_id(user_id):
    db = get_db()
    try:
        row = db.execute(
            'SELECT name, email, created_at FROM users WHERE id = ?',
            (user_id,)
        ).fetchone()
    finally:
        db.close()

    if row is None:
        return None

    name = row['name']
    initials = ''.join(part[0].upper() for part in name.split()[:2])
    member_since = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %Y')

    return {
        'name': name,
        'email': row['email'],
        'initials': initials,
        'member_since': member_since,
    }


def get_recent_transactions(user_id, limit=10):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT id, amount, category, date, description '
            'FROM expenses WHERE user_id = ? ORDER BY date DESC LIMIT ?',
            (user_id, limit)
        ).fetchall()
        result = []
        for row in rows:
            formatted_date = datetime.strptime(row['date'], '%Y-%m-%d').strftime('%d %b %Y')
            formatted_amount = '{:,.2f}'.format(row['amount'])
            result.append({
                'date': formatted_date,
                'description': row['description'],
                'category': row['category'],
                'amount': formatted_amount,
            })
        return result
    finally:
        db.close()


def get_category_breakdown(user_id):
    db = get_db()
    try:
        rows = db.execute(
            'SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total DESC',
            (user_id,)
        ).fetchall()

        if not rows:
            return []

        overall_total = sum(row['total'] for row in rows)

        result = []
        for row in rows:
            pct = round(row['total'] / overall_total * 100)
            result.append({
                'name': row['category'],
                'amount': f"{row['total']:,.2f}",
                'percent': pct,
                '_raw': row['total'],
            })

        diff = 100 - sum(item['percent'] for item in result)
        if diff != 0:
            largest = max(result, key=lambda x: x['_raw'])
            largest['percent'] += diff

        for item in result:
            del item['_raw']

        return result
    finally:
        db.close()


def get_summary_stats(user_id):
    db = get_db()
    try:
        row = db.execute(
            'SELECT SUM(amount) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?',
            (user_id,)
        ).fetchone()

        total = row['total'] if row['total'] is not None else 0.0
        count = row['cnt'] if row['cnt'] is not None else 0

        total_spent = f"{total:,.2f}"
        transaction_count = int(count)

        cat_row = db.execute(
            'SELECT category FROM expenses WHERE user_id = ? GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1',
            (user_id,)
        ).fetchone()

        top_category = cat_row['category'] if cat_row else '—'
    finally:
        db.close()

    return {
        'total_spent': total_spent,
        'transaction_count': transaction_count,
        'top_category': top_category,
    }
