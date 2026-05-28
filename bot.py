import logging
import os
import asyncio
import time
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import (init_db, add_agreement, get_agreements, get_agreement_by_id,
                      mark_done, delete_agreement, update_agreement,
                      set_reminder, delete_reminder, get_reminder, get_users_with_reminders)

# Логирование с 24-часовым форматом времени
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MSK_OFFSET = timedelta(hours=3)

# ---------- Flask-сервер ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

@app.route('/check_reminders')
def check_reminders_route():
    """Вызывается cron-job'ом каждую минуту, чтобы проверить напоминания"""
    asyncio.run(async_check_reminders())
    return "OK"

async def async_check_reminders():
    now = (datetime.utcnow() + MSK_OFFSET).strftime("%H:%M")
    users = get_users_with_reminders()
    for user_id, remind_time in users:
        if remind_time == now:
            agreements = get_agreements(user_id)
            if not agreements:
                continue
            undone = [(agr_id, text) for agr_id, text, is_done in agreements if not is_done]
            if undone:
                message = "🔔 **Напоминание!** У тебя есть невыполненные обещания:\n\n"
                for _, text in undone:
                    message += f"⬜ {text}\n"
                message += "\nНе забудь их выполнить! /list"
                try:
                    await _app.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
                except Exception as e:
                    logging.error(f"Не удалось отправить напоминание пользователю {user_id}: {e}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()
# ---------------------------------

# ---------- Вспомогательная функция списка обещаний ----------
def build_list_message(user_id: int):
    agreements = get_agreements(user_id)
    if not agreements:
        return "У тебя пока нет ни одного обещания.", None

    response = "📝 **Твои обещания:**\n\n"
    keyboard = []
    for i, (agr_id, text, is_done) in enumerate(agreements, start=1):
        status = "✅" if is_done else "⬜"
        response += f"{i}. {status} {text}\n"
        if not is_done:
            keyboard.append([
                InlineKeyboardButton(f"✅ Выполнено ({i})", callback_data=f"done_{agr_id}"),
                InlineKeyboardButton(f"🗑 Удалить ({i})", callback_data=f"delete_{agr_id}"),
                InlineKeyboardButton(f"✏️ Изменить ({i})", callback_data=f"edit_{agr_id}")
            ])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    return response, reply_markup

# ---------- Главное меню ----------
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📋 Мой список")],
        [KeyboardButton("⏰ Напоминания"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("⭐ Премиум")]
    ]
    await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! Я бот-трекер «Договорился с собой».\n\n"
        "С моей помощью ты сможешь записывать свои обещания.\n"
        "/menu — главное меню, /remind — установить ежедневное напоминание."
    )
    await menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/add — добавить обещание\n"
        "/list — показать список с управлением\n"
        "/menu — главное меню\n"
        "/remind ЧЧ:ММ — ежедневное напоминание в указанное время\n"
        "/remind off — отключить напоминание\n"
        "/premium — информация о премиуме"
    )

async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Напиши текст после команды. Пример: `/add Прочитать 20 страниц`")
        return
    text = " ".join(context.args)
    add_agreement(user_id, text)
    await update.message.reply_text(f"✅ Сохранено: \"{text}\"")

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, markup = build_list_message(user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⭐ **Премиум-возможности** (в разработке):\n"
        "• Напоминания (в том числе несколько в день)\n"
        "• Категории\n• Статистика\n• Экспорт\n"
        "Пока можно бесплатно установить одно ежедневное напоминание через /remind",
        parse_mode="Markdown"
    )

# ---------- Напоминания ----------
async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        current = get_reminder(user_id)
        if current:
            await update.message.reply_text(f"Сейчас напоминание установлено на {current}. Измените: `/remind 20:00` или отключите: `/remind off`")
        else:
            await update.message.reply_text("Напоминание не установлено. Укажите время: `/remind 18:00`")
        return

    arg = context.args[0].strip().lower()
    if arg == "off":
        delete_reminder(user_id)
        await update.message.reply_text("🔕 Ежедневное напоминание отключено.")
        return

    try:
        datetime.strptime(arg, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Используйте ЧЧ:ММ, например 18:00")
        return

    set_reminder(user_id, arg)
    await update.message.reply_text(f"⏰ Ежедневное напоминание установлено на {arg}. Я проверю твои обещания в это время!")

# ---------- Обработчик кнопок ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("done_"):
        mark_done(int(data.split("_")[1]))
        await query.edit_message_text("✅ Обещание отмечено как выполненное!")
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
        await query.edit_message_text(f"Введите новый текст для «{agreement[1]}»:")
    elif data.startswith("confirm_delete_"):
        agr_id = int(data.split("_")[2])
        agreement = get_agreement_by_id(agr_id)
        if agreement:
            delete_agreement(agr_id)
            await query.edit_message_text(f"🗑 «{agreement[1]}» удалено.",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("📋 К списку", callback_data="show_list")
                                          ]]))
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

# ---------- Обработчик сообщений ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if 'editing_agreement_id' in context.user_data:
        agr_id = context.user_data.pop('editing_agreement_id')
        update_agreement(agr_id, text)
        await update.message.reply_text(f"✏️ Изменено: \"{text}\"")
        user_id = update.effective_user.id
        t, m = build_list_message(user_id)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
        return

    if text == "➕ Новое обещание":
        await update.message.reply_text("Напиши /add и текст обещания.")
    elif text == "📋 Мой список":
        uid = update.effective_user.id
        t, m = build_list_message(uid)
        await update.message.reply_text(t, parse_mode="Markdown", reply_markup=m)
    elif text == "⏰ Напоминания":
        uid = update.effective_user.id
        rem = get_reminder(uid)
        if rem:
            await update.message.reply_text(f"Напоминание установлено на {rem}. `/remind off` — отключить, `/remind 20:00` — изменить.")
        else:
            await update.message.reply_text("Напоминание не установлено. `/remind 18:00` — задать время.")
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    else:
        uid = update.effective_user.id
        add_agreement(uid, text)
        await update.message.reply_text(f"✅ Сохранено: \"{text}\"")

def main():
    global _app
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан")

    application = Application.builder().token(BOT_TOKEN).build()
    _app = application
    init_db()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    keep_alive()
    time.sleep(2)  # даём время Flask-серверу запуститься
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()