import os
import uuid
import random
from datetime import datetime, date, timedelta
from pymongo import MongoClient
from bson.objectid import ObjectId

MONGODB_URI = os.environ.get("MONGODB_URI")
client = MongoClient(MONGODB_URI)
db = client["promise_bot"]

# ---------- Питомцы ----------
PET_TYPES = {
    "cat": {
        "name": "Котёнок", "emoji": "🐱", "cost": 0, "premium": False,
        "mood_messages": {
            "happy": ["Мяу! Ты молодец, хозяин!", "Ура, меня покормили!", "Мур-мур, спасибо!"],
            "sad": ["Мяу... ты забыл про меня...", "Мне грустно без тебя...", "Покорми меня, пожалуйста!"],
            "danger": ["Я могу убежать, если ты не будешь выполнять обещания!", "Мяу! Моё настроение на нуле!"]
        }
    },
    "dog": {
        "name": "Щенок", "emoji": "🐶", "cost": 500, "premium": False,
        "mood_messages": {
            "happy": ["Гав! Ты лучший!", "Ура, гулять!", "Спасибо, хозяин!"],
            "sad": ["Гав... я скучаю...", "Ты меня не выгулял...", "Мне одиноко..."],
            "danger": ["Гав! Если ты не вернёшься, я убегу!", "Моё терпение на исходе!"]
        }
    },
    "dragon": {
        "name": "Дракончик", "emoji": "🐉", "cost": 0, "premium": True,
        "mood_messages": {
            "happy": ["Ррр! Ты великий воин!", "Моя чешуя сияет!", "Драконье спасибо!"],
            "sad": ["Ррр... я слабею...", "Мне нужна твоя сила...", "Дракон грустит..."],
            "danger": ["Ррр! Я могу улететь навсегда!", "Моя ярость растёт!"]
        }
    }
}

def get_pet(user_id: int):
    user = db.users.find_one({"user_id": user_id})
    if not user or "pet" not in user:
        pet = {"type": "cat", "name": "Барсик", "hunger": 100, "mood": 100, "level": 1, "xp": 0}
        db.users.update_one({"user_id": user_id}, {"$set": {"pet": pet}}, upsert=True)
        return pet
    return user["pet"]

def update_pet_stats(user_id: int, hunger_delta: int = 0, mood_delta: int = 0):
    pet = get_pet(user_id)
    pet["hunger"] = max(0, min(200, pet["hunger"] + hunger_delta))
    pet["mood"] = max(0, min(200, pet["mood"] + mood_delta))
    pet["xp"] += abs(hunger_delta) // 2
    if pet["xp"] >= 100:
        pet["level"] += 1
        pet["xp"] -= 100
    db.users.update_one({"user_id": user_id}, {"$set": {"pet": pet}})
    return pet

def get_pet_message(user_id: int) -> str | None:
    pet = get_pet(user_id)
    pet_type = pet["type"]
    if pet["mood"] >= 100:
        msg_list = PET_TYPES[pet_type]["mood_messages"]["happy"]
    elif pet["mood"] >= 30:
        msg_list = PET_TYPES[pet_type]["mood_messages"]["sad"]
    else:
        msg_list = PET_TYPES[pet_type]["mood_messages"]["danger"]
    return f"{PET_TYPES[pet_type]['emoji']} {random.choice(msg_list)}"

def change_pet(user_id: int, new_type: str, cost_xp: int = 0) -> bool:
    if new_type not in PET_TYPES:
        return False
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return False
    if cost_xp > 0:
        current_xp = user.get("xp", 0)
        if current_xp < cost_xp:
            return False
        db.users.update_one({"user_id": user_id}, {"$inc": {"xp": -cost_xp}})
    pet = {"type": new_type, "name": PET_TYPES[new_type]["name"], "hunger": 100, "mood": 100, "level": 1, "xp": 0}
    db.users.update_one({"user_id": user_id}, {"$set": {"pet": pet}})
    return True

# ---------- Магазин ----------
SHOP_ITEMS = [
    {"id": "badge_ninja", "name": "Ниндзя продуктивности", "cost": 500, "type": "badge", "emoji": "🥷"},
    {"id": "badge_master", "name": "Мастер дисциплины", "cost": 1000, "type": "badge", "emoji": "🏅"},
    {"id": "badge_legend", "name": "Легенда", "cost": 5000, "type": "badge", "emoji": "👑"},
    {"id": "pet_accessory_hat", "name": "Шляпа для питомца", "cost": 300, "type": "accessory", "emoji": "🎩"},
    {"id": "pet_accessory_glasses", "name": "Очки для питомца", "cost": 300, "type": "accessory", "emoji": "👓"},
]

def get_shop_items():
    return SHOP_ITEMS

def buy_item(user_id: int, item_id: str) -> tuple[bool, str]:
    item = next((i for i in SHOP_ITEMS if i["id"] == item_id), None)
    if not item:
        return False, "Товар не найден."
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return False, "Пользователь не найден."
    if user.get("xp", 0) < item["cost"]:
        return False, f"Недостаточно XP. Нужно {item['cost']}, у вас {user.get('xp', 0)}."
    inventory = user.get("inventory", [])
    if item_id in inventory:
        return False, "У вас уже есть этот предмет."
    db.users.update_one({"user_id": user_id}, {"$inc": {"xp": -item["cost"]}, "$addToSet": {"inventory": item_id}})
    return True, f"Вы купили {item['emoji']} {item['name']}!"

def get_inventory(user_id: int) -> list[str]:
    user = db.users.find_one({"user_id": user_id})
    return user.get("inventory", []) if user else []

# ---------- Пользователи ----------
def init_db():
    pass

def create_user(user_id: int, referrer_id: int = None):
    user = db.users.find_one({"user_id": user_id})
    if user:
        return
    ref_code = uuid.uuid4().hex[:8]
    new_user = {
        "user_id": user_id, "is_premium": False, "premium_until": None,
        "ref_code": ref_code, "referrer_id": referrer_id, "xp": 0,
        "freezes_available": 0, "pet": None, "inventory": []
    }
    db.users.insert_one(new_user)
    get_pet(user_id)  # сразу даём питомца
    if referrer_id:
        set_premium(user_id, True, days=3)
        referrer = db.users.find_one({"user_id": referrer_id})
        if referrer:
            current_until = referrer.get("premium_until")
            if current_until and current_until > datetime.utcnow():
                new_until = current_until + timedelta(days=7)
            else:
                new_until = datetime.utcnow() + timedelta(days=7)
            db.users.update_one({"user_id": referrer_id}, {"$set": {"is_premium": True, "premium_until": new_until}})

def is_premium(user_id: int) -> bool:
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return False
    if user.get("is_premium") and user.get("premium_until"):
        if user["premium_until"] > datetime.utcnow():
            return True
        else:
            db.users.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
            return False
    return user.get("is_premium", False)

def set_premium(user_id: int, status: bool, days: int = 0):
    if days > 0:
        premium_until = datetime.utcnow() + timedelta(days=days)
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"is_premium": True, "premium_until": premium_until, "freezes_available": 1}},
            upsert=True
        )
    else:
        db.users.update_one({"user_id": user_id}, {"$set": {"is_premium": status}}, upsert=True)

def add_xp(user_id: int, amount: int):
    db.users.update_one({"user_id": user_id}, {"$inc": {"xp": amount}})

def get_xp(user_id: int) -> int:
    user = db.users.find_one({"user_id": user_id})
    return user.get("xp", 0) if user else 0

def use_freeze(user_id: int) -> bool:
    user = db.users.find_one({"user_id": user_id})
    if not user or user.get("freezes_available", 0) <= 0:
        return False
    db.users.update_one({"user_id": user_id}, {"$inc": {"freezes_available": -1}})
    today = date.today()
    doc = {"user_id": user_id, "text": "❄️ Заморозка дня", "created_at": datetime.utcnow(),
           "is_done": True, "done_at": datetime.utcnow(), "is_freeze": True, "difficulty": 0}
    db.agreements.insert_one(doc)
    return True

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
def add_agreement(user_id: int, text: str, category_id: ObjectId = None, difficulty: int = 0):
    doc = {
        "user_id": user_id, "text": text, "category_id": category_id,
        "created_at": datetime.utcnow(), "is_done": False, "done_at": None,
        "difficulty": difficulty, "is_freeze": False, "photo_file_id": None
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

def mark_done(agreement_id: str, photo_file_id: str = None):
    try:
        oid = ObjectId(agreement_id)
    except:
        return
    update = {"is_done": True, "done_at": datetime.utcnow()}
    if photo_file_id:
        update["photo_file_id"] = photo_file_id
    db.agreements.update_one({"_id": oid}, {"$set": update})
    # Начисляем XP
    agreement = db.agreements.find_one({"_id": oid})
    if agreement:
        xp_map = {0: 10, 1: 25, 2: 50}
        diff = agreement.get("difficulty", 0)
        add_xp(agreement["user_id"], xp_map.get(diff, 10))

def delete_agreement(agreement_id: str):
    try:
        oid = ObjectId(agreement_id)
    except:
        return
    db.agreements.delete_one({"_id": oid})

# ---------- Лимит фото ----------
def count_photos_today(user_id: int) -> int:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.agreements.count_documents({
        "user_id": user_id, "is_done": True,
        "photo_file_id": {"$ne": None},
        "done_at": {"$gte": today_start}
    })

def can_attach_photo(user_id: int) -> bool:
    if is_premium(user_id):
        return True
    return count_photos_today(user_id) < 1

# ---------- Статистика по категориям ----------
def get_stats_by_category(user_id: int) -> list[dict]:
    categories = get_categories(user_id)
    result = []
    for cat in categories:
        cat_id = cat["_id"]
        total = db.agreements.count_documents({"user_id": user_id, "category_id": cat_id})
        done = db.agreements.count_documents({"user_id": user_id, "category_id": cat_id, "is_done": True})
        percent = round(done / total * 100, 1) if total > 0 else 0.0
        result.append({"name": cat["name"], "total": total, "done": done, "percent": percent})
    return result

# ---------- Челленджи ----------
def create_daily_challenge():
    today = date.today().isoformat()
    existing = db.challenges.find_one({"date": today})
    if existing:
        return existing["_id"]
    challenge = {
        "title": "Ежедневный челлендж",
        "description": "Выполни хотя бы одно обещание сегодня и не прерывай серию!",
        "date": today,
        "participants": [],
        "completed": [],
        "is_daily": True,
        "created_at": datetime.utcnow()
    }
    result = db.challenges.insert_one(challenge)
    return result.inserted_id

def get_active_challenges():
    today = date.today().isoformat()
    return list(db.challenges.find({"date": today}))

def join_challenge(user_id: int, challenge_id: str):
    try:
        oid = ObjectId(challenge_id)
    except:
        return False, "Неверный идентификатор челленджа."
    challenge = db.challenges.find_one({"_id": oid})
    if not challenge:
        return False, "Челлендж не найден."
    if user_id in challenge.get("participants", []):
        return False, "Вы уже участвуете в этом челлендже."
    db.challenges.update_one({"_id": oid}, {"$addToSet": {"participants": user_id}})
    return True, "Вы присоединились к челленджу!"

def check_challenge_completion(challenge_id: str):
    try:
        oid = ObjectId(challenge_id)
    except:
        return
    challenge = db.challenges.find_one({"_id": oid})
    if not challenge:
        return
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed = []
    failed = []
    for user_id in challenge.get("participants", []):
        done = db.agreements.count_documents({
            "user_id": user_id, "is_done": True,
            "done_at": {"$gte": today_start}
        })
        if done > 0:
            completed.append(user_id)
            db.challenges.update_one({"_id": oid}, {"$addToSet": {"completed": user_id}})
        else:
            failed.append(user_id)
    return {"completed": completed, "failed": failed, "title": challenge["title"]}

def get_all_challenges_stats():
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    return list(db.challenges.find({"date": {"$gte": week_ago}}).sort("date", -1))

# ---------- Рефералы ----------
def get_ref_code(user_id: int) -> str | None:
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return None
    ref_code = user.get("ref_code")
    if not ref_code:
        ref_code = uuid.uuid4().hex[:8]
        db.users.update_one({"user_id": user_id}, {"$set": {"ref_code": ref_code}})
    return ref_code

def get_user_by_ref_code(ref_code: str):
    return db.users.find_one({"ref_code": ref_code})

def get_referral_stats(user_id: int) -> dict:
    total = db.users.count_documents({"referrer_id": user_id})
    active = len([
        u for u in db.users.find({"referrer_id": user_id})
        if db.agreements.count_documents({"user_id": u["user_id"]}) > 0
    ])
    return {"total": total, "active": active}

# ---------- Напоминания ----------
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

# ---------- Сводки ----------
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
    one_time = db.scheduled_reminders.find({
        "remind_date": now_date.isoformat(),
        "remind_time": now_time,
        "is_recurring": False
    })
    for r in one_time:
        agr = db.agreements.find_one({"_id": r["agreement_id"]})
        if agr:
            results.append((str(r["_id"]), r["user_id"], agr["text"]))
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

# ---------- Админ-статистика ----------
def get_admin_stats() -> dict:
    total_users = db.users.count_documents({})
    total_agreements = db.agreements.count_documents({})
    premium_users = db.users.count_documents({"is_premium": True})
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    active_today = len(set(
        db.agreements.distinct("user_id", {"created_at": {"$gte": today_start}})
    ))
    total_referrals = db.users.count_documents({"referrer_id": {"$ne": None}})
    return {
        "total_users": total_users, "active_today": active_today,
        "premium_users": premium_users, "total_agreements": total_agreements,
        "total_referrals": total_referrals
    }