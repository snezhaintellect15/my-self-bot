import logging
import os
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from database import init_db, add_agreement, get_agreements, get_agreement_by_id, mark_done, delete_agreement, update_agreement

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

# ---------- Вспомогательная функция для формирования списка ----------
def build_list_message(user_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    """Возвращает текст списка и inline-клавиатуру (или None)"""
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
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [KeyboardButton("➕ Новое обещание")],
        [KeyboardButton("📋 Мой список")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("⭐ Премиум")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)

# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"Привет, {user_name}! Я бот-трекер «Договорился с собой».\n\n"
        "С моей помощью ты сможешь записывать свои обещания.\n"
        "Напиши /menu, чтобы открыть главное меню."
    )
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
    if not context.args:
        await update.message.reply_text(
            "Пожалуйста, напиши текст обещания после команды. Например: `/add Начать бегать по утрам`\n\n"
            "Или просто отправь сообщение с текстом обещания, и я сохраню его."
        )
        return
    agreement_text = " ".join(context.args)
    add_agreement(user_id, agreement_text)
    await update.message.reply_text(f"✅ Обещание сохранено: \"{agreement_text}\"")

async def list_agreements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text, reply_markup = build_list_message(user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

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

# ---------- Обработчик кнопок ----------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # Кнопка "Выполнено"
    if data.startswith("done_"):
        agr_id = int(data.split("_")[1])
        mark_done(agr_id)
        await query.edit_message_text("✅ Обещание отмечено как выполненное!")

    # Кнопка "Удалить" – запрос подтверждения
    elif data.startswith("delete_"):
        agr_id = int(data.split("_")[1])
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено.")
            return
        text = agreement[1]
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{agr_id}"),
                InlineKeyboardButton("❌ Нет, оставить", callback_data=f"cancel_delete_{agr_id}")
            ]
        ]
        await query.edit_message_text(
            f"Удалить обещание «{text}»?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # Кнопка "Изменить" – запрос нового текста
    elif data.startswith("edit_"):
        agr_id = int(data.split("_")[1])
        agreement = get_agreement_by_id(agr_id)
        if not agreement:
            await query.edit_message_text("Обещание не найдено.")
            return
        # Запоминаем, что пользователь редактирует это обещание
        context.user_data['editing_agreement_id'] = agr_id
        await query.edit_message_text(
            f"Введите новый текст для обещания «{agreement[1]}».\n"
            "Отправьте следующее сообщение — оно полностью заменит старую формулировку."
        )

    # Подтверждение удаления
    elif data.startswith("confirm_delete_"):
        agr_id = int(data.split("_")[2])
        agreement = get_agreement_by_id(agr_id)
        if agreement:
            delete_agreement(agr_id)
            await query.edit_message_text(f"🗑 Обещание «{agreement[1]}» удалено.",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("📋 Вернуться к списку", callback_data="show_list")
                                          ]]))
        else:
            await query.edit_message_text("Обещание уже удалено.")

    # Отмена удаления – возврат к списку
    elif data.startswith("cancel_delete_"):
        user_id = query.from_user.id
        text, reply_markup = build_list_message(user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    # Кнопка "Вернуться к списку"
    elif data == "show_list":
        user_id = query.from_user.id
        text, reply_markup = build_list_message(user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# ---------- Обработчик обычных сообщений ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text

    # Проверяем, не ожидается ли ввод нового текста для редактирования
    if 'editing_agreement_id' in context.user_data:
        agr_id = context.user_data.pop('editing_agreement_id')  # удаляем флаг после использования
        update_agreement(agr_id, text)
        await update.message.reply_text(f"✏️ Обещание изменено: \"{text}\"")
        # Покажем обновлённый список
        user_id = update.effective_user.id
        list_text, reply_markup = build_list_message(user_id)
        await update.message.reply_text(list_text, parse_mode="Markdown", reply_markup=reply_markup)
        return

    # Обработка кнопок главного меню
    if text == "➕ Новое обещание":
        await update.message.reply_text(
            "Введи команду /add и текст обещания. Например:\n`/add Прочитать 20 страниц`",
            parse_mode="Markdown"
        )
    elif text == "📋 Мой список":
        user_id = update.effective_user.id
        list_text, reply_markup = build_list_message(user_id)
        await update.message.reply_text(list_text, parse_mode="Markdown", reply_markup=reply_markup)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "⭐ Премиум":
        await premium_info(update, context)
    else:
        # Автосохранение любого другого текста как нового обещания
        user_id = update.effective_user.id
        add_agreement(user_id, text)
        await update.message.reply_text(f"✅ Обещание сохранено: \"{text}\"\nИспользуй /list для просмотра.")

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")

    application = Application.builder().token(BOT_TOKEN).build()
    init_db()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_agreement_command))
    application.add_handler(CommandHandler("list", list_agreements))
    application.add_handler(CommandHandler("premium", premium_info))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    keep_alive()
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()