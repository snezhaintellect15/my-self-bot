import os
from datetime import datetime, date, timedelta
from pymongo import MongoClient
from bson.objectid import ObjectId

MONGODB_URI = os.environ.get("MONGODB_URI")
client = MongoClient(MONGODB_URI)
db = client["promise_bot"]  # название базы данных

def init_db():
    """MongoDB создаёт коллекции автоматически, ничего не делаем."""
    pass

# ---------- Пользователи ----------
def create_user(user_id: int):
    if not db.users.find_one({"user_id": user_id}):
        db.users.insert_one({"user_id": user_id, "is_premium": False})

def is_premium(user_id: int) -> bool:
    user = db.users.find_one({"user_id": user_id})
    return user.get("is_premium", False) if user else False

def set_premium(user_id: int, status: bool):
    db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": status}},
        upsert=True
    )

# ---------- Категории ----------
def create_category(user_id: int, name: str) -> bool:
    existing = db.categories.find_one({"user_id": user_id, "name": name})
    if existing:
        return False
    db.categories.insert_one({"user_id": user_id, "name": name})
    return True

def get_categories(user_id: int):
    return list(db.categories.find({"user_id": user_id}, {"_id": 1, "name": 1}).sort("name", 1))

def get_category_count(user_id: int) -> int:
    return db.categories.count_documents({"user_id": user_id})

# ---------- Обещания ----------
def add_agreement(user_id: int, text: str, category_id: ObjectId = None):
    doc = {
        "user_id": user_id,
        "text": text,
        "category_id": category_id,
        "created_at": datetime.utcnow(),
        "is_done": False,
        "done_at": None
    }
    db.agreements.insert_one(doc)

def get_agreements(user_id: int, only_active: bool = False):
    filter = {"user_id": user_id}
    if only_active:
        filter["is_done"] = False
    pipeline = [
        {"$match": filter},
        {"$lookup": {
            "from": "categories",
            "localField": "category_id",
            "foreignField": "_id",
            "as": "category"
        }},
        {"$addFields": {
            "category_name": {"$arrayElemAt": ["$category.name", 0]}
        }},
        {"$sort": {"created_at": -1}}
    ]
    return list(db.agreements.aggregate(pipeline))

def get_agreement_by_id(agreement_id: str):
    try:
        oid = ObjectId(agreement_id)
    except:
        return None
    return db.agreements.find_one({"_id": oid})

def update_agreement(agreement_id: str, new_text: str):
    try:
        oid = ObjectId(agreement_id)
    except:
        return
    db.agreements.update_one({"_id": oid}, {"$set": {"text": new_text}})

def mark_done(agreement_id: str):
    try:
        oid = ObjectId(agreement_id)
    except:
        return
    db.agreements.update_one(
        {"_id": oid},
        {"$set": {"is_done": True, "done_at": datetime.utcnow()}}
    )

def delete_agreement(agreement_id: str):
    try:
        oid = ObjectId(agreement_id)
    except:
        return
    db.agreements.delete_one({"_id": oid})

# ---------- Ежедневные напоминания ----------
def set_reminder(user_id: int, time_str: str):
    db.reminders.update_one(
        {"user_id": user_id},
        {"$set": {"remind_time": time_str}},
        upsert=True
    )

def delete_reminder(user_id: int):
    db.reminders.delete_one({"user_id": user_id})

def get_reminder(user_id: int) -> str | None:
    doc = db.reminders.find_one({"user_id": user_id})
    return doc.get("remind_time") if doc else None

def get_users_with_reminders() -> list[tuple[int, str]]:
    return [(r["user_id"], r["remind_time"]) for r in db.reminders.find()]

# ---------- Ежедневная сводка ----------
def set_summary_time(user_id: int, time_str: str):
    db.daily_summary.update_one(
        {"user_id": user_id},
        {"$set": {"summary_time": time_str}},
        upsert=True
    )

def delete_summary_time(user_id: int):
    db.daily_summary.delete_one({"user_id": user_id})

def get_summary_time(user_id: int) -> str | None:
    doc = db.daily_summary.find_one({"user_id": user_id})
    return doc.get("summary_time") if doc else None

def get_users_with_summary() -> list[tuple[int, str]]:
    return [(s["user_id"], s["summary_time"]) for s in db.daily_summary.find()]

# ---------- Статистика ----------
def get_stats(user_id: int) -> dict:
    total = db.agreements.count_documents({"user_id": user_id})
    done = db.agreements.count_documents({"user_id": user_id, "is_done": True})
    percent = round(done / total * 100, 1) if total > 0 else 0.0

    # Streak (дни подряд с выполненными обещаниями)
    pipeline = [
        {"$match": {"user_id": user_id, "is_done": True}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}}},
        {"$sort": {"_id": -1}},
        {"$limit": 365}
    ]
    dates = [datetime.strptime(d["_id"], "%Y-%m-%d").date() for d in db.agreements.aggregate(pipeline)]
    streak = 0
    if dates:
        streak_end = dates[0]
        streak = 1
        expected = streak_end - timedelta(days=1)
        for d in dates[1:]:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
    return {"total": total, "done": done, "percent": percent, "streak": streak}

# ---------- Экспорт ----------
def get_agreements_export(user_id: int):
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$lookup": {
            "from": "categories",
            "localField": "category_id",
            "foreignField": "_id",
            "as": "category"
        }},
        {"$addFields": {
            "category_name": {"$arrayElemAt": ["$category.name", 0]}
        }},
        {"$sort": {"created_at": -1}}
    ]
    return list(db.agreements.aggregate(pipeline))

# ---------- Достижения ----------
ACHIEVEMENTS = {
    "novice": ("🏅 Новичок", "Создать 10 обещаний"),
    "discipline": ("🔥 Дисциплина", "Выполнять обещания 7 дней подряд"),
    "champion": ("👑 Чемпион", "Выполнить 100 обещаний"),
}

def get_user_achievements(user_id: int) -> list[str]:
    doc = db.achievements.find_one({"user_id": user_id})
    return doc.get("keys", []) if doc else []

def award_achievement(user_id: int, key: str) -> bool:
    result = db.achievements.update_one(
        {"user_id": user_id, "keys": {"$ne": key}},
        {"$addToSet": {"keys": key}},
        upsert=True
    )
    return result.modified_count > 0

def check_achievements(user_id: int) -> list[str]:
    newly_awarded = []
    total_created = db.agreements.count_documents({"user_id": user_id})
    total_done = db.agreements.count_documents({"user_id": user_id, "is_done": True})
    # streak уже считается в get_stats, но мы можем переиспользовать
    stats = get_stats(user_id)
    streak = stats["streak"]

    if total_created >= 10 and award_achievement(user_id, "novice"):
        newly_awarded.append("novice")
    if streak >= 7 and award_achievement(user_id, "discipline"):
        newly_awarded.append("discipline")
    if total_done >= 100 and award_achievement(user_id, "champion"):
        newly_awarded.append("champion")
    return newly_awarded

# ---------- Запланированные напоминания ----------
def count_scheduled_reminders(user_id: int) -> int:
    return db.scheduled_reminders.count_documents({"user_id": user_id})

def create_scheduled_reminder(user_id: int, agreement_id: ObjectId, remind_date: date, remind_time: str,
                              is_recurring: bool = False, recurring_day: int = None):
    doc = {
        "user_id": user_id,
        "agreement_id": agreement_id,
        "remind_date": remind_date.isoformat(),
        "remind_time": remind_time,
        "is_recurring": is_recurring,
        "recurring_day": recurring_day,
        "created_at": datetime.utcnow()
    }
    db.scheduled_reminders.insert_one(doc)

def get_pending_reminders_for_now(now_date: date, now_time: str) -> list[tuple]:
    results = []
    # Одноразовые на сегодня
    one_time = db.scheduled_reminders.find({
        "remind_date": now_date.isoformat(),
        "remind_time": now_time,
        "is_recurring": False
    })
    for r in one_time:
        agr = db.agreements.find_one({"_id": r["agreement_id"]})
        if agr:
            results.append((str(r["_id"]), r["user_id"], agr["text"]))
    # Повторяющиеся по дню недели
    weekday = now_date.weekday()
    recurring = db.scheduled_reminders.find({
        "is_recurring": True,
        "recurring_day": weekday,
        "remind_time": now_time
    })
    for r in recurring:
        agr = db.agreements.find_one({"_id": r["agreement_id"]})
        if agr:
            results.append((str(r["_id"]), r["user_id"], agr["text"]))
    return results

def delete_scheduled_reminder(reminder_id: str):
    try:
        oid = ObjectId(reminder_id)
    except:
        return
    db.scheduled_reminders.delete_one({"_id": oid})  