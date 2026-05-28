import sqlite3

DB_NAME = "agreements.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_done INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def add_agreement(user_id: int, text: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO agreements (user_id, text) VALUES (?, ?)", (user_id, text))
    conn.commit()
    conn.close()

def get_agreements(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, is_done FROM agreements WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    agreements = cursor.fetchall()
    conn.close()
    return agreements

def get_agreement_by_id(agreement_id: int):
    """Возвращает одно обещание по ID или None, если не найдено"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, text, is_done, user_id FROM agreements WHERE id = ?", (agreement_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_agreement(agreement_id: int, new_text: str):
    """Изменяет текст обещания"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET text = ? WHERE id = ?", (new_text, agreement_id))
    conn.commit()
    conn.close()

def mark_done(agreement_id: int):
    """Отмечает обещание выполненным"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE agreements SET is_done = 1 WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()

def delete_agreement(agreement_id: int):
    """Удаляет обещание по id"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agreements WHERE id = ?", (agreement_id,))
    conn.commit()
    conn.close()