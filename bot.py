import logging
import os
import sqlite3
from datetime import datetime, timedelta, UTC, date
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
                      DB_NAME)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
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

# Вспомогательная: построение сгруппированного списка обещаний
def build_list_message(user_id: int):
    agreements = get_agreements(user_id)
    if not agreements:
        return "У тебя пока нет ни одного обещания.", None

    groups = {}
    no_cat = []
    for agr_id, text, is_done, cat_name in agreements:
        if cat_name is None:
            no_cat.append((agr_id, text, is_done))
        else:
            groups.setdefault(cat_name, []).append((agr_id, text, is_done))

    response = "📝 **Твои обещания:**\n\n"
    keyboard = []

    if no_cat:
        response += "⚪️ *Без категории:*\n"
        for agr_id, text, is_done in no_cat:
            status = "✅" if is_done else "⬜"
            response += f"  {status} {text}\n"
            if not is_done:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып. ({text[:15]})", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Изм.", callback_data=f"edit_{agr_id}")
                ])

    for cat, items in groups.items():
        response += f"\n📂 *{cat}:*\n"
        for agr_id, text, is_done in items:
            status = "✅" if is_done else "⬜"
            response += f"  {status} {text}\n"
            if not is_done:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып. ({text[:15]})", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Изм.", callback_data=f"edit_{agr_id}")
                ])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return response, reply_markup

# Главное меню (с разными иконками)
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📋 Мой список"), KeyboardButton("📂 Категории")],
        [KeyboardButton("⏰ Напоминания"), KeyboardButton("📋 Сводка")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⭐ Премиум")],
        [KeyboardButton("📤 Экспорт"), KeyboardButton("🏆 Достижения")]
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)
    await update.message.reply_text(
        "Привет! Я бот-трекер «Договорился с собой».\n"
        "С моей помощью ты можешь записывать обещания, распределять их по категориям и получать напоминания.\n"
        "/menu — главное меню."
    )
    await menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add — быстро добавить обещание без категории\n"
        "/list — показать список\n"
        "/stats — твоя статистика и достижения\n"
        "/achievements — список достижений\n"
        "/export — экспорт данных (премиум — текстовый файл)\n"
        "/summary — сводка за сегодня\n"
        "/setsummary ЧЧ:ММ — установить время ежедневной сводки\n"
        "/setsummary off — отключить ежедневную сводку\n"
        "/remind ЧЧ:ММ — напоминание\n"
        "/remind off — отключить напоминание\n"
        "/premium — инфо о премиуме и переключение (on/off)"
    )

# Быстрое добавление без категории
async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Напиши текст после /add. Пример: `/add Прочитать книгу`")
        return
    text = " ".join(context.args)
    add_agreement(user_id, text)
    await update.message.reply_text(f"✅ Сохранено: \"{text}\" (без категории)")
    new_achievements = check_achievements(user_id)
    for key in new_achievements:
        name, desc = ACHIEVEMENTS[key]
        await update.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")

# Список
async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_list_message(user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)

# Статистика
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_stats(user_id)
    message = (
        "📊 **Твоя статистика:**\n\n"
        f"• Всего обещаний: {stats['total']}\n"
        f"• Выполнено: {stats['done']} ({stats['percent']}%)\n"
        f"• Дней подряд с выполненными обещаниями: {stats['streak']}\n"
    )
    if stats['total'] > 0 and stats['percent'] == 100:
        message += "\n🌟 Идеально! Ты выполнил все обещания!"
    elif stats['streak'] >= 7:
        message += "\n🔥 Отличная серия! Продолжай в том же духе."

    achieved = get_user_achievements(user_id)
    if achieved:
        message += "\n\n🏆 **Твои достижения:**\n"
        for key in achieved:
            name, desc = ACHIEVEMENTS[key]
            message += f"  {name} — {desc}\n"
    await update.message.reply_text(message, parse_mode="Markdown")

# Достижения
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

# Экспорт
async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_agreements_export(user_id)
    if not data:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    text = "📤 **Экспорт обещаний**\n\n"
    for text_line, cat, created, is_done, done_at in data:
        status = "✅" if is_done else "⬜"
        cat_str = f"[{cat}:] " if cat else ""

        created_dt = datetime.fromisoformat(created)
        created_msk = created_dt + MSK_OFFSET
        created_formatted = created_msk.strftime("%Y-%m-%d %H:%M")

        line = f"{status} {cat_str}{text_line} (создано: {created_formatted}"

        if is_done and done_at:
            done_dt = datetime.fromisoformat(done_at)
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

# Премиум
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
        f"• Более одной категории (сейчас можно создать только 1)\n"
        f"• Расширенные напоминания\n"
        f"• Статистика и экспорт\n"
        f"• Текстовый файл с экспортом\n\n"
        f"Для теста: /premium on / /premium off",
        parse_mode="Markdown"
    )

# Управление категориями
async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cats = get_categories(user_id)
    text = "📂 **Твои категории:**\n"
    if not cats:
        text += "Пока нет ни одной."
    else:
        for i, (cid, name) in enumerate(cats, 1):
            text += f"  {i}. {name}\n"
    text += "\nВыбери действие:"
    keyboard = [
        [InlineKeyboardButton("➕ Создать категорию", callback_data="cat_create")],
    ]
    if cats:
        keyboard.append([InlineKeyboardButton("🗑 Удалить категорию", callback_data="cat_delete_menu")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# Напоминания
async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_reminder(user_id)
        if current:
            await update.message.reply_text(f"Сейчас напоминание на {current}. /remind off — отключить, /remind ЧЧ:ММ — изменить.")
        else:
            await update.message.reply_text("Напоминание не установлено. /remind 18:00")
        return
    arg = context.args[0].strip().lower()
    if arg == "off":
        delete_reminder(user_id)
        await update.message.reply_text("🔕 Напоминание отключено.")
        return
    try:
        datetime.strptime(arg, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Используй ЧЧ:ММ, например 18:00")
        return
    set_reminder(user_id, arg)
    await update.message.reply_text(f"⏰ Напоминание установлено на {arg}")

# Ежедневная сводка: ручная
async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(await build_daily_summary(user_id))

# Ежедневная сводка: настройка времени
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

# Построение текста сводки (с иконкой 📋)
async def build_daily_summary(user_id: int) -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    today = date.today()
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ? AND is_done = 1 AND DATE(done_at) = ?", (user_id, today.isoformat()))
    done_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM agreements WHERE user_id = ? AND is_done = 1", (user_id,))
    done_total = cursor.fetchone()[0]
    percent = round(done_total / total * 100, 1) if total > 0 else 0.0
    conn.close()

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

# Планировщик: проверка напоминаний и сводок
async def check_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE):
    now = (datetime.now(UTC) + MSK_OFFSET).strftime("%H:%M")
    # Напоминания
    users_remind = get_users_with_reminders()
    for user_id, remind_time in users_remind:
        if remind_time == now:
            agreements = get_agreements(user_id)
            if agreements:
                undone = [(a[0], a[1]) for a in agreements if not a[2]]
                if undone:
                    message = "🔔 **Напоминание!** Невыполненные обещания:\n\n"
                    for _, text in undone:
                        message += f"⬜ {text}\n"
                    message += "\nНе забудь выполнить! /list"
                    try:
                        await context.application.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Ошибка отправки напоминания {user_id}: {e}")
    # Сводки
    users_summary = get_users_with_summary()
    for user_id, summary_time in users_summary:
        if summary_time == now:
            try:
                await context.application.bot.send_message(
                    chat_id=user_id,
                    text=await build_daily_summary(user_id),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Ошибка отправки сводки {user_id}: {e}")

# Обработчик кнопок
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cat_create":
        user_id = query.from_user.id
        count = get_category_count(user_id)
        if not is_premium(user_id) and count >= 1:
            await query.edit_message_text("❌ В бесплатной версии можно создать только 1 категорию. Приобрети премиум! /premium")
            return
        context.user_data['awaiting_category_name'] = True
        await query.edit_message_text("Введи название новой категории (одно слово или фразу):")
    elif data == "cat_delete_menu":
        user_id = query.from_user.id
        cats = get_categories(user_id)
        if not cats:
            await query.edit_message_text("Нет категорий для удаления.")
            return
        keyboard = [[InlineKeyboardButton(name, callback_data=f"catdel_{cid}")] for cid, name in cats]
        keyboard.append([InlineKeyboardButton("« Назад", callback_data="cat_back")])
        await query.edit_message_text("Выбери категорию для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("catdel_"):
        cid = int(data.split("_")[1])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        await query.edit_message_text("Категория удалена. Обещания без категории.")
    elif data == "cat_back":
        await categories_menu(update, context)
        return
    elif data.startswith("done_"):
        agr_id = int(data.split("_")[1])
        mark_done(agr_id)
        user_id = query.from_user.id
        new_achievements = check_achievements(user_id)
        await query.edit_message_text("✅ Отмечено выполненным!")
        for key in new_achievements:
            name, desc = ACHIEVEMENTS[key]
            await query.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")
    elif data.startswith("delete_"):
        agr_id = int(data.split("_")[1])
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено."); return
        keyboard = [[
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{agr_id}"),
            InlineKeyboardButton("❌ Нет, оставить", callback_data=f"cancel_delete_{agr_id}")
        ]]
        await query.edit_message_text(f"Удалить «{agreement[1]}»?", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("edit_"):
        agr_id = int(data.split("_")[1])
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено."); return
        context.user_data['editing_agreement_id'] = agr_id
        await query.edit_message_text(f"Введи новый текст для «{agreement[1]}»:")
    elif data.startswith("confirm_delete_"):
        agr_id = int(data.split("_")[2])
        agreement = get_agreement_by_id(agr_id)
        if agreement:
            delete_agreement(agr_id)
            await query.edit_message_text("🗑 Удалено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 К списку", callback_data="show_list")]]))
        else:
            await query.edit_message_text("Уже удалено.")
    elif data.startswith("cancel_delete_"):
        user_id = query.from_user.id
        text, markup = build_list_message(user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    elif data == "show_list":
        user_id = query.from_user.id
        text, markup = build_list_message(user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

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
        t, m = build_list_message(user_id)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
        return

    if text == "➕ Новое обещание":
        cats = get_categories(user_id)
        if not cats:
            await update.message.reply_text("Введи текст обещания (оно сохранится без категории):")
            context.user_data['adding_agreement_no_cat'] = True
        else:
            keyboard = [[InlineKeyboardButton(name, callback_data=f"addcat_{cid}")] for cid, name in cats]
            keyboard.append([InlineKeyboardButton("Без категории", callback_data="addcat_none")])
            await update.message.reply_text("Выбери категорию для обещания:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif text == "📋 Мой список":
        t, m = build_list_message(user_id)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
    elif text == "📂 Категории":
        await categories_menu(update, context)
    elif text == "⏰ Напоминания":
        rem = get_reminder(user_id)
        if rem:
            await update.message.reply_text(f"Напоминание на {rem}. /remind off, /remind ЧЧ:ММ")
        else:
            await update.message.reply_text("Нет напоминания. /remind 18:00")
    elif text == "📋 Сводка":
        await summary_command(update, context)
    elif text == "📊 Статистика":
        await stats_command(update, context)
    elif text == "📤 Экспорт":
        await export_command(update, context)
    elif text == "🏆 Достижения":
        await achievements_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    else:
        if context.user_data.get('adding_agreement_no_cat'):
            del context.user_data['adding_agreement_no_cat']
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено (без категории): \"{text}\"")
            new_achievements = check_achievements(user_id)
            for key in new_achievements:
                name, desc = ACHIEVEMENTS[key]
                await update.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")
        elif 'selected_category_id' in context.user_data:
            cat_id = context.user_data.pop('selected_category_id')
            add_agreement(user_id, text, category_id=cat_id)
            cat_name = dict(get_categories(user_id)).get(cat_id, "категория")
            await update.message.reply_text(f"✅ Сохранено в «{cat_name}»: \"{text}\"")
            new_achievements = check_achievements(user_id)
            for key in new_achievements:
                name, desc = ACHIEVEMENTS[key]
                await update.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")
        else:
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено: \"{text}\" (без категории)")
            new_achievements = check_achievements(user_id)
            for key in new_achievements:
                name, desc = ACHIEVEMENTS[key]
                await update.message.reply_text(f"🎉 Поздравляем! Ты получил достижение **{name}**!\n_{desc}_", parse_mode="Markdown")

# Обработчик выбора категории при добавлении обещания
async def add_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data == "addcat_none":
        context.user_data['adding_agreement_no_cat'] = True
        await query.edit_message_text("Введи текст обещания (без категории):")
    elif data.startswith("addcat_"):
        cid = int(data.split("_")[1])
        context.user_data['selected_category_id'] = cid
        cat_name = dict(get_categories(user_id)).get(cid, "")
        await query.edit_message_text(f"Введи текст обещания для категории «{cat_name}»:")

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан")

    job_queue = JobQueue()
    application = Application.builder().token(BOT_TOKEN).job_queue(job_queue).build()
    init_db()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("achievements", achievements_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("setsummary", set_summary_command))
    application.add_handler(CallbackQueryHandler(add_category_callback, pattern="^addcat_"))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue.run_repeating(check_scheduled_jobs, interval=60, first=10)
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()