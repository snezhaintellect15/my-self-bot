import logging
import os
from datetime import datetime, timedelta, date
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue
from database import (init_db, create_user, is_premium, set_premium,
                      add_agreement, get_agreements, get_agreement_by_id,
                      mark_done, delete_agreement, update_agreement,
                      create_category, get_categories, get_category_count,
                      set_reminder, delete_reminder, get_reminder, get_users_with_reminders,
                      get_stats, get_agreements_export,
                      check_achievements, get_user_achievements, ACHIEVEMENTS,
                      set_summary_time, delete_summary_time, get_summary_time, get_users_with_summary,
                      count_scheduled_reminders, create_scheduled_reminder,
                      get_pending_reminders_for_now, delete_scheduled_reminder,
                      get_ref_code, get_user_by_ref_code, get_referral_stats,
                      get_admin_stats, add_xp, get_xp, use_freeze,
                      get_pet, update_pet_stats, get_pet_message, change_pet,
                      get_shop_items, buy_item, get_inventory,
                      get_coins, add_coins,
                      PET_TYPES, lose_level_if_inactive, get_pet_ascii_art,
                      create_daily_challenge, get_active_challenges, join_challenge,
                      check_challenge_completion, get_all_challenges_stats,
                      can_attach_photo, count_photos_today, get_stats_by_category,
                      db)
from bson.objectid import ObjectId

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_USERNAME = "MyPromiseTrackerBot"  # замени на свой username бота (без @)
MSK_OFFSET = timedelta(hours=3)

# ---------- Flask ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_flask).start()
# -----------------------

def build_list_message(user_id: int, only_active: bool = False, only_done: bool = False):
    agreements = get_agreements(user_id, only_active=only_active, only_done=only_done)
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
        text = agr["text"]
        is_done = agr["is_done"]
        cat_name = agr.get("category_name")
        agr_id = str(agr["_id"])
        diff = agr.get("difficulty", 0)
        prefix = diff_icons.get(diff, "")
        photo_mark = " 📷" if agr.get("photo_file_id") else ""
        display_text = f"{prefix} {text}{photo_mark}"
        if cat_name is None:
            no_cat.append((agr_id, display_text, is_done))
        else:
            groups.setdefault(cat_name, []).append((agr_id, display_text, is_done))

    response = "📝 **Активные обещания:**\n\n" if only_active else "📜 **История выполненных:**\n\n"
    keyboard = []

    if no_cat:
        response += "⚪️ *Без категории:*\n"
        for agr_id, text, is_done in no_cat:
            status = "⬜" if not is_done else "✅"
            response += f"  {status} {text}\n"
            if not is_done:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып. ({text[:15]})", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Изм.", callback_data=f"edit_{agr_id}"),
                    InlineKeyboardButton(f"🔔 Напомнить", callback_data=f"remindat_{agr_id}")
                ])

    for cat, items in groups.items():
        response += f"\n📂 *{cat}:*\n"
        for agr_id, text, is_done in items:
            status = "⬜" if not is_done else "✅"
            response += f"  {status} {text}\n"
            if not is_done:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып. ({text[:15]})", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Изм.", callback_data=f"edit_{agr_id}"),
                    InlineKeyboardButton(f"🔔 Напомнить", callback_data=f"remindat_{agr_id}")
                ])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return response, reply_markup

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
        [KeyboardButton("🪙 Баланс")]
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    referrer_id = None
    if args:
        ref_code = args[0]
        referrer = get_user_by_ref_code(ref_code)
        if referrer:
            referrer_id = referrer["user_id"]

    create_user(user_id, referrer_id)

    xp = get_xp(user_id)
    level = xp // 100 + 1
    coins = get_coins(user_id)
    welcome_text = (
        f"👋 Привет! Я твой персональный трекер обещаний.\n\n"
        f"✨ Со мной ты можешь:\n"
        f"• Записывать обещания и цели\n"
        f"• Выбирать уровень сложности (🌱 Легко, ⚡️ Средне, 🔥 Хардкор)\n"
        f"• Получать напоминания и ежедневные сводки\n"
        f"• Отслеживать прогресс и достижения\n"
        f"• Делать фото-подтверждение выполненных обещаний\n\n"
        f"📊 Твой уровень: {level} (XP: {xp})\n"
        f"🪙 Монеты: {coins}\n"
        f"📌 <b>Главное меню:</b> /menu\n"
        f"👥 Пригласи друга и получи <b>7 дней премиума</b> — /invite\n"
        f"ℹ️ Все команды: /help"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")

    if referrer_id:
        await update.message.reply_text("🎁 Вы перешли по реферальной ссылке! Вам начислено 3 дня премиума.")
        try:
            await context.application.bot.send_message(
                chat_id=referrer_id,
                text="🎉 По вашей реферальной ссылке зарегистрировался новый пользователь! Вы получили 7 дней премиума."
            )
        except:
            pass

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
        "Приглашайте друзей и получайте бонусы!\n"
        "• За каждого приглашённого — **7 дней премиума**.\n"
        "• Приглашённый получает **3 дня премиума**.\n\n"
        f"📊 **Ваша статистика:**\n"
        f"• Приглашено всего: {stats['total']}\n"
        f"• Активных: {stats['active']}"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add — быстро добавить обещание без категории\n"
        "/list — показать активные обещания\n"
        "/history — показать выполненные обещания\n"
        "/stats — твоя статистика и достижения\n"
        "/achievements — список достижений\n"
        "/export — экспорт данных (премиум — текстовый файл)\n"
        "/summary — сводка за сегодня\n"
        "/setsummary ЧЧ:ММ — установить время ежедневной сводки\n"
        "/setsummary off — отключить ежедневную сводку\n"
        "/remind ЧЧ:ММ — ежедневное напоминание о невыполненных\n"
        "/remind off — отключить ежедневное напоминание\n"
        "/remindat ДД.ММ ЧЧ:ММ [текст] — напомнить о конкретном обещании в дату/время\n"
        "/invite — реферальная ссылка и статистика\n"
        "/pet — твой питомец\n"
        "/changepet — сменить питомца\n"
        "/shop — магазин достижений\n"
        "/freeze — заморозить день (премиум)\n"
        "/challenges — активные челленджи\n"
        "/balance — твой баланс монет\n"
        "/premium — инфо о премиуме и переключение (on/off)"
    )

async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Напиши текст после /add. Пример: `/add Прочитать книгу`")
        return
    text = " ".join(context.args)
    keyboard = [
        [InlineKeyboardButton("🌱 Легко", callback_data=f"diff_{text}|0"),
         InlineKeyboardButton("⚡️ Средне", callback_data=f"diff_{text}|1"),
         InlineKeyboardButton("🔥 Хардкор", callback_data=f"diff_{text}|2")]
    ]
    await update.message.reply_text("Выбери сложность обещания:", reply_markup=InlineKeyboardMarkup(keyboard))

async def difficulty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("diff_"):
        _, payload = data.split("_", 1)
        text, diff = payload.rsplit("|", 1)
        diff = int(diff)
        user_id = query.from_user.id
        add_agreement(user_id, text, difficulty=diff)
        diff_names = {0: "Легко", 1: "Средне", 2: "Хардкор"}
        await query.edit_message_text(f"✅ Сохранено ({diff_names[diff]}): \"{text}\"")
        new_achievements = check_achievements(user_id)
        for key in new_achievements:
            name, desc = ACHIEVEMENTS[key]
            await query.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_list_message(user_id, only_active=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_list_message(user_id, only_done=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)

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
        f"• Дней подряд с выполненными обещаниями: {stats['streak']}\n"
        f"• Уровень: {level} (XP: {xp})\n"
        f"• Монеты: {coins} 🪙\n\n"
    )
    cat_stats = get_stats_by_category(user_id)
    if cat_stats:
        message += "📂 **По категориям:**\n"
        for cat in cat_stats:
            message += f"  {cat['name']}: {cat['done']}/{cat['total']} ({cat['percent']}%)\n"
    else:
        message += "Создайте категории, чтобы увидеть статистику по ним.\n"

    if stats['streak'] >= 30:
        message += "\n🔥 Легендарная серия! Ты невероятен!"
    elif stats['streak'] >= 7:
        message += "\n🌟 Отличная серия! Продолжай в том же духе."
    elif stats['streak'] == 0:
        message += "\n😴 Сегодня начни новую серию!"

    achieved = get_user_achievements(user_id)
    if achieved:
        message += "\n\n🏆 **Твои достижения:**\n"
        for key in achieved:
            name, desc = ACHIEVEMENTS[key]
            message += f"  {name} — {desc}\n"
    await update.message.reply_text(message, parse_mode="Markdown")

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

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_agreements_export(user_id)
    if not data:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    text = "📤 **Экспорт обещаний**\n\n"
    for agr in data:
        status = "✅" if agr["is_done"] else "⬜"
        cat_str = f"[{agr.get('category_name', '')}:] " if agr.get("category_name") else ""
        created_dt = agr["created_at"]
        created_msk = created_dt + MSK_OFFSET
        created_formatted = created_msk.strftime("%Y-%m-%d %H:%M")
        line = f"{status} {cat_str}{agr['text']} (создано: {created_formatted}"
        if agr["is_done"] and agr.get("done_at"):
            done_dt = agr["done_at"]
            done_msk = done_dt + MSK_OFFSET
            done_formatted = done_msk.strftime("%Y-%m-%d %H:%M")
            line += f", выполнено: {done_formatted}"
        line += ")\n"
        text += line

    text += f"\nВсего записей: {len(data)}"
    if is_premium(user_id):
        file_content = text
        await update.message.reply_document(
            document=file_content.encode('utf-8-sig'),
            filename="agreements_export.txt",
            caption="📎 Ваш текстовый файл с обещаниями (премиум-доступ)"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    status_text = "активен ✅" if premium else "неактивен ❌"
    if context.args and context.args[0] in ("on", "off"):
        new_status = context.args[0] == "on"
        set_premium(user_id, new_status)
        await update.message.reply_text(f"Премиум-статус изменён: {'активен' if new_status else 'отключён'}.")
        return
    await update.message.reply_text(
        f"⭐ **Премиум-возможности**\n"
        f"Твой статус: {status_text}\n\n"
        f"• Неограниченное количество категорий (сейчас можно создать только 1)\n"
        f"• Безлимитные напоминания на конкретные даты через /remindat (бесплатно — 1)\n"
        f"• Экспорт обещаний в текстовый файл\n"
        f"• Безлимитные фото-подтверждения\n"
        f"• Заморозка дня (сохраняет серию)\n"
        f"• Смена питомца на дракончика\n\n"
        f"👥 **Получить премиум бесплатно:**\n"
        f"Пригласи друга по реферальной ссылке — и вы оба получите премиум-дни! /invite\n\n"
        f"Для теста: /premium on / /premium off",
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
            text += f"  {i}. {cat['name']}\n"
    text += "\nВыбери действие:"
    keyboard = [
        [InlineKeyboardButton("➕ Создать категорию", callback_data="cat_create")],
    ]
    if cats:
        keyboard.append([InlineKeyboardButton("🗑 Удалить категорию", callback_data="cat_delete_menu")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_reminder(user_id)
        if current:
            await update.message.reply_text(f"Сейчас ежедневное напоминание на {current}. /remind off — отключить, /remind ЧЧ:ММ — изменить.")
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
    await update.message.reply_text(f"⏰ Ежедневное напоминание о невыполненных установлено на {arg}")

async def remindat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Используй:\n"
            "/remindat ДД.ММ ЧЧ:ММ <текст обещания> — напомнить о конкретном обещании в указанное время\n"
            "/remindat ДД.ММ ЧЧ:ММ — затем бот попросит выбрать обещание из активных\n"
            "/remindat каждую <день недели> ЧЧ:ММ <текст> — повторять еженедельно (например, каждую среду 09:00 Йога)\n"
            "День недели: пн, вт, ср, чт, пт, сб, вс (или английские mon, tue, wed, thu, fri, sat, sun)"
        )
        return

    args = context.args
    if args[0].lower() == "каждую":
        if len(args) < 3:
            await update.message.reply_text("Укажи день недели и время. Пример: /remindat каждую среду 09:00 Йога")
            return
        days_map = {
            "пн": 0, "mon": 0,
            "вт": 1, "tue": 1,
            "ср": 2, "wed": 2,
            "чт": 3, "thu": 3,
            "пт": 4, "fri": 4,
            "сб": 5, "sat": 5,
            "вс": 6, "sun": 6
        }
        day_str = args[1].lower().rstrip(',')
        if day_str not in days_map:
            await update.message.reply_text("Неизвестный день недели.")
            return
        recurring_day = days_map[day_str]
        time_str = args[2]
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await update.message.reply_text("Неверный формат времени.")
            return
        if len(args) > 3:
            text = " ".join(args[3:])
        else:
            await update.message.reply_text("Введи текст обещания после команды.")
            return
        if not is_premium(user_id) and count_scheduled_reminders(user_id) >= 1:
            await update.message.reply_text("Лимит бесплатных напоминаний (1) исчерпан. Приобрети премиум /premium")
            return
        add_agreement(user_id, text)
        last_agr = get_agreements(user_id)[0]
        agr_id = last_agr["_id"]
        today = date.today()
        days_ahead = recurring_day - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_date = today + timedelta(days=days_ahead)
        create_scheduled_reminder(user_id, agr_id, next_date, time_str, is_recurring=True, recurring_day=recurring_day)
        await update.message.reply_text(f"🔔 Напоминание о «{text}» будет приходить каждую {day_str.capitalize()} в {time_str}")
        return

    if len(args) < 2:
        await update.message.reply_text("Укажи дату и время. Пример: /remindat 05.06 18:00 Купить подарок")
        return
    date_str = args[0]
    time_str = args[1]
    try:
        remind_date = datetime.strptime(date_str, "%d.%m").replace(year=date.today().year).date()
        if remind_date < date.today():
            remind_date = remind_date.replace(year=date.today().year + 1)
    except ValueError:
        await update.message.reply_text("Неверный формат даты.")
        return
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат времени.")
        return

    if len(args) > 2:
        text = " ".join(args[2:])
    else:
        await update.message.reply_text("Введи текст обещания после команды.")
        return

    if not is_premium(user_id) and count_scheduled_reminders(user_id) >= 1:
        await update.message.reply_text("Лимит бесплатных напоминаний (1) исчерпан. Приобрети премиум /premium")
        return

    add_agreement(user_id, text)
    last_agr = get_agreements(user_id)[0]
    agr_id = last_agr["_id"]
    create_scheduled_reminder(user_id, agr_id, remind_date, time_str)
    await update.message.reply_text(f"🔔 Напоминание о «{text}» установлено на {remind_date.strftime('%d.%m.%Y')} в {time_str}")

async def button_remindat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("remindat_"):
        agr_id = data.split("_", 1)[1]
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено.")
            return
        context.user_data['pending_remindat_agr_id'] = agr_id
        await query.edit_message_text(
            f"Введи дату и время для напоминания о «{agreement['text']}» в формате:\n"
            "`ДД.ММ ЧЧ:ММ` (например, 05.06 18:00)\n"
            "Или для еженедельного повтора: `каждую среду 09:00`",
            parse_mode="Markdown"
        )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(await build_daily_summary(user_id))

async def set_summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_summary_time(user_id)
        if current:
            await update.message.reply_text(f"Сейчас сводка приходит в {current}. /setsummary off — отключить, /setsummary ЧЧ:ММ — изменить.")
        else:
            await update.message.reply_text("Время сводки не задано. /setsummary 20:00 — установить.")
        return
    arg = context.args[0].strip().lower()
    if arg == "off":
        delete_summary_time(user_id)
        await update.message.reply_text("📵 Ежедневная сводка отключена.")
        return
    try:
        datetime.strptime(arg, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Используй ЧЧ:ММ, например 20:00")
        return
    set_summary_time(user_id, arg)
    await update.message.reply_text(f"📋 Ежедневная сводка будет приходить в {arg}.")

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

    message = "📋 **Сводка за сегодня**\n\n"
    if done_today > 0:
        message += f"✅ Сегодня ты выполнил {done_today} обещаний. Молодец!\n"
    else:
        message += "😴 Сегодня пока нет выполненных обещаний. Не забудь отметить сделанное!\n"
    message += f"\n📈 **Общий прогресс:** {done_total} из {total} ({percent}%)\n"
    if percent == 100:
        message += "🌟 Идеально! Все обещания выполнены."
    elif percent >= 75:
        message += "🔥 Отличный результат, продолжай в том же духе!"
    return message

async def check_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE):
    now_utc = datetime.utcnow()
    now_msk = now_utc + MSK_OFFSET
    now_time = now_msk.strftime("%H:%M")
    today_msk = now_msk.date()

    # Ежедневный челлендж
    create_daily_challenge()

    # Напоминания с Quick Actions
    users_remind = get_users_with_reminders()
    for user_id, remind_time in users_remind:
        if remind_time == now_time:
            agreements = get_agreements(user_id, only_active=True)
            if agreements:
                undone = [(str(a["_id"]), a["text"]) for a in agreements if not a["is_done"]]
                if undone:
                    streak = get_stats(user_id)["streak"]
                    if streak >= 7:
                        message = f"🔥 Твоя серия: {streak} дней! Не прерывай!\n\n"
                    elif streak >= 3:
                        message = f"⚠️ Серия {streak} дня. Продолжай!\n\n"
                    else:
                        message = "🔔 **Напоминание!** Невыполненные обещания:\n\n"
                    for _, text in undone:
                        message += f"⬜ {text}\n"
                    message += "\nНе забудь выполнить! /list"
                    # Quick Actions кнопки
                    keyboard = [
                        [InlineKeyboardButton("✅ Сделал", callback_data=f"quickdone_{user_id}"),
                         InlineKeyboardButton("⏳ Отложить на час", callback_data=f"quickdelay_{user_id}"),
                         InlineKeyboardButton("❌ Пропустил", callback_data=f"quickskip_{user_id}")]
                    ]
                    try:
                        await context.application.bot.send_message(
                            chat_id=user_id, text=message, parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                    except Exception as e:
                        logging.error(f"Ошибка отправки напоминания {user_id}: {e}")

    # Предупреждение о сбросе серии
    for user_id, _ in users_remind:
        stats = get_stats(user_id)
        if stats["streak"] >= 3:
            last_done_dates = [d["_id"] for d in db.agreements.aggregate([
                {"$match": {"user_id": user_id, "is_done": True}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$done_at"}}}},
                {"$sort": {"_id": -1}},
                {"$limit": 2}
            ])]
            if len(last_done_dates) == 1 or (len(last_done_dates) > 1 and last_done_dates[0] != today_msk.isoformat() and last_done_dates[1] != today_msk.isoformat()):
                try:
                    await context.application.bot.send_message(
                        chat_id=user_id,
                        text="⚠️ Твоя серия под угрозой! Если сегодня не выполнишь обещание, прогресс обнулится."
                    )
                except:
                    pass

    # Запланированные напоминания
    pending = get_pending_reminders_for_now(today_msk, now_time)
    for reminder_id, user_id, text in pending:
        try:
            await context.application.bot.send_message(chat_id=user_id, text=f"🔔 **Напоминание:** {text}")
            delete_scheduled_reminder(reminder_id)
        except Exception as e:
            logging.error(f"Ошибка отправки запланированного напоминания {reminder_id}: {e}")

    # Сводки
    users_summary = get_users_with_summary()
    for user_id, summary_time in users_summary:
        if summary_time == now_time:
            try:
                await context.application.bot.send_message(
                    chat_id=user_id,
                    text=await build_daily_summary(user_id),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Ошибка отправки сводки {user_id}: {e}")

    # Итоги челленджей
    if now_msk.strftime("%H:%M") == "23:55":
        challenges = get_active_challenges()
        for ch in challenges:
            completed = check_challenge_completion(str(ch["_id"]))
            if completed:
                message = (
                    f"🏁 **Итоги челленджа «{ch['title']}»**\n"
                    f"✅ Выполнили: {len(completed)} из {len(ch.get('participants', []))}\n"
                    f"Каждый выполнивший получил по 100 монет! 🪙"
                )
                for user_id in ch.get("participants", []):
                    try:
                        await context.application.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                    except:
                        pass

    # Проверка неактивности и потеря уровня питомца (раз в сутки в 03:00)
    if now_msk.strftime("%H:%M") == "03:00":
        all_users = db.users.find({})
        for user in all_users:
            uid = user["user_id"]
            if lose_level_if_inactive(uid):
                try:
                    await context.application.bot.send_message(
                        chat_id=uid,
                        text="⚠️ Твой питомец потерял уровень из-за долгого отсутствия! Возвращайся и выполняй обещания."
                    )
                except:
                    pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Quick Actions
    if data.startswith("quickdone_"):
        user_id = query.from_user.id
        agreements = get_agreements(user_id, only_active=True)
        if agreements:
            # Отмечаем первое невыполненное
            for a in agreements:
                if not a["is_done"]:
                    mark_done(str(a["_id"]))
                    await query.edit_message_text("✅ Отмечено как выполненное!")
                    return
        await query.edit_message_text("Все обещания уже выполнены!")
        return
    elif data.startswith("quickdelay_"):
        # Просто удаляем сообщение с напоминанием
        await query.edit_message_text("⏳ Напоминание отложено на час. Я напомню позже.")
        # Можно реализовать реальную задержку через job_queue, но пока заглушка
        return
    elif data.startswith("quickskip_"):
        await query.edit_message_text("❌ Пропущено. Не забудь выполнить позже!")
        return

    if data.startswith("diff_"):
        await difficulty_callback(update, context)
        return
    if data.startswith("remindat_"):
        await button_remindat(update, context)
        return
    if data.startswith("buy_"):
        await buy_callback(update, context)
        return
    if data.startswith("joinchallenge_"):
        await join_challenge_callback(update, context)
        return
    if data.startswith("changepet_"):
        await changepet_callback(update, context)
        return
    if data == "changepet_start":
        await changepet_start(update, context)
        return

    if data == "cat_create":
        user_id = query.from_user.id
        count = get_category_count(user_id)
        if not is_premium(user_id) and count >= 1:
            await query.edit_message_text("❌ В бесплатной версии можно создать только 1 категорию. Приобрети премиум! /premium")
            return
        context.user_data['awaiting_category_name'] = True
        await query.edit_message_text("Введи название новой категории:")
    elif data == "cat_delete_menu":
        user_id = query.from_user.id
        cats = get_categories(user_id)
        if not cats:
            await query.edit_message_text("Нет категорий для удаления.")
            return
        keyboard = [[InlineKeyboardButton(cat["name"], callback_data=f"catdel_{str(cat['_id'])}")] for cat in cats]
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="cat_back")])
        await query.edit_message_text("Выбери категорию для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("catdel_"):
        cat_id = data.split("_", 1)[1]
        try:
            oid = ObjectId(cat_id)
        except:
            await query.edit_message_text("Неверный идентификатор категории.")
            return
        db.categories.delete_one({"_id": oid})
        await query.edit_message_text("Категория удалена.")
    elif data == "cat_back":
        await categories_menu(update, context)
        return
    elif data.startswith("done_"):
        agr_id = data.split("_", 1)[1]
        mark_done(agr_id)
        user_id = query.from_user.id
        update_pet_stats(user_id, hunger_delta=20, mood_delta=30, performed=True)
        status_emoji, pet_msg = get_pet_message(user_id)
        new_achievements = check_achievements(user_id)
        await query.edit_message_text("✅ Отмечено выполненным!")
        await query.message.reply_text(pet_msg)
        for key in new_achievements:
            name, desc = ACHIEVEMENTS[key]
            await query.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")

        if can_attach_photo(user_id):
            context.user_data['pending_photo_agreement_id'] = agr_id
            keyboard = [[
                InlineKeyboardButton("📷 Да, прикрепить фото", callback_data="attach_photo"),
                InlineKeyboardButton("❌ Нет, спасибо", callback_data="skip_photo")
            ]]
            await query.message.reply_text("Хотите прикрепить фото к выполненному обещанию? (1 фото в день бесплатно, премиум безлимит)", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text("⚠️ Дневной лимит фото исчерпан (1 бесплатно). Премиум снимает ограничение! /premium")

    elif data == "attach_photo":
        await query.edit_message_text("Отправьте фото. Для отмены нажмите /cancel")
        context.user_data['awaiting_photo'] = True

    elif data == "skip_photo":
        if 'pending_photo_agreement_id' in context.user_data:
            del context.user_data['pending_photo_agreement_id']
        await query.edit_message_text("Фото не прикреплено.")

    elif data.startswith("delete_"):
        agr_id = data.split("_", 1)[1]
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено."); return
        keyboard = [[
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{agr_id}"),
            InlineKeyboardButton("❌ Нет, оставить", callback_data=f"cancel_delete_{agr_id}")
        ]]
        await query.edit_message_text(f"Удалить «{agreement['text']}»?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("edit_"):
        agr_id = data.split("_", 1)[1]
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено."); return
        context.user_data['editing_agreement_id'] = agr_id
        await query.edit_message_text(f"Введи новый текст для «{agreement['text']}»:")
    elif data.startswith("confirm_delete_"):
        agr_id = data.split("_", 2)[2]
        agreement = get_agreement_by_id(agr_id)
        if agreement:
            delete_agreement(agr_id)
            await query.edit_message_text("🗑 Удалено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 К активным", callback_data="show_list")]]))
        else:
            await query.edit_message_text("Уже удалено.")
    elif data.startswith("cancel_delete_"):
        user_id = query.from_user.id
        text, markup = build_list_message(user_id, only_active=True)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    elif data == "show_list":
        user_id = query.from_user.id
        text, markup = build_list_message(user_id, only_active=True)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message.text else ""
    user_id = update.effective_user.id

    if context.user_data.get('awaiting_photo') and update.message.photo:
        photo_file = update.message.photo[-1]
        photo_file_id = photo_file.file_id
        agr_id = context.user_data.get('pending_photo_agreement_id')
        if agr_id:
            if can_attach_photo(user_id):
                mark_done(agr_id, photo_file_id=photo_file_id)
                await update.message.reply_text("📷 Фото прикреплено к обещанию!")
            else:
                await update.message.reply_text("⚠️ Дневной лимит исчерпан. Фото не сохранено.")
        del context.user_data['awaiting_photo']
        del context.user_data['pending_photo_agreement_id']
        return

    if 'pending_remindat_agr_id' in context.user_data:
        agr_id = context.user_data.pop('pending_remindat_agr_id')
        parts = text.split()
        if not parts:
            await update.message.reply_text("Введи дату и время. Пример: 05.06 18:00 или каждую среду 09:00")
            return
        if parts[0].lower() == "каждую":
            days_map = {"пн":0,"вт":1,"ср":2,"чт":3,"пт":4,"сб":5,"вс":6,"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
            if len(parts) < 3:
                await update.message.reply_text("Укажи день недели и время. Пример: каждую среду 09:00")
                return
            day_str = parts[1].lower().rstrip(',')
            if day_str not in days_map:
                await update.message.reply_text("Неизвестный день недели.")
                return
            recurring_day = days_map[day_str]
            time_str = parts[2]
            try:
                datetime.strptime(time_str, "%H:%M")
            except ValueError:
                await update.message.reply_text("Неверный формат времени.")
                return
            if not is_premium(user_id) and count_scheduled_reminders(user_id) >= 1:
                await update.message.reply_text("Лимит бесплатных напоминаний (1) исчерпан. Приобрети премиум /premium")
                return
            today = date.today()
            days_ahead = recurring_day - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_date = today + timedelta(days=days_ahead)
            create_scheduled_reminder(user_id, agr_id, next_date, time_str, is_recurring=True, recurring_day=recurring_day)
            agreement = get_agreement_by_id(agr_id)
            await update.message.reply_text(f"🔔 Напоминание о «{agreement['text']}» будет приходить каждую {day_str.capitalize()} в {time_str}")
            return
        else:
            if len(parts) < 2:
                await update.message.reply_text("Укажи дату и время через пробел. Пример: 05.06 18:00")
                return
            date_str = parts[0]
            time_str = parts[1]
            try:
                remind_date = datetime.strptime(date_str, "%d.%m").replace(year=date.today().year).date()
                if remind_date < date.today():
                    remind_date = remind_date.replace(year=date.today().year + 1)
            except ValueError:
                await update.message.reply_text("Неверный формат даты.")
                return
            try:
                datetime.strptime(time_str, "%H:%M")
            except ValueError:
                await update.message.reply_text("Неверный формат времени.")
                return
            if not is_premium(user_id) and count_scheduled_reminders(user_id) >= 1:
                await update.message.reply_text("Лимит бесплатных напоминаний (1) исчерпан. Приобрети премиум /premium")
                return
            create_scheduled_reminder(user_id, agr_id, remind_date, time_str)
            agreement = get_agreement_by_id(agr_id)
            await update.message.reply_text(f"🔔 Напоминание о «{agreement['text']}» установлено на {remind_date.strftime('%d.%m.%Y')} в {time_str}")
        return

    if context.user_data.get('awaiting_category_name'):
        del context.user_data['awaiting_category_name']
        if create_category(user_id, text):
            await update.message.reply_text(f"Категория «{text}» создана.")
        else:
            await update.message.reply_text("Категория с таким именем уже существует.")
        return

    if 'editing_agreement_id' in context.user_data:
        agr_id = context.user_data.pop('editing_agreement_id')
        update_agreement(agr_id, text)
        await update.message.reply_text(f"✏️ Изменено: \"{text}\"")
        t, m = build_list_message(user_id, only_active=True)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
        return

    if text == "➕ Новое обещание":
        cats = get_categories(user_id)
        if not cats:
            await update.message.reply_text("Введи текст обещания (оно сохранится без категории):")
            context.user_data['adding_agreement_no_cat'] = True
        else:
            keyboard = [[InlineKeyboardButton(cat["name"], callback_data=f"addcat_{str(cat['_id'])}")] for cat in cats]
            keyboard.append([InlineKeyboardButton("Без категории", callback_data="addcat_none")])
            await update.message.reply_text("Выбери категорию для обещания:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📝 Активные":
        t, m = build_list_message(user_id, only_active=True)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
    elif text == "📜 История":
        await history_command(update, context)
    elif text == "📂 Категории":
        await categories_menu(update, context)
    elif text == "⏰ Напоминания":
        rem = get_reminder(user_id)
        if rem:
            await update.message.reply_text(f"Ежедневное напоминание на {rem}. /remind off, /remind ЧЧ:ММ")
        else:
            await update.message.reply_text("Ежедневное напоминание не установлено. /remind 18:00")
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
    else:
        if context.user_data.get('adding_agreement_no_cat'):
            del context.user_data['adding_agreement_no_cat']
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено (без категории): \"{text}\"")
        elif 'selected_category_id' in context.user_data:
            cat_id = context.user_data.pop('selected_category_id')
            add_agreement(user_id, text, category_id=ObjectId(cat_id))
            cat_name = next((c["name"] for c in get_categories(user_id) if str(c["_id"]) == cat_id), "категория")
            await update.message.reply_text(f"✅ Сохранено в «{cat_name}»: \"{text}\"")
        else:
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено: \"{text}\" (без категории)")
        new_achievements = check_achievements(user_id)
        for key in new_achievements:
            name, desc = ACHIEVEMENTS[key]
            await update.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")

async def add_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data == "addcat_none":
        context.user_data['adding_agreement_no_cat'] = True
        await query.edit_message_text("Введи текст обещания (без категории):")
    elif data.startswith("addcat_"):
        cat_id = data.split("_", 1)[1]
        context.user_data['selected_category_id'] = cat_id
        cat_name = next((c["name"] for c in get_categories(user_id) if str(c["_id"]) == cat_id), "")
        await query.edit_message_text(f"Введи текст обещания для категории «{cat_name}»:")

# ---------- Питомец ----------
async def pet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pet = get_pet(user_id)
    if not pet:
        await update.message.reply_text("У вас пока нет питомца. Напишите /start, чтобы получить его!")
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
        f"{current_emoji} **{pet['name']}** (уровень {level})\n"
        f"🍖 Сытость: {pet['hunger']}/200\n"
        f"😊 Настроение: {pet['mood']}/200 ({status_emoji})\n"
        f"✨ Опыт: {pet['xp']}/100\n"
    )
    if is_sick:
        message += "🤒 **Питомец болен!** Выполните 3 обещания подряд, чтобы вылечить.\n"
    message += f"\n```\n{ascii_art}\n```\n{pet_msg}\n"
    if next_emoji:
        message += f"\nСледующая эволюция на уровне {next_level}: {next_emoji}"

    keyboard = [[InlineKeyboardButton("🔄 Сменить питомца", callback_data="changepet_start")]]
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def changepet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for pet_type, info in PET_TYPES.items():
        if info["premium"]:
            cost_text = "Только премиум"
        else:
            cost_text = f"{info['cost']} 🪙" if info['cost'] > 0 else "Бесплатно"
        button_text = f"{info['emoji']} {info['name']} ({cost_text})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"changepet_{pet_type}")])
    await query.edit_message_text("Выберите нового питомца:", reply_markup=InlineKeyboardMarkup(keyboard))

async def changepet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "changepet_start":
        await changepet_start(update, context)
        return
    pet_type = data.split("_", 1)[1]
    user_id = query.from_user.id
    info = PET_TYPES[pet_type]
    if info["premium"] and not is_premium(user_id):
        await query.edit_message_text("❌ Дракончик доступен только премиум-пользователям. Приобретите премиум /premium")
        return
    cost = info["cost"]
    if cost > 0:
        current_coins = get_coins(user_id)
        if current_coins < cost:
            await query.edit_message_text(f"❌ Недостаточно монет. Нужно {cost}, у вас {current_coins}.")
            return
    success = change_pet(user_id, pet_type, cost_coins=cost)
    if success:
        await query.edit_message_text(f"✅ Питомец изменён на {info['emoji']} {info['name']}!")
    else:
        await query.edit_message_text("❌ Не удалось сменить питомца.")

async def changepet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for pet_type, info in PET_TYPES.items():
        if info["premium"]:
            cost_text = "Только премиум"
        else:
            cost_text = f"{info['cost']} 🪙" if info['cost'] > 0 else "Бесплатно"
        button_text = f"{info['emoji']} {info['name']} ({cost_text})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"changepet_{pet_type}")])
    await update.message.reply_text("Выберите нового питомца:", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Магазин ----------
async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    coins = get_coins(user_id)
    items = get_shop_items()
    message = f"🛒 **Магазин достижений** (ваш баланс: {coins} 🪙)\n\n"
    keyboard = []
    for item in items:
        message += f"{item['emoji']} {item['name']} — {item['cost']} 🪙\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item['name']} ({item['cost']} 🪙)", callback_data=f"buy_{item['id']}")])
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("buy_"):
        item_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        success, msg = buy_item(user_id, item_id)
        await query.edit_message_text(msg)

# ---------- Заморозка ----------
async def freeze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_premium(user_id):
        await update.message.reply_text("🛡 Заморозка доступна только премиум-пользователям. Приобретите премиум /premium")
        return
    success = use_freeze(user_id)
    if success:
        await update.message.reply_text("❄️ День заморожен! Ваша серия не прервётся, даже если сегодня не будет выполненных обещаний.")
    else:
        await update.message.reply_text("😔 У вас не осталось заморозок. Они обновляются каждый месяц с продлением премиума.")

# ---------- Челленджи ----------
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

async def join_challenge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("joinchallenge_"):
        challenge_id = data.split("_", 1)[1]
        user_id = query.from_user.id
        success, msg = join_challenge(user_id, challenge_id)
        await query.edit_message_text(msg)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    coins = get_coins(user_id)
    await update.message.reply_text(f"🪙 Ваш баланс: {coins} монет.")

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = int(os.environ.get("ADMIN_ID", 0))
    if user_id != admin_id:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    stats = get_admin_stats()
    message = (
        "📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📝 Всего обещаний: {stats['total_agreements']}\n"
        f"⭐ Премиум-пользователей: {stats['premium_users']}\n"
        f"📅 Активных сегодня: {stats['active_today']}\n"
        f"👥 Приглашено рефералов: {stats['total_referrals']}\n"
    )
    await update.message.reply_text(message, parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан")
    global db
    job_queue = JobQueue()
    application = Application.builder().token(BOT_TOKEN).job_queue(job_queue).build()
    init_db()

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
    application.add_handler(CommandHandler("remindat", remindat_command))
    application.add_handler(CommandHandler("invite", invite_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("setsummary", set_summary_command))
    application.add_handler(CommandHandler("pet", pet_command))
    application.add_handler(CommandHandler("changepet", changepet_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("freeze", freeze_command))
    application.add_handler(CommandHandler("challenges", challenges_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("admin", admin_stats_command))
    application.add_handler(CallbackQueryHandler(button_remindat, pattern="^remindat_"))
    application.add_handler(CallbackQueryHandler(add_category_callback, pattern="^addcat_"))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue.run_repeating(check_scheduled_jobs, interval=60, first=10)
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()