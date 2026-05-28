import logging
import os
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from database import init_db, add_agreement, get_agreements

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Токен теперь берём из переменной окружения (зададим на Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ---------- Flask-сервер для "пинга" ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает!"

def run_flask():
    # Порт Render передаёт в переменной PORT, по умолчанию 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()
# ---------------------------------------------

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! Я бот-трекер «Договорился с собой».\n\n"
        "С моей помощью ты сможешь записывать свои обещания.\n"
        "Напиши /help, чтобы узнать, что я умею."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Вот что я умею:\n"
        "/add - Добавить новое обещание\n"
        "/list - Показать все обещания\n"
        "/help - Показать эту справку"
    )
    await update.message.reply_text(help_text)

async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    agreement_text = " ".join(context.args)
    if not agreement_text:
        await update.message.reply_text("Пожалуйста, напиши текст обещания после команды. Например: `/add Начать бегать по утрам`")
        return
    add_agreement(user_id, agreement_text)
    await update.message.reply_text(f"✅ Обещание сохранено: \"{agreement_text}\"")

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    agreements = get_agreements(user_id)
    if not agreements:
        await update.message.reply_text("У тебя пока нет ни одного обещания.")
        return
    response = "📝 **Твои обещания:**\n\n"
    for i, (agr_id, text, is_done) in enumerate(agreements, start=1):
        status = "✅" if is_done else "⬜"
        response += f"{i}. {status} {text}\n"
    await update.message.reply_text(response, parse_mode="Markdown")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Я не знаю такой команды. Напиши /help, чтобы увидеть, что я умею.")

def main() -> None:
    # Проверяем, что токен задан
    if not BOT_TOKEN:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")
    
    # Создаём приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Инициализируем базу данных
    init_db()

    # Регистрируем хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    # Запускаем Flask-сервер в отдельном потоке
    keep_alive()
    
    # Запускаем бота (polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()