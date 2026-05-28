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
    cursor.execute("SELECT id, text, is_done FROM agreements WHERE user_id = ?", (user_id,))
    agreements = cursor.fetchall()
    conn.close()
    return agreements