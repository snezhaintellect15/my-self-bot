import sqlite3
from datetime import datetime, date, timedelta

DB_NAME = "agreements.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            category_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_done INTEGER DEFAULT 0,
            done_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER NOT NULL,
            achievement_key TEXT NOT NULL,
            awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, achievement_key)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id INTEGER PRIMARY KEY,
            remind_time TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            user_id INTEGER PRIMARY KEY,
            summary_time TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            agreement_id INTEGER REFERENCES agreements(id) ON DELETE CASCADE,
            remind_date DATE NOT NULL,
            remind_time TIME NOT NULL,
            is_recurring INTEGER DEFAULT 0,
            recurring_day INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    try:
        cursor.execute("ALTER TABLE agreements ADD COLUMN done_at TIMESTAMP DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE agreements ADD COLUMN category_id INTEGER DEFAULT NULL REFERENCES categories(id)")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

# ---------- Пользователи ----------
def create_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def is_premium(user_id: int) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])

def set_premium(user_id: int, status: bool):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, is_premium) VALUES (?, ?)", (user_id, int(status)))
    conn.commit()
    conn.close()

# ---------- Категории ----------
def create_category(user_id: int, name: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_categories(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories WHERE user_id = ? ORDER BY name", (user_id,))
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_category_count(user_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categories WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ---------- Обещания ----------
def add_agreement(user_id: int, text: str, category_id: int = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO agreements (user_id, text, category_id) VALUES (?, ?, ?)", (user_id, text, category_id))
    conn.commit()
    conn.close()

def get_agreements(user_id: int, only_active: bool = False):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = """
        SELECT a.id, a.text, a.is_done, c.name as category_name
        FROM agreements a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.user_id = ?
    """
    if only_active:
        query += " AND a.is_done = 0"
    query += " ORDER BY a.category_id IS NULL, c.name, a.created_at DESC"
    cursor.execute(query, (user_id,))
    agreements = cursor.fetchall()
    conn.close()
    return agreements

def get_agreement_by_id(agreement_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, is_done, user_id, category_id FROM agreements WHERE id = ?", (agreement_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_agreement(agreement_id: int, new_text: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET text = ? WHERE id = ?", (new_text, agreement_id))
    conn.commit()
    conn.close()

def mark_done(agreement_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET is_done = 1, done_at = CURRENT_TIMESTAMP WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()

def delete_agreement(agreement_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agreements WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()

# ---------- Ежедневные напоминания ----------
def set_reminder(user_id: int, time_str: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO reminders (user_id, remind_time) VALUES (?, ?)", (user_id, time_str))
    conn.commit()
    conn.close()

def delete_reminder(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_reminder(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT remind_time FROM reminders WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_users_with_reminders() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, remind_time FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------- Ежедневная сводка ----------
def set_summary_time(user_id: int, time_str: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO daily_summary (user_id, summary_time) VALUES (?, ?)", (user_id, time_str))
    conn.commit()
    conn.close()

def delete_summary_time(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_summary WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_summary_time(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT summary_time FROM daily_summary WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_users_with_summary() -> list[tuple[int, str]]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, summary_time FROM daily_summary")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------- Статистика ----------
def get_stats(user_id: int) -> dict:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ? AND is_done = 1", (user_id,))
    done = cursor.fetchone()[0]
    percent = round(done / total * 100, 1) if total > 0 else 0.0
    cursor.execute("SELECT DISTINCT DATE(created_at) as d FROM agreements WHERE user_id = ? AND is_done = 1 ORDER BY d DESC", (user_id,))
    dates = [row[0] for row in cursor.fetchall()]
    streak = 0
    if dates:
        streak_end = datetime.strptime(dates[0], "%Y-%m-%d").date()
        streak = 1
        expected = streak_end - timedelta(days=1)
        for d_str in dates[1:]:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
    conn.close()
    return {"total": total, "done": done, "percent": percent, "streak": streak}

# ---------- Экспорт ----------
def get_agreements_export(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.text, c.name, a.created_at, a.is_done, a.done_at
        FROM agreements a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (user_id,))
    data = cursor.fetchall()
    conn.close()
    return data

# ---------- Достижения ----------
ACHIEVEMENTS = {
    "novice": ("🏅 Новичок", "Создать 10 обещаний"),
    "discipline": ("🔥 Дисциплина", "Выполнять обещания 7 дней подряд"),
    "champion": ("👑 Чемпион", "Выполнить 100 обещаний"),
}

def get_user_achievements(user_id: int) -> list[str]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT achievement_key FROM achievements WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def award_achievement(user_id: int, key: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO achievements (user_id, achievement_key) VALUES (?, ?)", (user_id, key))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def check_achievements(user_id: int) -> list[str]:
    newly_awarded = []
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ?", (user_id,))
    total_created = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ? AND is_done = 1", (user_id,))
    total_done = cursor.fetchone()[0]
    cursor.execute("SELECT DISTINCT DATE(created_at) as d FROM agreements WHERE user_id = ? AND is_done = 1 ORDER BY d DESC", (user_id,))
    dates = [row[0] for row in cursor.fetchall()]
    streak = 0
    if dates:
        streak_end = datetime.strptime(dates[0], "%Y-%m-%d").date()
        streak = 1
        expected = streak_end - timedelta(days=1)
        for d_str in dates[1:]:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
    if total_created >= 10 and award_achievement(user_id, "novice"):
        newly_awarded.append("novice")
    if streak >= 7 and award_achievement(user_id, "discipline"):
        newly_awarded.append("discipline")
    if total_done >= 100 and award_achievement(user_id, "champion"):
        newly_awarded.append("champion")
    conn.close()
    return newly_awarded

# ---------- Запланированные напоминания ----------
def count_scheduled_reminders(user_id: int) -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scheduled_reminders WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def create_scheduled_reminder(user_id: int, agreement_id: int, remind_date: date, remind_time: str, is_recurring: bool = False, recurring_day: int = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scheduled_reminders (user_id, agreement_id, remind_date, remind_time, is_recurring, recurring_day) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, agreement_id, remind_date.isoformat(), remind_time, int(is_recurring), recurring_day)
    )
    conn.commit()
    conn.close()

def get_pending_reminders_for_now(now_date: date, now_time: str) -> list[tuple]:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sr.id, sr.user_id, a.text
        FROM scheduled_reminders sr
        JOIN agreements a ON sr.agreement_id = a.id
        WHERE sr.remind_date = ? AND sr.remind_time = ? AND sr.is_recurring = 0
    """, (now_date.isoformat(), now_time))
    results = cursor.fetchall()
    weekday = now_date.weekday()
    cursor.execute("""
        SELECT sr.id, sr.user_id, a.text
        FROM scheduled_reminders sr
        JOIN agreements a ON sr.agreement_id = a.id
        WHERE sr.is_recurring = 1 AND sr.recurring_day = ? AND sr.remind_time = ?
    """, (weekday, now_time))
    results.extend(cursor.fetchall())
    conn.close()
    return results

def delete_scheduled_reminder(reminder_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()