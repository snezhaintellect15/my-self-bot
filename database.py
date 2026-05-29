import sqlite3

DB_NAME = "agreements.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица пользователей (для премиум-статуса и т.д.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium INTEGER DEFAULT 0
        )
    """)

    # Таблица категорий
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)

    # Таблица обещаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            category_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_done INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    """)

    # Попытка добавить колонку category_id, если её ещё нет
    try:
        cursor.execute("ALTER TABLE agreements ADD COLUMN category_id INTEGER DEFAULT NULL REFERENCES categories(id)")
    except sqlite3.OperationalError:
        pass  # колонка уже существует

    # Таблица напоминаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id INTEGER PRIMARY KEY,
            remind_time TEXT NOT NULL
        )
    """)

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
    """Создаёт категорию. Возвращает True при успехе, False если такая уже есть."""
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

def get_categories(user_id: int) -> list[tuple[int, str]]:
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

def get_agreements(user_id: int):
    """Возвращает список обещаний с названием категории (или None)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.text, a.is_done, c.name as category_name
        FROM agreements a
        LEFT JOIN categories c ON a.category_id = c.id
        WHERE a.user_id = ?
        ORDER BY a.category_id IS NULL, c.name, a.created_at DESC
    """, (user_id,))
    agreements = cursor.fetchall()
    conn.close()
    return agreements  # список кортежей (id, text, is_done, category_name)

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
    cursor.execute("UPDATE agreements SET is_done = 1 WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()

def delete_agreement(agreement_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agreements WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()

# ---------- Напоминания ----------
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