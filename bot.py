import logging
import os
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import init_db, add_agreement, get_agreements, mark_done, delete_agreement

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Токен из переменной окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ---------- Flask-сервер для "пинга" ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()
# ---------------------------------------------

# --- Главное меню с постоянной клавиатурой ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📋 Мой список")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("⭐ Премиум")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! Я бот-трекер «Договорился с собой».\n\n"
        "С моей помощью ты сможешь записывать свои обещания.\n"
        "Напиши /menu, чтобы открыть главное меню."
    )
    # Сразу покажем меню
    await menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Вот что я умею:\n"
        "/add - Добавить новое обещание\n"
        "/list - Показать все обещания с кнопками управления\n"
        "/menu - Главное меню\n"
        "/help - Показать эту справку\n"
        "/premium - Информация о премиум-возможностях"
    )
    await update.message.reply_text(help_text)

async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # Если вызвано через кнопку, текст "/add" — нужно пояснить пользователю
    if not context.args:
        await update.message.reply_text("Пожалуйста, напиши текст обещания после команды. Например: `/add Начать бегать по утрам`\n\nИли просто отправь сообщение с текстом обещания, и я сохраню его.")
        return
    agreement_text = " ".join(context.args)
    add_agreement(user_id, agreement_text)
    await update.message.reply_text(f"✅ Обещание сохранено: \"{agreement_text}\"")

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    agreements = get_agreements(user_id)
    if not agreements:
        await update.message.reply_text("У тебя пока нет ни одного обещания.")
        return

    response = "📝 **Твои обещания:**\n\n"
    keyboard = []
    for i, (agr_id, text, is_done) in enumerate(agreements, start=1):
        status = "✅" if is_done else "⬜"
        response += f"{i}. {status} {text}\n"
        if not is_done:
            keyboard.append([
                InlineKeyboardButton(f"✅ Выполнено ({i})", callback_data=f"done_{agr_id}"),
                InlineKeyboardButton(f"🗑 Удалить ({i})", callback_data=f"delete_{agr_id}")
            ])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(response, parse_mode="Markdown", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    action, agr_id = data.split("_")
    agr_id = int(agr_id)

    if action == "done":
        mark_done(agr_id)
        await query.edit_message_text(text="✅ Обещание отмечено как выполненное!")
    elif action == "delete":
        delete_agreement(agr_id)
        await query.edit_message_text(text="🗑 Обещание удалено.")
    else:
        await query.edit_message_text(text="Неизвестное действие.")

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "⭐ **Премиум-возможности** (скоро!):\n"
        "• Категории обещаний\n"
        "• Напоминания в заданное время\n"
        "• Подробная статистика\n"
        "• Экспорт данных\n"
        "• Безлимитное количество обещаний\n\n"
        "Сейчас идёт разработка. Следи за обновлениями!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Обработчик текстовых сообщений (для кнопок главного меню) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text

    if text == "➕ Новое обещание":
        # Просто подскажем, что нужно ввести /add с текстом
        await update.message.reply_text("Введи команду /add и текст обещания. Например:\n`/add Прочитать 20 страниц`", parse_mode="Markdown")
    elif text == "📋 Мой список":
        await list_agreements(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    else:
        # На любое другое сообщение можно попробовать сохранить как обещание
        # (если пользователь прислал просто текст без команды)
        user_id = update.effective_user.id
        add_agreement(user_id, text)
        await update.message.reply_text(f"✅ Обещание сохранено: \"{text}\"\nИспользуй /list для просмотра.")

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")

    application = Application.builder().token(BOT_TOKEN).build()
    init_db()

    # Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Обработчик обычных текстовых сообщений (для кнопок меню и прочего)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()