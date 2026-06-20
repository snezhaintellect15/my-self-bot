import asyncio
import io
import logging
import os
import re
import random
from datetime import datetime, timedelta, date, timezone
from threading import Thread

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, PreCheckoutQueryHandler
from telegram.helpers import escape_markdown

from database import (init_db, create_user, is_premium, set_premium,
                      add_agreement, get_agreements, get_agreement_by_id,
                      mark_done, delete_agreement, update_agreement,
                      create_category, get_categories, get_category_count, delete_category,
                      set_reminder, delete_reminder, get_reminder, get_users_with_reminders,
                      get_stats, get_agreements_export,
                      check_achievements, get_user_achievements, ACHIEVEMENTS,
                      set_summary_time, delete_summary_time, get_summary_time, get_users_with_summary,
                      count_scheduled_reminders, create_scheduled_reminder,
                      get_pending_reminders_for_now, delete_scheduled_reminder,
                      get_ref_code, get_user_by_ref_code, get_referral_stats,
                      get_admin_stats, add_xp, get_xp, use_freeze, get_freezes_count,
                      get_pet, update_pet_stats, get_pet_message, change_pet,
                      get_shop_items, buy_item, get_inventory,
                      get_coins, add_coins,
                      PET_TYPES, lose_level_if_inactive, get_pet_ascii_art,
                      create_daily_challenge, get_active_challenges, join_challenge,
                      check_challenge_completion, get_all_challenges_stats,
                      can_attach_photo, count_photos_today, get_stats_by_category,
                      save_feedback, get_recent_feedback, has_poll_today, save_poll_response,
                      db)
from bson.objectid import ObjectId
from fpdf import FPDF

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "MyPromiseTrackerBot")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
MSK_OFFSET = timedelta(hours=3)

app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

# ---------- Мотивационные сообщения ----------
MOTIVATIONAL_MESSAGES = {
    "daily_summary": [
        "🌟 Ты сегодня супер-звезда! Так держать!",
        "💪 Каждый выполненный шаг приближает тебя к цели!",
        "🎯 Ты на верном пути! Продолжай в том же духе!",
        "🔥 Сегодня ты настоящий воин продуктивности!",
        "⭐ Даже маленький шаг — это прогресс. Ты молодец!",
        "🌈 Твоя дисциплина вдохновляет!",
        "🏆 Ещё один день — ещё одна победа над прокрастинацией!",
        "💎 Качество твоих дел растёт с каждым днём!",
    ],
    "task_completed": [
        "✅ Отлично! Ещё один шаг к цели!",
        "🎉 Ура! Задача выполнена!",
        "💪 Сила воли прокачана!",
        "🏅 Ты на шаг ближе к новому достижению!",
        "🔥 Ещё одна задача покорена!",
        "⭐ Твоя продуктивность зашкаливает!",
        "🌈 Молодец! Так держать!",
        "🎯 Точное попадание в цель!",
    ],
    "streak_milestones": {
        3: "🎉 3 дня подряд! +20 монет!",
        7: "🔥 7 дней серии! +50 монет! 🎁",
        14: "💪 Две недели дисциплины! +100 монет! 🏆",
        21: "🌈 21 день! +150 монет! 🎯",
        30: "👑 МЕСЯЦ серии! +300 монет! ⭐",
        50: "🦁 50 дней подряд! +500 монет! 🔥",
        100: "🏆🏆🏆 100 ДНЕЙ! +1000 монет! 👑",
    },
    "morning_greetings": [
        "☀️ Доброе утро! Какой подвиг совершишь сегодня?",
        "🌅 Новый день — новые победы!",
        "⭐ Вставай и сияй!",
        "💪 Утро — время планировать дела!",
    ],
    "evening_encouragement": [
        "🌙 Отличный день! Отдыхай!",
        "💤 Завтра будет новый день!",
        "⭐ Не переживай, если что-то не успел(а)!",
        "📖 Каждый день — страница успеха!",
    ],
    "procrastination_alert": [
        "⚠️ Внимание! Есть невыполненные обещания!",
        "⏰ Начни с малого шага прямо сейчас!",
        "🎯 Лучше сделать плохо, чем не сделать совсем!",
        "💪 Просто сделай первый шаг!",
    ],
    "perfect_day": [
        "🏆 ИДЕАЛЬНЫЙ ДЕНЬ! Все обещания выполнены!",
        "👑 100% выполнение! Ты бог продуктивности!",
        "⭐ Сегодня ты показал(а) высший пилотаж!",
        "💎 Идеальный день в копилку успехов!",
    ],
    "coins_earned": {
        10: "🪙 +10 монет!",
        20: "💰 +20 монет!",
        50: "💎 Ого! +50 монет!",
        100: "🎉 ВАУ! +100 монет!",
    }
}

def get_motivation_message(category: str, **kwargs) -> str:
    if category in MOTIVATIONAL_MESSAGES:
        if isinstance(MOTIVATIONAL_MESSAGES[category], dict):
            key = kwargs.get('key')
            if key and key in MOTIVATIONAL_MESSAGES[category]:
                return MOTIVATIONAL_MESSAGES[category][key]
            return ""
        else:
            return random.choice(MOTIVATIONAL_MESSAGES[category])
    return ""

def check_streak_milestone(streak: int) -> str:
    milestones = MOTIVATIONAL_MESSAGES["streak_milestones"]
    if streak in milestones:
        return milestones[streak]
    return ""

def get_coins_message(amount: int) -> str:
    for threshold, message in MOTIVATIONAL_MESSAGES["coins_earned"].items():
        if amount >= threshold:
            return message
    return f"🪙 +{amount} монет!"

# ---------- NLP парсер ----------
DAYS_RU = {
    'понедельник': 0, 'пн': 0,
    'вторник': 1, 'вт': 1,
    'среда': 2, 'ср': 2,
    'четверг': 3, 'чт': 3,
    'пятница': 4, 'пт': 4,
    'суббота': 5, 'сб': 5,
    'воскресенье': 6, 'вс': 6,
}

MONTHS_RU = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
    'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
    'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
}

def parse_natural_language(text: str):
    text_lower = text.lower()
    today = date.today()
    now = datetime.now(timezone.utc) + MSK_OFFSET
    remind_date = today
    remind_time = "09:00"
    task_text = text
    is_recurring = False
    recurring_day = None

    # --- Относительное время ("через X минут/часов/дней") ---
    relative_match = re.search(r'через\s+(\d+)\s+(минут[уы]?|час[а]?[ов]?|день|дня|дней)', text_lower)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        if 'минут' in unit:
            delta = timedelta(minutes=amount)
        elif 'час' in unit:
            delta = timedelta(hours=amount)
        elif 'день' in unit or 'дня' in unit or 'дней' in unit:
            delta = timedelta(days=amount)
        else:
            delta = timedelta(minutes=amount)
        target_dt = now + delta
        remind_date = target_dt.date()
        remind_time = target_dt.strftime("%H:%M")
        task_text = re.sub(r'через\s+\d+\s+(минут[уы]?|час[а]?[ов]?|день|дня|дней)\s*,?\s*', '', text, flags=re.IGNORECASE)
        markers = ['напомни', 'мне', 'что', 'нужно', 'сделать', 'купить', 'позвонить', 'напомнить']
        for marker in markers:
            task_text = re.sub(r'^' + marker + r'\s*', '', task_text, flags=re.IGNORECASE)
        task_text = re.sub(r'\s+', ' ', task_text).strip()
        if not task_text:
            task_text = "Напоминание"
        return remind_date, remind_time, task_text, False, None

    # --- Абсолютное время ---
    time_match = None

    # 1) "HH:MM"
    match = re.search(r'(\d{1,2}):(\d{2})', text_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        remind_time = f"{hour:02d}:{minute:02d}"
        time_match = True

    # 2) "в X часов Y минут" или "в X часов"
    if not time_match:
        match = re.search(r'в (\d{1,2})\s*часов?\s*(?:(\d{1,2})\s*минут?)?', text_lower)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) else 0
            remind_time = f"{hour:02d}:{minute:02d}"
            time_match = True

    # 3) "X утра"
    if not time_match:
        match = re.search(r'(\d{1,2})\s*утра', text_lower)
        if match:
            hour = int(match.group(1))
            if hour == 12:
                hour = 0
            minute = 0
            remind_time = f"{hour:02d}:{minute:02d}"
            time_match = True

    # 4) "X дня"
    if not time_match:
        match = re.search(r'(\d{1,2})\s*дня', text_lower)
        if match:
            hour = int(match.group(1))
            if hour < 12:
                hour += 12
            minute = 0
            remind_time = f"{hour:02d}:{minute:02d}"
            time_match = True

    # 5) "X вечера"
    if not time_match:
        match = re.search(r'(\d{1,2})\s*вечера', text_lower)
        if match:
            hour = int(match.group(1))
            if hour < 12:
                hour += 12
            minute = 0
            remind_time = f"{hour:02d}:{minute:02d}"
            time_match = True

    # --- Дни недели и повторения ---
    for day_name, day_num in DAYS_RU.items():
        if day_name in text_lower:
            if re.search(r'(каждый|каждую)\s+' + day_name, text_lower):
                is_recurring = True
                recurring_day = day_num
                task_text = re.sub(r'(каждый|каждую)\s+' + day_name + r'\s*', '', text, flags=re.IGNORECASE)

    # --- Относительные даты ---
    if 'послезавтра' in text_lower:
        remind_date = today + timedelta(days=2)
        task_text = re.sub(r'послезавтра\s*', '', text, flags=re.IGNORECASE)
    elif 'завтра' in text_lower:
        remind_date = today + timedelta(days=1)
        task_text = re.sub(r'завтра\s*', '', text, flags=re.IGNORECASE)
    elif 'сегодня' in text_lower:
        remind_date = today
        task_text = re.sub(r'сегодня\s*', '', text, flags=re.IGNORECASE)

    # --- Абсолютные даты ---
    date_match = re.search(r'(\d{1,2})\s+(\w+)', text_lower)
    if date_match and not is_recurring:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        if month_name in MONTHS_RU:
            month = MONTHS_RU[month_name]
            year = today.year
            try:
                remind_date = date(year, month, day)
                if remind_date < today:
                    remind_date = date(year + 1, month, day)
                task_text = re.sub(r'\d{1,2}\s+\w+\s*', '', text, flags=re.IGNORECASE)
            except:
                pass

    # --- Если дата не задана, пробуем понять по дням недели ---
    if not remind_date and not is_recurring:
        for day_name, day_num in DAYS_RU.items():
            if day_name in text_lower:
                days_ahead = day_num - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                remind_date = today + timedelta(days=days_ahead)
                task_text = re.sub(day_name + r'\s*', '', text, flags=re.IGNORECASE)
                break

    # --- Очистка ---
    markers = ['напомни', 'сделать', 'купить', 'позвонить', 'напомнить', 'в ']
    for marker in markers:
        task_text = re.sub(r'^' + marker + r'\s*', '', task_text, flags=re.IGNORECASE)

    task_text = re.sub(r'\s+', ' ', task_text).strip()
    task_text = re.sub(r'\d{1,2}:\d{2}', '', task_text)
    task_text = re.sub(r'\d{1,2}\s*(часов|утра|дня|вечера)', '', task_text)
    task_text = re.sub(r'\s+', ' ', task_text).strip()

    if not task_text:
        task_text = "Напоминание"

    return remind_date, remind_time, task_text, is_recurring, recurring_day

# ---------- Вспомогательные функции ----------
def split_message(text: str, max_len: int = 4000):
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.split('\n')
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 <= max_len:
            current_part += line + '\n'
        else:
            parts.append(current_part)
            current_part = line + '\n'
    if current_part:
        parts.append(current_part)
    return parts

def build_list_message(user_id: int, only_active: bool = False, only_done: bool = False):
    agreements = get_agreements(user_id, only_active=only_active, only_done=only_done, limit=100)
    if not agreements:
        if only_active:
            return "У тебя пока нет активных обещаний.", None
        elif only_done:
            return "Нет выполненных обещаний.", None
        else:
            return "У тебя пока нет ни одного обещания.", None

    diff_icons = {0: "🌱", 1: "⚡️", 2: "🔥"}
    groups = {}
    no_cat = []
    for agr in agreements:
        if agr.get("is_freeze"):
            continue
        safe_text = escape_markdown(agr["text"], version=2)
        is_done = agr["is_done"]
        cat_name = agr.get("category_name")
        agr_id = str(agr["_id"])
        diff = agr.get("difficulty", 0)
        prefix = diff_icons.get(diff, "")
        photo_mark = " 📷" if agr.get("photo_file_id") else ""
        display_text = f"{prefix} {safe_text}{photo_mark}"
        if cat_name is None:
            no_cat.append((agr_id, display_text, is_done))
        else:
            groups.setdefault(cat_name, []).append((agr_id, display_text, is_done))

    if only_active:
        response = "📝 **Активные обещания:**\n\n"
    elif only_done:
        response = "📜 **История выполненных:**\n\n"
    else:
        response = "📋 **Все обещания:**\n\n"

    keyboard = []

    if no_cat:
        response += "⚪️ *Без категории:*\n"
        for agr_id, text, is_done in no_cat:
            status = "⬜" if not is_done else "✅"
            response += f"  {status} {text}\n"
            if not is_done and only_active:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып.", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Ред.", callback_data=f"edit_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                ])

    for cat, items in groups.items():
        safe_cat = escape_markdown(cat, version=2)
        response += f"\n📂 *{safe_cat}:*\n"
        for agr_id, text, is_done in items:
            status = "⬜" if not is_done else "✅"
            response += f"  {status} {text}\n"
            if not is_done and only_active:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып.", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Ред.", callback_data=f"edit_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                ])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return response, reply_markup

async def build_daily_summary(user_id: int) -> str:
    today = date.today()
    done_today = db.agreements.count_documents({
        "user_id": user_id,
        "is_done": True,
        "done_at": {"$gte": datetime(today.year, today.month, today.day)}
    })
    total = db.agreements.count_documents({"user_id": user_id})
    done_total = db.agreements.count_documents({"user_id": user_id, "is_done": True})
    percent = round(done_total / total * 100, 1) if total > 0 else 0.0
    active = db.agreements.count_documents({"user_id": user_id, "is_done": False})

    message = "📋 **Ежедневная сводка**\n\n"

    if done_today > 0:
        message += f"✅ Сегодня выполнено: {done_today} обещаний\n"
    else:
        message += "😴 Сегодня пока нет выполненных обещаний\n"

    message += f"📊 Активных обещаний: {active}\n"
    message += f"🏆 Общий прогресс: {done_total}/{total} ({percent}%)\n\n"

    if percent == 100 and total > 0:
        message += get_motivation_message("perfect_day") + "\n\n"
    elif active == 0 and total > 0:
        message += "🎉 Все обещания выполнены! Ты герой!\n\n"
    elif active > 0 and done_today == 0:
        message += get_motivation_message("procrastination_alert") + "\n\n"
    else:
        message += get_motivation_message("daily_summary") + "\n"

    tips = [
        "💡 Совет: Начни с самой маленькой задачи!",
        "🎯 Совет: Разбей большие задачи на маленькие шаги.",
        "⏰ Совет: Используй технику Pomodoro!",
        "📝 Совет: Записывай даже маленькие победы!",
        "🌟 Совет: Похвали себя за каждое выполненное обещание!",
    ]
    message += "\n" + random.choice(tips)

    return message

# ---------- Команды бота ----------
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Операция отменена.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📝 Активные"), KeyboardButton("📜 История")],
        [KeyboardButton("📂 Категории")],
        [KeyboardButton("⏰ Напоминания"), KeyboardButton("📋 Сводка")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⭐ Премиум")],
        [KeyboardButton("📤 Экспорт"), KeyboardButton("🏆 Достижения")],
        [KeyboardButton("👥 Рефералы"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("🐾 Питомец"), KeyboardButton("🛒 Магазин")],
        [KeyboardButton("🛡 Заморозка"), KeyboardButton("🌍 Челленджи")],
        [KeyboardButton("🪙 Баланс"), KeyboardButton("🤖 Напомнить")],
        [KeyboardButton("💬 Фидбек"), KeyboardButton("❌ Отмена")],
        [KeyboardButton("📢 Наш канал")]
    ]
    if is_premium(update.effective_user.id):
        keyboard.append([KeyboardButton("👑 VIP-помощь")])

    # Если это колбэк — используем сообщение из колбэка
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "Выбери действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    elif update.message:
        await update.message.reply_text(
            "Выбери действие:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    args = context.args

    referrer_id = None
    if args:
        ref_code = args[0]
        referrer = get_user_by_ref_code(ref_code)
        if referrer:
            referrer_id = referrer["user_id"]

    create_user(user_id, referrer_id)
    db.users.update_one({"user_id": user_id}, {"$set": {"username": username}})

    xp = get_xp(user_id)
    level = xp // 100 + 1
    coins = get_coins(user_id)

    welcome_text = (
        f"👋 Привет, {username or 'друг'}! Я твой персональный трекер обещаний.\n\n"
        "✨ Что я умею:\n"
        "• Записывать обещания и цели\n"
        "• Понимать естественный язык (просто пиши как человеку)\n"
        "• Дарить питомца, который растёт с тобой\n"
        "• Отслеживать прогресс и выдавать достижения\n\n"
        f"📊 Твой уровень: {level} (XP: {xp})\n"
        f"🪙 Монеты: {coins}\n\n"
        "📌 Главное меню: /menu\n"
        "👥 Пригласи друга: /invite\n\n"
        "🤖 Попробуй умное напоминание:\n"
        "/remindme Напомни завтра в 10 утра купить хлеб\n\n"
        "📢 Подпишись на наш канал «Время действовать!»: https://t.me/PromiseAction\n\n"
        "💬 Если есть идеи или проблемы — напиши /feedback"
    )
    await update.message.reply_text(welcome_text)

    if referrer_id:
        await update.message.reply_text("🎁 Вы перешли по реферальной ссылке! Вам начислено 3 дня премиума.")
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text="🎉 По вашей реферальной ссылке зарегистрировался новый пользователь! Вы получили 7 дней премиума."
            )
        except:
            pass

    if ADMIN_ID:
        user_count = db.users.count_documents({})
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🆕 Новый пользователь!\n\n"
                     f"👤 @{username}\n"
                     f"🆔 ID: {user_id}\n"
                     f"📊 Всего пользователей: {user_count}\n"
                     f"👥 Реферал: {'да' if referrer_id else 'нет'}"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить админа о новом пользователе: {e}")

    await menu(update, context)

async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_code = get_ref_code(user_id)
    if not ref_code:
        await update.message.reply_text("Не удалось сгенерировать реферальную ссылку.")
        return

    ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    stats = get_referral_stats(user_id)
    message = (
        "👥 **Реферальная программа**\n\n"
        f"Ваша ссылка:\n`{ref_link}`\n\n"
        "**Как получить премиум БЕСПЛАТНО:**\n"
        "• Пригласи 1 друга → 7 дней премиума\n"
        "• Пригласи 5 друзей → 1 месяц премиума\n"
        "• Пригласи 20 друзей → ПРЕМИУМ НАВСЕГДА!\n\n"
        f"📊 **Ваша статистика:**\n"
        f"• Приглашено всего: {stats['total']}\n"
        f"• Активных: {stats['active']}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 **Справка по командам**\n\n"
        "**Основные:**\n"
        "/start — Запустить бота\n"
        "/menu — Главное меню\n"
        "/add — Быстро добавить обещание\n"
        "/list — Активные обещания\n"
        "/history — Выполненные обещания\n\n"
        "**Статистика:**\n"
        "/stats — Твоя статистика\n"
        "/achievements — Достижения\n"
        "/export — Экспорт данных\n\n"
        "**Напоминания:**\n"
        "/remindme — Умное напоминание (понимает язык!)\n"
        "/remind ЧЧ:ММ — Ежедневное напоминание\n"
        "/setsummary ЧЧ:ММ — Время сводки\n\n"
        "**Игровые:**\n"
        "/pet — Питомец\n"
        "/shop — Магазин\n"
        "/challenges — Челленджи\n"
        "/balance — Баланс монет\n\n"
        "**Другое:**\n"
        "/invite — Реферальная ссылка\n"
        "/feedback — Написать идею/проблему\n"
        "/premium — Премиум-доступ\n"
        "/cancel — Отменить операцию\n\n"
        "📢 Наш канал: https://t.me/PromiseAction\n"
    )
    if is_premium(update.effective_user.id):
        help_text += "\n👑 **Премиум:**\n/viphelp — Приоритетная поддержка"
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def vip_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("❌ Эта команда доступна только премиум-пользователям.")
        return

    if not context.args:
        await update.message.reply_text(
            "👑 **VIP-поддержка**\n\n"
            "Опишите вашу проблему или вопрос после команды /viphelp.\n"
            "Пример: `/viphelp Не могу сменить питомца`\n\n"
            "Ваше сообщение будет помечено как приоритетное и передано разработчику."
        )
        return

    vip_text = " ".join(context.args)
    username = update.effective_user.username or "без юзернейма"
    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👑 VIP-запрос (премиум)\n\nОт: @{username}\nID: {user_id}\nТекст: {vip_text}"
            )
            await update.message.reply_text(
                "✅ Ваше сообщение отправлено разработчику с высоким приоритетом. "
                "Ожидайте ответа в ближайшее время."
            )
        except Exception as e:
            logging.error(f"Ошибка VIP-уведомления: {e}")
            await update.message.reply_text("❌ Произошла ошибка, попробуйте позже.")
    else:
        await update.message.reply_text("❌ Администратор пока не настроен.")

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "без юзернейма"

    if not context.args:
        await update.message.reply_text(
            "💬 **Поделись идеей или проблемой**\n\n"
            "Напиши /feedback и свой текст\n"
            "Пример: `/feedback Хочу тёмную тему!`\n\n"
            "Лучшие идеи получат 🎁 100 монет!\n"
            "Спасибо, что помогаешь улучшать бота! 🙏",
            parse_mode="Markdown"
        )
        return

    feedback_text = " ".join(context.args)
    save_feedback(user_id, username, feedback_text)
    add_coins(user_id, 10)

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📝 Новый фидбек!\n\nОт: @{username}\nID: {user_id}\nТекст: {feedback_text}"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить админа о фидбеке: {e}")

    await update.message.reply_text(
        "🙏 Спасибо за обратную связь! Я передал её разработчику.\n"
        "🎁 За полезные идеи начисляем +10 монет!"
    )

async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши текст после /add. Пример: `/add Прочитать книгу`")
        return
    text = " ".join(context.args)
    context.user_data['pending_agreement_text'] = text
    keyboard = [
        [InlineKeyboardButton("🌱 Легко", callback_data="diff_0"),
         InlineKeyboardButton("⚡️ Средне", callback_data="diff_1"),
         InlineKeyboardButton("🔥 Хардкор", callback_data="diff_2")]
    ]
    await update.message.reply_text("Выбери сложность обещания:", reply_markup=InlineKeyboardMarkup(keyboard))

async def difficulty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("diff_"):
        diff = int(data.split("_")[1])
        user_id = query.from_user.id
        text = context.user_data.get('pending_agreement_text')
        if not text:
            await query.edit_message_text("❌ Ошибка: текст обещания не найден. Попробуйте снова.")
            return
        # Сохраняем текст и сложность в контексте
        context.user_data['pending_agreement_text'] = text
        context.user_data['pending_agreement_diff'] = diff
        # Показываем список категорий
        cats = get_categories(user_id)
        keyboard = []
        for cat in cats:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"addcat_{str(cat['_id'])}")])
        keyboard.append([InlineKeyboardButton("Без категории", callback_data="addcat_none")])
        keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="cancel_add")])
        await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_list_message(user_id, only_active=True)
    for part in split_message(text):
        await update.message.reply_text(part, parse_mode="Markdown", reply_markup=markup if part == text else None)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, _ = build_list_message(user_id, only_done=True)
    for part in split_message(text):
        await update.message.reply_text(part, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_stats(user_id)
    xp = get_xp(user_id)
    coins = get_coins(user_id)
    level = xp // 100 + 1
    message = (
        "📊 **Твоя статистика:**\n\n"
        f"• Всего обещаний: {stats['total']}\n"
        f"• Выполнено: {stats['done']} ({stats['percent']}%)\n"
        f"• Дней подряд: {stats['streak']}\n"
        f"• Уровень: {level} (XP: {xp})\n"
        f"• Монеты: {coins} 🪙\n\n"
    )
    cat_stats = get_stats_by_category(user_id)
    if cat_stats:
        message += "📂 **По категориям:**\n"
        for cat in cat_stats:
            safe_cat_name = escape_markdown(cat['name'], version=2)
            message += f"  {safe_cat_name}: {cat['done']}/{cat['total']} ({cat['percent']}%)\n"

    if stats['streak'] >= 30:
        message += "\n🔥 Легендарная серия! Ты невероятен!"
    elif stats['streak'] >= 7:
        message += "\n🌟 Отличная серия! Продолжай в том же духе."

    achieved = get_user_achievements(user_id)
    if achieved:
        message += "\n\n🏆 **Твои достижения:**\n"
        for key in achieved:
            if key in ACHIEVEMENTS:
                name, desc = ACHIEVEMENTS[key]
                message += f"  {name} — {desc}\n"

    for part in split_message(message):
        await update.message.reply_text(part, parse_mode="Markdown")

async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    achieved = get_user_achievements(user_id)
    message = "🏆 **Доска достижений**\n\n"
    for key, (name, desc) in ACHIEVEMENTS.items():
        status = "✅" if key in achieved else "⬜"
        message += f"{status} {name}: {desc}\n"
    if not achieved:
        message += "\nПока нет ни одного достижения. Начни с создания 10 обещаний!"
    await update.message.reply_text(message, parse_mode="Markdown")

def generate_pdf(user_id: int, stats: dict, cat_stats: list, agreements: list):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    try:
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
    except:
        pdf.set_font("Helvetica", size=12)

    # Заголовок
    pdf.set_font_size(18)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 12, "Отчёт Promise Tracker", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font_size(10)
    pdf.cell(0, 8, f"Создан: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    # Общая статистика
    pdf.set_font_size(14)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 10, "Общая статистика", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.set_font_size(12)
    pdf.cell(0, 8, f"Всего обещаний: {stats['total']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Выполнено: {stats['done']} ({stats['percent']}%)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Дней подряд: {stats['streak']}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # По категориям
    if cat_stats:
        pdf.set_font_size(14)
        pdf.set_fill_color(230, 240, 255)
        pdf.cell(0, 10, "По категориям", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.set_font_size(12)
        for cat in cat_stats:
            pdf.cell(0, 8, f"{cat['name']}: {cat['done']}/{cat['total']} ({cat['percent']}%)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Разделяем обещания
    done_agreements = [a for a in agreements if a.get("is_done")]
    active_agreements = [a for a in agreements if not a.get("is_done")]

    def print_agreement_list(title, agreements_list, header_color):
        if not agreements_list:
            return
        pdf.set_font_size(14)
        pdf.set_fill_color(*header_color)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font_size(10)
        # Шапка таблицы
        pdf.set_fill_color(245, 245, 245)
        col_widths = [22, 95, 40, 40, 40]
        pdf.cell(col_widths[0], 7, "Статус", border=1, fill=True)
        pdf.cell(col_widths[1], 7, "Текст", border=1, fill=True)
        pdf.cell(col_widths[2], 7, "Создано", border=1, fill=True)
        pdf.cell(col_widths[3], 7, "Выполнено", border=1, fill=True)
        pdf.cell(col_widths[4], 7, "Категория", border=1, fill=True)
        pdf.ln()
        for agr in agreements_list[:100]:
            status = "[V]" if agr.get("is_done") else "[ ]"
            text = agr["text"][:50] + ("..." if len(agr["text"]) > 50 else "")
            created = agr["created_at"].strftime("%d.%m.%y") if isinstance(agr.get("created_at"), datetime) else str(agr.get("created_at", ""))
            done_date = ""
            if agr.get("is_done") and agr.get("done_at"):
                done_date = agr["done_at"].strftime("%d.%m.%y") if isinstance(agr["done_at"], datetime) else str(agr["done_at"])
            cat = agr.get("category_name") or "-"
            pdf.cell(col_widths[0], 7, status, border=1)
            pdf.cell(col_widths[1], 7, text, border=1)
            pdf.cell(col_widths[2], 7, created, border=1)
            pdf.cell(col_widths[3], 7, done_date, border=1)
            pdf.cell(col_widths[4], 7, cat, border=1)
            pdf.ln()
        pdf.ln(4)

    # Выводим выполненные (зелёный) и активные (оранжевый)
    print_agreement_list("[V] Выполненные обещания", done_agreements, (0, 128, 0))
    print_agreement_list("[ ] Активные обещания", active_agreements, (200, 80, 0))

    # --- График продуктивности за 7 дней ---
    try:
        today = date.today()
        days = []
        counts = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cnt = db.agreements.count_documents({
                "user_id": user_id,
                "is_done": True,
                "done_at": {
                    "$gte": datetime(d.year, d.month, d.day),
                    "$lt": datetime(d.year, d.month, d.day) + timedelta(days=1)
                }
            })
            days.append(d.strftime("%d.%m"))
            counts.append(cnt)

        pdf.add_page()
        pdf.set_font_size(16)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, "Продуктивность за 7 дней", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        max_count = max(counts) if counts else 1
        bar_width = 22
        chart_x = 35
        chart_y = pdf.get_y() + 10
        max_bar_height = 70
        pdf.set_fill_color(100, 180, 255)
        pdf.set_draw_color(0, 0, 0)
        for i, cnt in enumerate(counts):
            h = (cnt / max_count) * max_bar_height if max_count > 0 else 0
            x = chart_x + i * (bar_width + 10)
            pdf.rect(x, chart_y + max_bar_height - h, bar_width, h, style="DF")
            pdf.set_xy(x, chart_y + max_bar_height + 2)
            pdf.set_font_size(8)
            pdf.cell(bar_width, 5, days[i], align="C")
            pdf.set_xy(x, chart_y + max_bar_height - h - 7)
            pdf.cell(bar_width, 5, str(cnt), align="C")
        pdf.ln(max_bar_height + 15)
    except Exception as e:
        logging.error(f"Не удалось построить график: {e}")

    return pdf.output()

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_agreements_export(user_id)
    if not data:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    stats = get_stats(user_id)

    text = "📤 **Экспорт обещаний**\n\n"
    for agr in data[:30]:
        status = "✅" if agr["is_done"] else "⬜"
        cat_str = f"[{agr.get('category_name', '')}] " if agr.get("category_name") else ""
        created_dt = agr["created_at"]
        created_formatted = created_dt.strftime("%Y-%m-%d %H:%M") if isinstance(created_dt, datetime) else str(created_dt)
        safe_text = escape_markdown(agr['text'], version=2)
        text += f"{status} {cat_str}{safe_text} ({created_formatted})\n"

    text += f"\nВсего записей: {len(data)}\nВыполнено: {stats['done']} из {stats['total']} ({stats['percent']}%)"

    for part in split_message(text):
        await update.message.reply_text(part, parse_mode="Markdown")

    if is_premium(user_id):
        cat_stats = get_stats_by_category(user_id)
        try:
            pdf_bytes = generate_pdf(user_id, stats, cat_stats, data)
            if not pdf_bytes or len(pdf_bytes) == 0:
                raise ValueError("Сгенерированный PDF пуст")
            pdf_file = io.BytesIO(pdf_bytes)
            pdf_file.name = "promise_tracker_report.pdf"
            await update.message.reply_document(
                document=pdf_file,
                caption="📎 Ваш PDF-отчёт"
            )
        except Exception as e:
            logging.error(f"Ошибка генерации PDF: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Не удалось создать PDF: {e}")

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    status_text = "активен ✅" if premium else "неактивен ❌"
    freezes_count = get_freezes_count(user_id) if premium else 0

    yoo_money = os.environ.get("DONATION_YOOMONEY", "")
    card_number = os.environ.get("DONATION_CARD", "")

    donation_message = ""
    if yoo_money or card_number:
        donation_message = (
            "\n☕ **Поддержать донатом:**\n"
            "💰 Цены в рублях:\n"
            "• 30 дней — 200 ₽\n"
            "• 90 дней — 450 ₽\n"
            "• Навсегда — 2000 ₽\n\n"
            "Реквизиты для перевода:\n"
        )
        if yoo_money:
            donation_message += f"💳 ЮMoney: {yoo_money}\n"
        if card_number:
            donation_message += f"🏦 Т-Банк: {card_number}\n"
        donation_message += "\nПосле оплаты напишите /feedback с подтверждением."
    else:
        donation_message = "\n☕ **Поддержать проект:**\nИспользуйте команду /feedback, чтобы связаться с разработчиком.\n"

    message = (
        f"⭐ **Премиум-доступ**\n\n"
        f"Твой статус: {status_text}\n\n"
        f"**Что даёт премиум:**\n"
        f"• Безлимитные напоминания\n"
        f"• Экспорт в PDF с графиком продуктивности\n"
        f"• Безлимитные фото-подтверждения\n"
        f"• 3 заморозки дня (сохраняют серию, осталось: {freezes_count})\n"
        f"• Эксклюзивный питомец «Феникс»\n"
        f"• Приоритетная поддержка (/viphelp)\n\n"
        f"💎 **Цены:**\n"
        f"• 30 дней — 50 Telegram Stars\n"
        f"• 90 дней — 125 Stars (скидка 15%)\n"
        f"• Навсегда — 500 Stars\n\n"
        f"👥 **Получить БЕСПЛАТНО:**\n"
        f"Пригласи друга по ссылке /invite\n"
        f"{donation_message}"
    )

    keyboard = [
        [InlineKeyboardButton("⭐ 30 дней (50 Stars)", callback_data="premium_30")],
        [InlineKeyboardButton("🔥 90 дней (125 Stars)", callback_data="premium_90")],
        [InlineKeyboardButton("👑 Навсегда (500 Stars)", callback_data="premium_forever")],
    ]
    if not (yoo_money or card_number):
        keyboard.append([InlineKeyboardButton("☕ Поддержать донатом", callback_data="donate_info")])

    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload

    days = 30
    if payload == "premium_30":
        days = 30
    elif payload == "premium_90":
        days = 90
    elif payload == "premium_forever":
        days = 365 * 10
    else:
        return

    set_premium(user_id, True, days=days)

    await update.message.reply_text(
        f"🎉 **Поздравляем! Премиум-доступ активирован на {days if days < 3650 else 'все время'} дней!**\n\n"
        f"Теперь тебе доступны все премиум-функции.\n"
        f"Спасибо за поддержку проекта! 🙏",
        parse_mode="Markdown"
    )

async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cats = get_categories(user_id)
    text = "📂 **Твои категории:**\n"
    if not cats:
        text += "Пока нет ни одной."
    else:
        for i, cat in enumerate(cats, 1):
            safe_name = escape_markdown(cat['name'], version=2)
            text += f"  {i}. {safe_name}\n"
    text += "\nВыбери действие:"
    keyboard = [
        [InlineKeyboardButton("➕ Создать категорию", callback_data="cat_create")],
    ]
    if cats:
        keyboard.append([InlineKeyboardButton("🗑 Удалить категорию", callback_data="cat_delete_menu")])
    keyboard.append([InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")])

    # Если это колбэк (update.callback_query существует), редактируем сообщение
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_reminder(user_id)
        if current:
            await update.message.reply_text(f"Сейчас ежедневное напоминание на {current}. /remind off — отключить")
        else:
            await update.message.reply_text("Ежедневное напоминание не установлено. /remind 18:00")
        return
    arg = context.args[0].strip().lower()
    if arg == "off":
        delete_reminder(user_id)
        await update.message.reply_text("🔕 Ежедневное напоминание отключено.")
        return
    try:
        datetime.strptime(arg, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Используй ЧЧ:ММ, например 18:00")
        return
    set_reminder(user_id, arg)
    await update.message.reply_text(f"⏰ Ежедневное напоминание установлено на {arg}")

async def smart_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "🤖 **Умное напоминание**\n\n"
            "Просто напишите, что и когда нужно сделать!\n\n"
            "📌 **Примеры:**\n"
            "• `Напомни завтра в 10 утра купить хлеб`\n"
            "• `Каждый понедельник в 9:00 йога`\n"
            "• `Сделать отчет сегодня в 18:00`\n"
            "• `25 декабря в 12:00 поздравить маму`\n\n"
            "💡 Бот сам распознает дату, время и задачу!",
            parse_mode="Markdown"
        )
        return

    full_text = " ".join(context.args)
    remind_date, remind_time, task_text, is_recurring, recurring_day = parse_natural_language(full_text)

    if not is_premium(user_id) and count_scheduled_reminders(user_id) >= 1 and not is_recurring:
        await update.message.reply_text(
            "⚠️ Лимит бесплатных напоминаний (1) исчерпан.\n"
            "💡 Используйте повторяющиеся напоминания - они бесплатны!\n"
            "🌟 Или приобретите премиум /premium"
        )
        return

    add_agreement(user_id, task_text, difficulty=0)
    agreements = get_agreements(user_id, only_active=True)
    if not agreements:
        await update.message.reply_text("❌ Ошибка при создании обещания")
        return

    last_agr = agreements[0]
    agr_id = last_agr["_id"]

    safe_task = escape_markdown(task_text, version=2)
    if is_recurring and recurring_day is not None:
        days_ahead = recurring_day - remind_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_date = remind_date + timedelta(days=days_ahead)

        create_scheduled_reminder(user_id, agr_id, next_date, remind_time,
                                  is_recurring=True, recurring_day=recurring_day)

        day_name = [k for k, v in DAYS_RU.items() if v == recurring_day][0]
        await update.message.reply_text(
            f"✅ **Напоминание создано!**\n\n"
            f"📝 Задача: {safe_task}\n"
            f"🔄 Повтор: каждый {day_name.capitalize()} в {remind_time}\n"
            f"⏰ Первое напоминание: {next_date.strftime('%d.%m.%Y')}",
            parse_mode="Markdown"
        )
    else:
        create_scheduled_reminder(user_id, agr_id, remind_date, remind_time)
        await update.message.reply_text(
            f"✅ **Напоминание создано!**\n\n"
            f"📝 Задача: {safe_task}\n"
            f"📅 Дата: {remind_date.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {remind_time}",
            parse_mode="Markdown"
        )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(await build_daily_summary(user_id), parse_mode="Markdown")

async def set_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_summary_time(user_id)
        if current:
            await update.message.reply_text(f"Сейчас сводка приходит в {current}. /setsummary off — отключить")
        else:
            await update.message.reply_text("Время сводки не задано. /setsummary 20:00")
        return
    arg = context.args[0].strip().lower()
    if arg == "off":
        delete_summary_time(user_id)
        await update.message.reply_text("📵 Ежедневная сводка отключена.")
        return
    try:
        datetime.strptime(arg, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Используй ЧЧ:ММ")
        return
    set_summary_time(user_id, arg)
    await update.message.reply_text(f"📋 Ежедневная сводка будет приходить в {arg}.")

async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pet = get_pet(user_id)
    if not pet:
        await update.message.reply_text("У вас пока нет питомца. Напишите /start!")
        return

    pet_type = pet["type"]
    level = pet["level"]
    mood = pet["mood"]
    is_sick = pet.get("is_sick", False)

    evolution_map = PET_TYPES[pet_type]["evolution"]
    current_emoji = evolution_map.get(level, PET_TYPES[pet_type]["emoji"])
    next_level = min([l for l in evolution_map.keys() if l > level], default=None)
    next_emoji = evolution_map.get(next_level, "") if next_level else ""

    status_emoji, pet_msg = get_pet_message(user_id)
    ascii_art = get_pet_ascii_art(pet_type, level, mood, is_sick)

    message = (
        f"{current_emoji} **{escape_markdown(pet['name'], version=2)}** (уровень {level})\n"
        f"🍖 Сытость: {pet['hunger']}/200\n"
        f"😊 Настроение: {pet['mood']}/200 ({status_emoji})\n"
        f"✨ Опыт: {pet['xp']}/100\n"
    )
    if is_sick:
        message += "🤒 **Питомец болен!** Выполните 3 обещания подряд!\n"
    message += f"\n```\n{ascii_art}\n```\n{pet_msg}\n"
    if next_emoji:
        message += f"\nСледующая эволюция на уровне {next_level}: {next_emoji}"

    keyboard = [[InlineKeyboardButton("🔄 Сменить питомца", callback_data="changepet_start")]]
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def changepet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for pet_type, info in PET_TYPES.items():
        if info["premium"] and not is_premium(update.effective_user.id):
            continue
        if info["premium"]:
            cost_text = "Только премиум"
        else:
            cost_text = f"{info['cost']} 🪙" if info['cost'] > 0 else "Бесплатно"
        button_text = f"{info['emoji']} {info['name']} ({cost_text})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"changepet_{pet_type}")])
    await update.message.reply_text("Выберите нового питомца:", reply_markup=InlineKeyboardMarkup(keyboard))

async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    coins = get_coins(user_id)
    items = get_shop_items()
    message = f"🛒 **Магазин достижений** (ваш баланс: {coins} 🪙)\n\n"
    keyboard = []
    for item in items:
        message += f"{item['emoji']} {item['name']} — {item['cost']} 🪙\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item['name']}", callback_data=f"buy_{item['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def freeze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("🛡 Заморозка доступна только премиум-пользователям.")
        return

    user = db.users.find_one({"user_id": user_id})
    freezes = user.get("freezes_available", 0) if user else 0

    if freezes <= 0:
        await update.message.reply_text("😔 У вас не осталось заморозок.")
        return

    # Показываем подтверждение
    keyboard = [[
        InlineKeyboardButton("✅ Да, заморозить", callback_data="confirm_freeze"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_freeze")
    ]]
    await update.message.reply_text(
        f"🛡 У вас есть {freezes} замороз(ок).\n\n"
        "Вы уверены? Заморозка сохранит вашу серию на сегодня, даже если вы не выполните ни одного обещания.\n"
        "⚠️ Это действие нельзя отменить.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def challenges_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    challenges = get_active_challenges()
    if not challenges:
        await update.message.reply_text("Сегодня пока нет активных челленджей.")
        return
    for challenge in challenges:
        participants = len(challenge.get("participants", []))
        completed = len(challenge.get("completed", []))
        message = (
            f"🌍 **{challenge['title']}**\n"
            f"📝 {challenge['description']}\n"
            f"👥 Участников: {participants}\n"
            f"✅ Выполнили: {completed}\n"
        )
        keyboard = [[InlineKeyboardButton("Я участвую!", callback_data=f"joinchallenge_{str(challenge['_id'])}")]]
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    coins = get_coins(user_id)
    await update.message.reply_text(f"🪙 Ваш баланс: {coins} монет.")

async def motivate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages = [
        "💪 Ты можешь всё, что задумал(а)!",
        "🌟 Даже маленький шаг — это прогресс!",
        "🎯 Начало — самое сложное. Просто сделай первый шаг!",
        "🔥 Твоя дисциплина сегодня на высоте!",
        "⭐ Каждое выполненное обещание делает тебя сильнее!",
        "🌈 Верь в себя! У тебя всё получится!",
        "🏆 Ты — автор своей истории успеха!",
        "🎉 Празднуй маленькие победы — они ведут к большим!",
    ]
    await update.message.reply_text(random.choice(messages))

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    stats = get_admin_stats()
    recent_feedback = get_recent_feedback(5)
    feedback_text = ""
    if recent_feedback:
        feedback_text = "\n📝 **Последний фидбек:**\n"
        for fb in recent_feedback:
            safe_text = escape_markdown(fb['text'][:50] + '...' if len(fb['text'])>50 else fb['text'], version=2)
            feedback_text += f"• @{fb['username']}: {safe_text}\n"

    message = (
        "📊 **Статистика бота**\n\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"📝 Обещаний: {stats['total_agreements']}\n"
        f"⭐ Премиум: {stats['premium_users']}\n"
        f"📅 Активных сегодня: {stats['active_today']}\n"
        f"👥 Рефералов: {stats['total_referrals']}\n"
        f"{feedback_text}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

async def share_achievement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_stats(user_id)

    share_text = (
        f"🏆 **Мой прогресс в Promise Tracker!**\n\n"
        f"✅ Выполнено обещаний: {stats['done']}\n"
        f"🔥 Серия: {stats['streak']} дней\n"
        f"⭐ Уровень: {stats['xp']//100 + 1}\n\n"
        f"Присоединяйся: t.me/{BOT_USERNAME}"
    )

    await update.message.reply_text(
        f"📢 **Поделись своим прогрессом!**\n\n{share_text}\n\n"
        f"Скопируй этот текст и отправь в любой чат!\n"
        f"За каждого перешедшего по твоей ссылке ты получишь премиум! /invite",
        parse_mode="Markdown"
    )

# ---------- Обработчики ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_to_menu":
        await menu(update, context)
        return

    if data.startswith("diff_"):
        await difficulty_callback(update, context)
        return

    if data.startswith("done_"):
        agr_id = data.split("_", 1)[1]
        reward = mark_done(agr_id)
        user_id = query.from_user.id

        if reward is None:
            await query.edit_message_text("⚠️ Это обещание уже выполнено или не найдено.")
            return

        moto_msg = get_motivation_message("task_completed")
        coins_msg = get_coins_message(reward["coins"])
        safe_text = escape_markdown(reward['text'][:50], version=2)
        await query.edit_message_text(
            f"✅ Выполнено: «{safe_text}»\n\n"
            f"{moto_msg}\n"
            f"{coins_msg}\n"
            f"✨ +{reward['xp']} опыта",
            parse_mode="Markdown"
        )

        update_pet_stats(user_id, hunger_delta=20, mood_delta=30, performed=True)
        status_emoji, pet_msg = get_pet_message(user_id)
        await query.message.reply_text(pet_msg)

        new_achievements = check_achievements(user_id)
        for key in new_achievements:
            if key.startswith("streak_"):
                streak_val = int(key.split("_")[1])
                milestone_msg = check_streak_milestone(streak_val)
                if milestone_msg:
                    await query.message.reply_text(f"🎉 {milestone_msg}")
                    add_coins(user_id, 20)
            else:
                name, desc = ACHIEVEMENTS.get(key, (key, ""))
                if name:
                    await query.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!", parse_mode="Markdown")

        if can_attach_photo(user_id):
            context.user_data['pending_photo_agreement_id'] = agr_id
            keyboard = [[
                InlineKeyboardButton("📷 Да", callback_data="attach_photo"),
                InlineKeyboardButton("❌ Нет", callback_data="skip_photo")
            ]]
            await query.message.reply_text("Хотите прикрепить фото?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("edit_"):
        agr_id = data.split("_", 1)[1]
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено.")
            return
        safe_text = escape_markdown(agreement['text'], version=2)
        context.user_data['editing_agreement_id'] = agr_id
        await query.edit_message_text(
            f"✏️ Введите новый текст для обещания:\n«{safe_text}»\n\n"
            "Отправьте сообщение с новым текстом или /cancel для отмены."
        )
        return

    elif data.startswith("delete_"):
        agr_id = data.split("_", 1)[1]
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено.")
            return
        safe_text = escape_markdown(agreement['text'], version=2)
        keyboard = [[
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{agr_id}"),
            InlineKeyboardButton("❌ Нет", callback_data="show_list")
        ]]
        await query.edit_message_text(f"Удалить «{safe_text}»?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("confirm_delete_"):
        agr_id = data.split("_", 2)[2]
        delete_agreement(agr_id)
        await query.edit_message_text("🗑 Удалено.")
        user_id = query.from_user.id
        text, markup = build_list_message(user_id, only_active=True)
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "show_list":
        user_id = query.from_user.id
        text, markup = build_list_message(user_id, only_active=True)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    elif data == "attach_photo":
        await query.edit_message_text("Отправьте фото. /cancel для отмены")
        context.user_data['awaiting_photo'] = True
        return

    elif data == "skip_photo":
        if 'pending_photo_agreement_id' in context.user_data:
            del context.user_data['pending_photo_agreement_id']
        await query.edit_message_text("Фото не прикреплено.")
        return

    elif data == "cat_create":
        user_id = query.from_user.id
        count = get_category_count(user_id)
        if not is_premium(user_id) and count >= 1:
            await query.edit_message_text("❌ В бесплатной версии можно создать только 1 категорию.")
            return
        context.user_data['awaiting_category_name'] = True
        await query.edit_message_text("Введи название новой категории:")
        return

    elif data == "cat_delete_menu":
        user_id = query.from_user.id
        cats = get_categories(user_id)
        if not cats:
            await query.edit_message_text("Нет категорий для удаления.")
            return
        keyboard = [[InlineKeyboardButton(cat["name"], callback_data=f"catdel_{str(cat['_id'])}")] for cat in cats]
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="cat_back")])
        await query.edit_message_text("Выбери категорию:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("catdel_"):
        cat_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        if delete_category(user_id, cat_id):
            await query.edit_message_text("Категория удалена.")
        else:
            await query.edit_message_text("Не удалось удалить категорию.")
        return

    elif data == "cat_back":
        await categories_menu(update, context)
        return

    elif data.startswith("addcat_"):
        cat_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        text = context.user_data.get('pending_agreement_text')
        diff = context.user_data.get('pending_agreement_diff', 0)
        if not text:
            await query.edit_message_text("❌ Ошибка: текст обещания не найден. Попробуйте снова.")
            return
        del context.user_data['pending_agreement_text']
        del context.user_data['pending_agreement_diff']
        if cat_id == "none":
            add_agreement(user_id, text, difficulty=diff)
        else:
            try:
                oid = ObjectId(cat_id)
                add_agreement(user_id, text, category_id=oid, difficulty=diff)
            except:
                add_agreement(user_id, text, difficulty=diff)
        diff_names = {0: "Легко", 1: "Средне", 2: "Хардкор"}
        safe_text = escape_markdown(text, version=2)
        await query.edit_message_text(f"✅ Сохранено ({diff_names[diff]}): \"{safe_text}\"", parse_mode="Markdown")
        new_achievements = check_achievements(user_id)
        for key in new_achievements:
            if key.startswith("streak_"):
                continue
            name, desc = ACHIEVEMENTS.get(key, (key, ""))
            if name:
                await query.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!", parse_mode="Markdown")
        return

    elif data == "cancel_add":
        if 'pending_agreement_text' in context.user_data:
            del context.user_data['pending_agreement_text']
        if 'pending_agreement_diff' in context.user_data:
            del context.user_data['pending_agreement_diff']
        await query.edit_message_text("❌ Добавление обещания отменено.")
        return

    elif data == "changepet_start":
        keyboard = []
        for pet_type, info in PET_TYPES.items():
            if info["premium"] and not is_premium(query.from_user.id):
                continue
            if info["premium"]:
                cost_text = "Только премиум"
            else:
                cost_text = f"{info['cost']} 🪙" if info['cost'] > 0 else "Бесплатно"
            button_text = f"{info['emoji']} {info['name']} ({cost_text})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"changepet_{pet_type}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
        await query.edit_message_text("Выберите питомца:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data.startswith("changepet_"):
        pet_type = data.split("_", 1)[1]
        user_id = query.from_user.id
        info = PET_TYPES[pet_type]
        if info["premium"] and not is_premium(user_id):
            await query.edit_message_text("❌ Этот питомец только для премиум.")
            return
        cost = info["cost"]
        if cost > 0:
            current_coins = get_coins(user_id)
            if current_coins < cost:
                await query.edit_message_text(f"❌ Нужно {cost} монет, у вас {current_coins}.")
                return
        success = change_pet(user_id, pet_type, cost_coins=cost)
        if success:
            await query.edit_message_text(f"✅ Питомец изменён на {info['emoji']} {info['name']}!")
        else:
            await query.edit_message_text("❌ Не удалось сменить питомца.")
        return

    elif data.startswith("buy_"):
        item_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        success, msg = buy_item(user_id, item_id)
        await query.edit_message_text(msg)
        return

    elif data.startswith("joinchallenge_"):
        challenge_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        success, msg = join_challenge(user_id, challenge_id)
        await query.edit_message_text(msg)
        return

    elif data == "confirm_freeze":
        user_id = query.from_user.id
        success = use_freeze(user_id)
        if success:
            user = db.users.find_one({"user_id": user_id})
            freezes = user.get("freezes_available", 0) if user else 0
            await query.edit_message_text(f"❄️ День заморожен! Ваша серия не прервётся.\nОсталось заморозок: {freezes}")
        else:
            await query.edit_message_text("😔 Не удалось применить заморозку. Возможно, они закончились или уже использованы сегодня.")
        return

    elif data == "cancel_freeze":
        await query.edit_message_text("❌ Заморозка отменена.")
        return

    elif data == "donate_info":
        await query.edit_message_text(
            "☕ **Поддержать проект**\n\n"
            "Если бот помогает вам быть продуктивнее, вы можете поддержать его развитие:\n\n"
            "Для поддержки проекта свяжитесь с разработчиком через команду /feedback\n\n"
            "Спасибо, что помогаете боту расти! 🙏",
            parse_mode="Markdown"
        )
        return

    elif data.startswith("premium_"):
        days = 30
        stars_cost = 50
        if data == "premium_30":
            days = 30
            stars_cost = 50
        elif data == "premium_90":
            days = 90
            stars_cost = 125
        elif data == "premium_forever":
            days = 3650
            stars_cost = 500

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Promise Tracker Premium",
            description=f"Премиум-доступ на {days if days < 3650 else 'все время'} дней",
            payload=data,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Premium", stars_cost)],
            start_parameter="premium_subscription"
        )
        return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message.text else ""
    user_id = update.effective_user.id

    # Редактирование обещания
    if context.user_data.get('editing_agreement_id'):
        agr_id = context.user_data['editing_agreement_id']
        del context.user_data['editing_agreement_id']
        new_text = text.strip()
        if not new_text:
            await update.message.reply_text("❌ Текст не может быть пустым. Редактирование отменено.")
            return
        update_agreement(agr_id, new_text)
        safe_text = escape_markdown(new_text, version=2)
        await update.message.reply_text(f"✅ Обещание обновлено: «{safe_text}»")
        t, m = build_list_message(user_id, only_active=True)
        for part in split_message(t):
            await update.message.reply_text(part, parse_mode="Markdown", reply_markup=m if part == t else None)
        return

    # Прикрепление фото
    if context.user_data.get('awaiting_photo') and update.message.photo:
        photo_file = update.message.photo[-1]
        photo_file_id = photo_file.file_id
        agr_id = context.user_data.get('pending_photo_agreement_id')
        if agr_id:
            if can_attach_photo(user_id):
                mark_done(agr_id, photo_file_id=photo_file_id)
                await update.message.reply_text("📷 Фото прикреплено! +10 монет за выполнение!")
            else:
                await update.message.reply_text("⚠️ Дневной лимит фото исчерпан.")
        del context.user_data['awaiting_photo']
        if 'pending_photo_agreement_id' in context.user_data:
            del context.user_data['pending_photo_agreement_id']
        return

    if context.user_data.get('awaiting_category_name'):
        del context.user_data['awaiting_category_name']
        if create_category(user_id, text):
            await update.message.reply_text(f"Категория «{text}» создана.")
        else:
            await update.message.reply_text("Категория уже существует.")
        return

    if context.user_data.get('adding_agreement_no_cat'):
        del context.user_data['adding_agreement_no_cat']
        context.user_data['pending_agreement_text'] = text
        keyboard = [
            [InlineKeyboardButton("🌱 Легко", callback_data="diff_0"),
             InlineKeyboardButton("⚡️ Средне", callback_data="diff_1"),
             InlineKeyboardButton("🔥 Хардкор", callback_data="diff_2")]
        ]
        await update.message.reply_text("Выбери сложность обещания:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if text == "➕ Новое обещание":
        await update.message.reply_text("Напиши текст обещания:")
        context.user_data['adding_agreement_no_cat'] = True
        return
    elif text == "📝 Активные":
        t, m = build_list_message(user_id, only_active=True)
        for part in split_message(t):
            await update.message.reply_text(part, parse_mode="Markdown", reply_markup=m if part == t else None)
    elif text == "📜 История":
        await history_command(update, context)
    elif text == "📂 Категории":
        await categories_menu(update, context)
    elif text == "⏰ Напоминания":
        rem = get_reminder(user_id)
        if rem:
            await update.message.reply_text(f"Ежедневное напоминание на {rem}\n/remind off — отключить")
        else:
            await update.message.reply_text("Ежедневное напоминание не установлено\n/remind 18:00 — установить")
    elif text == "📋 Сводка":
        await summary_command(update, context)
    elif text == "📊 Статистика":
        await stats_command(update, context)
    elif text == "📤 Экспорт":
        await export_command(update, context)
    elif text == "🏆 Достижения":
        await achievements_command(update, context)
    elif text == "👥 Рефералы":
        await invite_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    elif text == "🐾 Питомец":
        await pet_command(update, context)
    elif text == "🛒 Магазин":
        await shop_command(update, context)
    elif text == "🛡 Заморозка":
        await freeze_command(update, context)
    elif text == "🌍 Челленджи":
        await challenges_command(update, context)
    elif text == "🪙 Баланс":
        await balance_command(update, context)
    elif text == "🤖 Напомнить":
        await update.message.reply_text(
            "🤖 **Умное напоминание**\n\n"
            "Просто напишите:\n"
            "`/remindme Завтра в 10 утра купить хлеб`\n\n"
            "Или /remindme без текста для примеров",
            parse_mode="Markdown"
        )
    elif text == "💬 Фидбек":
        await update.message.reply_text(
            "💬 **Поделись идеей или проблемой**\n\n"
            "Напишите /feedback и ваш текст\n"
            "Пример: `/feedback Хочу больше мотивации!`\n\n"
            "За полезные идеи дарим монеты! 🎁"
        )
    elif text == "📢 Наш канал":
        await update.message.reply_text(
            "📢 Подпишись на наш канал «Время действовать!»\n\n"
            "Там ты найдёшь советы по продуктивности, мотивацию, челленджи с призами и новости бота.\n\n"
            "👉 https://t.me/PromiseAction"
        )
        return
    elif text == "👑 VIP-помощь":
        await update.message.reply_text(
            "👑 **VIP-поддержка (премиум)**\n\n"
            "Опишите вашу проблему после команды /viphelp.\n"
            "Пример: `/viphelp Не могу сменить питомца`"
        )
    elif text == "❌ Отмена":
        await cancel_command(update, context)
    else:
        if text and not text.startswith('/'):
            context.user_data['pending_agreement_text'] = text
            keyboard = [
                [InlineKeyboardButton("🌱 Легко", callback_data="diff_0"),
                 InlineKeyboardButton("⚡️ Средне", callback_data="diff_1"),
                 InlineKeyboardButton("🔥 Хардкор", callback_data="diff_2")]
            ]
            await update.message.reply_text("Выбери сложность обещания:", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE):
    if context.bot is None:
        return

    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc + MSK_OFFSET
    now_time = now_msk.strftime("%H:%M")
    today_msk = now_msk.date()

    create_daily_challenge()

    users_remind = get_users_with_reminders()
    for user_id, remind_time in users_remind:
        if remind_time == now_time:
            agreements = get_agreements(user_id, only_active=True)
            if agreements:
                undone = [escape_markdown(a["text"], version=2) for a in agreements if not a["is_done"]]
                if undone:
                    message = "🔔 **Напоминание!**\n\n"
                    for t in undone[:5]:
                        message += f"⬜ {t}\n"
                    message += "\nСписок: /list"
                    try:
                        await context.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                    except:
                        pass

    pending = get_pending_reminders_for_now(today_msk, now_time)
    for reminder_id, user_id, text in pending:
        safe_text = escape_markdown(text, version=2)
        try:
            await context.bot.send_message(chat_id=user_id, text=f"🔔 **Напоминание:** {safe_text}", parse_mode="Markdown")
            delete_scheduled_reminder(reminder_id)
        except:
            pass

    users_summary = get_users_with_summary()
    for user_id, summary_time in users_summary:
        if summary_time == now_time:
            try:
                await context.bot.send_message(chat_id=user_id, text=await build_daily_summary(user_id), parse_mode="Markdown")
            except:
                pass

    if now_time == "09:00":
        for user_id, _ in get_users_with_reminders()[:10]:
            if random.random() < 0.3:
                try:
                    msg = random.choice(MOTIVATIONAL_MESSAGES["morning_greetings"])
                    await context.bot.send_message(chat_id=user_id, text=msg)
                except:
                    pass

    if now_time == "21:00":
        for user_id, _ in get_users_with_reminders()[:10]:
            if random.random() < 0.2:
                try:
                    msg = random.choice(MOTIVATIONAL_MESSAGES["evening_encouragement"])
                    await context.bot.send_message(chat_id=user_id, text=msg)
                except:
                    pass

    # Вечерняя проверка серии (за час до полуночи по МСК)
    if now_time == "23:00":
        active_users = db.agreements.distinct("user_id", {"is_done": False})
        for uid in active_users[:50]:
            try:
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                last_done = db.agreements.find_one(
                    {"user_id": uid, "is_done": True, "done_at": {"$gte": today_start}}
                )
                if not last_done:
                    freezes = db.users.find_one({"user_id": uid})
                    freezes_count = freezes.get("freezes_available", 0) if freezes else 0
                    msg = (
                        "⚠️ Сегодня у вас ещё нет выполненных обещаний!\n"
                        "Ваша серия может сброситься в полночь.\n\n"
                    )
                    if freezes_count > 0:
                        msg += f"У вас есть {freezes_count} замороз(ок). Используйте /freeze, чтобы сохранить серию."
                    else:
                        msg += "У вас нет заморозок. Выполните хотя бы одно обещание до полуночи!"
                    await context.bot.send_message(chat_id=uid, text=msg)
            except:
                pass

    if now_time == "03:00":
        for user_id, _ in get_users_with_reminders()[:50]:
            if lose_level_if_inactive(user_id):
                try:
                    await context.bot.send_message(chat_id=user_id, text="⚠️ Твой питомец потерял уровень из-за долгого отсутствия!")
                except:
                    pass

# ---------- Main ----------
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан")

    application = Application.builder().token(BOT_TOKEN).build()
    init_db()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("achievements", achievements_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("remindme", smart_remind))
    application.add_handler(CommandHandler("smartremind", smart_remind))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("setsummary", set_summary_command))
    application.add_handler(CommandHandler("pet", pet_command))
    application.add_handler(CommandHandler("changepet", changepet_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("freeze", freeze_command))
    application.add_handler(CommandHandler("challenges", challenges_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("motivate", motivate_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CommandHandler("share", share_achievement))
    application.add_handler(CommandHandler("admin", admin_stats_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("viphelp", vip_help))

    # Платежи
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # Колбэки и сообщения
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))

    # Планировщик
    if application.job_queue:
        application.job_queue.run_repeating(check_scheduled_jobs, interval=60, first=10)

    # Flask в фоновом потоке
    port = int(os.environ.get("PORT", 10000))
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True)
    flask_thread.start()
    logging.info("Flask health-check запущен в фоне")

    # Бот в главном потоке
    logging.info("Бот запущен в главном потоке")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()