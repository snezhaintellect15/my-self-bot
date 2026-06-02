import psycopg2
import os
import re
import socket
from datetime import datetime, date, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    """Подключается к Supabase, обрабатывая любой формат хоста (домен, IPv4, IPv6)"""
    # Ожидаемый формат: postgresql://user:password@host:port/dbname
    pattern = r'^postgresql://(.*?):(.*?)@(.*?):(\d+)/(.*?)$'
    match = re.match(pattern, DATABASE_URL)
    if not match:
        raise ValueError(f"Невозможно разобрать DATABASE_URL: {DATABASE_URL}")
    user, password, host, port, dbname = match.groups()

    # Если хост уже IP-адрес (v4 или v6) — используем как есть
    # Если это домен — получаем IPv4
    try:
        socket.inet_pton(socket.AF_INET, host)   # Это IPv4
        host_ip = host
    except OSError:
        try:
            socket.inet_pton(socket.AF_INET6, host)  # Это IPv6
            host_ip = f"[{host}]"  # psycopg2 требует квадратные скобки для IPv6
        except OSError:
            # Это доменное имя
            host_ip = socket.gethostbyname(host)

    new_url = f"postgresql://{user}:{password}@{host_ip}:{port}/{dbname}"
    return psycopg2.connect(new_url, sslmode='require')

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            is_premium SMALLINT DEFAULT 0
        )
    """)

    # Таблица категорий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)

    # Таблица обещаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agreements (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            category_id INTEGER DEFAULT NULL REFERENCES categories(id),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            is_done SMALLINT DEFAULT 0,
            done_at TIMESTAMPTZ DEFAULT NULL
        )
    """)

    # Таблица достижений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id BIGINT NOT NULL,
            achievement_key TEXT NOT NULL,
            awarded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, achievement_key)
        )
    """)

    # Таблица напоминаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id BIGINT PRIMARY KEY,
            remind_time TEXT NOT NULL
        )
    """)

    # Таблица ежедневной сводки
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            user_id BIGINT PRIMARY KEY,
            summary_time TEXT NOT NULL
        )
    """)

    # Таблица запланированных напоминаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_reminders (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            agreement_id INTEGER REFERENCES agreements(id) ON DELETE CASCADE,
            remind_date DATE NOT NULL,
            remind_time TIME NOT NULL,
            is_recurring SMALLINT DEFAULT 0,
            recurring_day INTEGER DEFAULT NULL,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# ---------- Пользователи ----------
def create_user(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
    conn.commit()
    conn.close()

def is_premium(user_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0])

def set_premium(user_id: int, status: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, is_premium) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET is_premium = EXCLUDED.is_premium",
        (user_id, int(status))
    )
    conn.commit()
    conn.close()

# ---------- Категории ----------
def create_category(user_id: int, name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO categories (user_id, name) VALUES (%s, %s)", (user_id, name))
        conn.commit()
        conn.close()
        return True
    except psycopg2.IntegrityError:
        conn.close()
        return False

def get_categories(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories WHERE user_id = %s ORDER BY name", (user_id,))
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_category_count(user_id: int) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM categories WHERE user_id = %s", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ---------- Обещания ----------
def add_agreement(user_id: int, text: str, category_id: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO agreements (user_id, text, category_id) VALUES (%s, %s, %s)", (user_id, text, category_id))
    conn.commit()
    conn.close()

def get_agreements(user_id: int, only_active: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT a.id, a.text, a.is_done, c.name as category_name
        FROM agreements a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.user_id = %s
    """
    if only_active:
        query += " AND a.is_done = 0"
    query += " ORDER BY a.category_id IS NULL, c.name, a.created_at DESC"
    cursor.execute(query, (user_id,))
    agreements = cursor.fetchall()
    conn.close()
    return agreements

def get_agreement_by_id(agreement_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, is_done, user_id, category_id FROM agreements WHERE id = %s", (agreement_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_agreement(agreement_id: int, new_text: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET text = %s WHERE id = %s", (new_text, agreement_id))
    conn.commit()
    conn.close()

def mark_done(agreement_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET is_done = 1, done_at = CURRENT_TIMESTAMP WHERE id = %s", (agreement_id,))
    conn.commit()
    conn.close()

def delete_agreement(agreement_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agreements WHERE id = %s", (agreement_id,))
    conn.commit()
    conn.close()

# ---------- Ежедневные напоминания ----------
def set_reminder(user_id: int, time_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reminders (user_id, remind_time) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET remind_time = EXCLUDED.remind_time",
        (user_id, time_str)
    )
    conn.commit()
    conn.close()

def delete_reminder(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

def get_reminder(user_id: int) -> str | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT remind_time FROM reminders WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_users_with_reminders() -> list[tuple[int, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, remind_time FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------- Ежедневная сводка ----------
def set_summary_time(user_id: int, time_str: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO daily_summary (user_id, summary_time) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET summary_time = EXCLUDED.summary_time",
        (user_id, time_str)
    )
    conn.commit()
    conn.close()

def delete_summary_time(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_summary WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()

def get_summary_time(user_id: int) -> str | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT summary_time FROM daily_summary WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_users_with_summary() -> list[tuple[int, str]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, summary_time FROM daily_summary")
    rows = cursor.fetchall()
    conn.close()
    return rows

# ---------- Статистика ----------
def get_stats(user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = %s", (user_id,))
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = %s AND is_done = 1", (user_id,))
    done = cursor.fetchone()[0]

    percent = round(done / total * 100, 1) if total > 0 else 0.0

    cursor.execute("SELECT DISTINCT DATE(created_at) as d FROM agreements WHERE user_id = %s AND is_done = 1 ORDER BY d DESC", (user_id,))
    dates = [row[0] for row in cursor.fetchall()]

    streak = 0
    if dates:
        streak_end = dates[0] if isinstance(dates[0], date) else datetime.strptime(str(dates[0]), "%Y-%m-%d").date()
        streak = 1
        expected = streak_end - timedelta(days=1)
        for d_str in dates[1:]:
            d = d_str if isinstance(d_str, date) else datetime.strptime(str(d_str), "%Y-%m-%d").date()
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break

    conn.close()
    return {"total": total, "done": done, "percent": percent, "streak": streak}

# ---------- Экспорт ----------
def get_agreements_export(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.text, c.name, a.created_at, a.is_done, a.done_at
        FROM agreements a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.user_id = %s
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT achievement_key FROM achievements WHERE user_id = %s", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def award_achievement(user_id: int, key: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO achievements (user_id, achievement_key) VALUES (%s, %s)", (user_id, key))
        conn.commit()
        conn.close()
        return True
    except psycopg2.IntegrityError:
        conn.close()
        return False

def check_achievements(user_id: int) -> list[str]:
    newly_awarded = []
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = %s", (user_id,))
    total_created = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = %s AND is_done = 1", (user_id,))
    total_done = cursor.fetchone()[0]
    cursor.execute("SELECT DISTINCT DATE(created_at) as d FROM agreements WHERE user_id = %s AND is_done = 1 ORDER BY d DESC", (user_id,))
    dates = [row[0] for row in cursor.fetchall()]
    streak = 0
    if dates:
        streak_end = dates[0] if isinstance(dates[0], date) else datetime.strptime(str(dates[0]), "%Y-%m-%d").date()
        streak = 1
        expected = streak_end - timedelta(days=1)
        for d_str in dates[1:]:
            d = d_str if isinstance(d_str, date) else datetime.strptime(str(d_str), "%Y-%m-%d").date()
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scheduled_reminders WHERE user_id = %s", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def create_scheduled_reminder(user_id: int, agreement_id: int, remind_date: date, remind_time: str, is_recurring: bool = False, recurring_day: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO scheduled_reminders (user_id, agreement_id, remind_date, remind_time, is_recurring, recurring_day) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, agreement_id, remind_date.isoformat(), remind_time, int(is_recurring), recurring_day)
    )
    conn.commit()
    conn.close()

def get_pending_reminders_for_now(now_date: date, now_time: str) -> list[tuple]:
    conn = get_connection()
    cursor = conn.cursor()
    # Одноразовые на сегодня
    cursor.execute("""
        SELECT sr.id, sr.user_id, a.text
        FROM scheduled_reminders sr
        JOIN agreements a ON sr.agreement_id = a.id
        WHERE sr.remind_date = %s AND sr.remind_time = %s AND sr.is_recurring = 0
    """, (now_date.isoformat(), now_time))
    results = cursor.fetchall()
    # Повторяющиеся по дню недели
    weekday = now_date.weekday()
    cursor.execute("""
        SELECT sr.id, sr.user_id, a.text
        FROM scheduled_reminders sr
        JOIN agreements a ON sr.agreement_id = a.id
        WHERE sr.is_recurring = 1 AND sr.recurring_day = %s AND sr.remind_time = %s
    """, (weekday, now_time))
    results.extend(cursor.fetchall())
    conn.close()
    return results

def delete_scheduled_reminder(reminder_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM scheduled_reminders WHERE id = %s", (reminder_id,))
    conn.commit()
    conn.close()