import logging
import os
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue
from database import (init_db, create_user, is_premium, set_premium,
                      add_agreement, get_agreements, get_agreement_by_id,
                      mark_done, delete_agreement, update_agreement,
                      create_category, get_categories, get_category_count,
                      set_reminder, delete_reminder, get_reminder, get_users_with_reminders,
                      get_stats)  # добавлен импорт get_stats

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

    # Группировка
    groups = {}
    no_cat = []
    for agr_id, text, is_done, cat_name in agreements:
        if cat_name is None:
            no_cat.append((agr_id, text, is_done))
        else:
            groups.setdefault(cat_name, []).append((agr_id, text, is_done))

    response = "📝 **Твои обещания:**\n\n"
    keyboard = []  # общий список кнопок

    # Сначала без категории
    if no_cat:
        response += "⚪️ *Без категории*\n"
        for i, (agr_id, text, is_done) in enumerate(no_cat, start=1):
            status = "✅" if is_done else "⬜"
            response += f"  {status} {text}\n"
            if not is_done:
                keyboard.append([
                    InlineKeyboardButton(f"✅ Вып. ({text[:15]})", callback_data=f"done_{agr_id}"),
                    InlineKeyboardButton(f"🗑 Удл.", callback_data=f"delete_{agr_id}"),
                    InlineKeyboardButton(f"✏️ Изм.", callback_data=f"edit_{agr_id}")
                ])

    # По категориям
    for cat, items in groups.items():
        response += f"\n📂 *{cat}*\n"
        for i, (agr_id, text, is_done) in enumerate(items, start=1):
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

# Главное меню
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📋 Мой список"), KeyboardButton("📂 Категории")],
        [KeyboardButton("⏰ Напоминания"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("⭐ Премиум")]
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    create_user(user_id)
    await update.message.reply_text(
        f"Привет! Я бот-трекер «Договорился с собой».\n"
        "С моей помощью ты можешь записывать обещания, распределять их по категориям и получать напоминания.\n"
        "/menu — главное меню."
    )
    await menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add — быстро добавить обещание без категории\n"
        "/list — показать список\n"
        "/stats — твоя статистика\n"
        "/menu — меню\n"
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
    await update.message.reply_text(message, parse_mode="Markdown")

# Премиум: инфо и переключение
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
        f"• Статистика и экспорт\n\n"
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

# Проверка напоминаний (JobQueue)
async def check_reminders_job(context: ContextTypes.DEFAULT_TYPE):
    now = (datetime.utcnow() + MSK_OFFSET).strftime("%H:%M")
    users = get_users_with_reminders()
    for user_id, remind_time in users:
        if remind_time == now:
            agreements = get_agreements(user_id)
            if not agreements:
                continue
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

# Обработчик кнопок (включая категории)
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Категории
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
        import sqlite3
        from database import DB_NAME
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        await query.edit_message_text("Категория удалена. Обещания без категории.")
    elif data == "cat_back":
        await categories_menu(update, context)
        return

    # Обещания
    elif data.startswith("done_"):
        mark_done(int(data.split("_")[1]))
        await query.edit_message_text("✅ Отмечено выполненным!")
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

    # Если ждём название категории
    if context.user_data.get('awaiting_category_name'):
        del context.user_data['awaiting_category_name']
        if create_category(user_id, text):
            await update.message.reply_text(f"Категория «{text}» создана.")
        else:
            await update.message.reply_text("Категория с таким именем уже существует.")
        return

    # Если редактируем обещание
    if 'editing_agreement_id' in context.user_data:
        agr_id = context.user_data.pop('editing_agreement_id')
        update_agreement(agr_id, text)
        await update.message.reply_text(f"✏️ Изменено: \"{text}\"")
        t, m = build_list_message(user_id)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
        return

    # Кнопки меню
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
    elif text == "📊 Статистика":
        await stats_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    else:
        # Может быть, ожидается текст после выбора категории или обычное автосохранение
        if context.user_data.get('adding_agreement_no_cat'):
            del context.user_data['adding_agreement_no_cat']
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено (без категории): \"{text}\"")
        elif 'selected_category_id' in context.user_data:
            cat_id = context.user_data.pop('selected_category_id')
            add_agreement(user_id, text, category_id=cat_id)
            cat_name = dict(get_categories(user_id)).get(cat_id, "категория")
            await update.message.reply_text(f"✅ Сохранено в «{cat_name}»: \"{text}\"")
        else:
            # На всякий случай автосохранение без категории
            add_agreement(user_id, text)
            await update.message.reply_text(f"✅ Сохранено: \"{text}\" (без категории)")

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
    application.add_handler(CommandHandler("stats", stats_command))  # новая команда
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CallbackQueryHandler(add_category_callback, pattern="^addcat_"))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue.run_repeating(check_reminders_job, interval=60, first=10)
    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
