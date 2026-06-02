import psycopg2
import os
from datetime import datetime, date, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            is_premium SMALLINT DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id BIGINT NOT NULL,
            achievement_key TEXT NOT NULL,
            awarded_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, achievement_key)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            user_id BIGINT PRIMARY KEY,
            remind_time TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            user_id BIGINT PRIMARY KEY,
            summary_time TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# ... (все остальные функции без изменений: create_user, is_premium, set_premium,
#      create_category, get_categories, get_category_count,
#      add_agreement, get_agreement_by_id, update_agreement, mark_done, delete_agreement,
#      set_reminder, delete_reminder, get_reminder, get_users_with_reminders,
#      set_summary_time, delete_summary_time, get_summary_time, get_users_with_summary,
#      get_stats, get_agreements_export, ACHIEVEMENTS, get_user_achievements,
#      award_achievement, check_achievements)

# Единственное изменение: добавим параметр only_active в get_agreements
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