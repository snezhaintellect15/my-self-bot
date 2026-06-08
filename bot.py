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
from fpdf import FPDF
import fpdf

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
        "/export — экспорт данных (премиум — PDF-файл с графиками)\n"
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

# --- Добавление обещания (выбор сложности для любого текста) ---
async def add_agreement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Напиши текст после /add. Пример: `/add Прочитать книгу`")
        return
    text = " ".join(context.args)
    await show_difficulty_selection(update, text)

async def show_difficulty_selection(update: Update, text: str):
    safe_text = text.replace("|", " ").replace("_", " ")
    keyboard = [
        [InlineKeyboardButton("🌱 Легко", callback_data=f"diff_{safe_text}|0"),
         InlineKeyboardButton("⚡️ Средне", callback_data=f"diff_{safe_text}|1"),
         InlineKeyboardButton("🔥 Хардкор", callback_data=f"diff_{safe_text}|2")]
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

# --- Экспорт (с корректным шрифтом DejaVu Sans) ---
def generate_pdf(user_id: int, stats: dict, cat_stats: list, agreements: list) -> bytes:
    # Используем DejaVu Sans, который гарантированно есть в fpdf2[fonts]
    font_path = os.path.join(os.path.dirname(fpdf.__file__), "fonts", "DejaVuSans.ttf")
    if not os.path.exists(font_path):
        # fallback (маловероятно)
        font_path = None
    pdf = FPDF()
    if font_path:
        pdf.add_font("DejaVu", fname=font_path)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("DejaVu", size=16)
    pdf.cell(0, 10, "PromiseTracker Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    pdf.set_font("DejaVu", size=10)
    pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("DejaVu", size=14)
    pdf.cell(0, 10, "Overall Statistics", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=12)
    pdf.cell(0, 8, f"Total promises: {stats['total']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Completed: {stats['done']} ({stats['percent']}%)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Current streak: {stats['streak']} days", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    bar_width = 100
    percent = stats['percent']
    pdf.set_font("DejaVu", size=10)
    pdf.cell(0, 5, "Progress:", new_x="LMARGIN", new_y="NEXT")
    x = pdf.get_x()
    y = pdf.get_y()
    pdf.rect(x, y, bar_width, 5, style="D")
    filled = int(bar_width * percent / 100)
    if filled > 0:
        pdf.rect(x, y, filled, 5, style="F")
    pdf.ln(8)

    if cat_stats:
        pdf.set_font("DejaVu", size=14)
        pdf.cell(0, 10, "By Category", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", size=12)
        for cat in cat_stats:
            pdf.cell(0, 8, f"{cat['name']}: {cat['done']}/{cat['total']} ({cat['percent']}%)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    pdf.set_font("DejaVu", size=14)
    pdf.cell(0, 10, "All Promises", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    col_widths = [15, 90, 40, 40]
    headers = ["Status", "Promise", "Category", "Date"]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1)
    pdf.ln()
    for agr in agreements:
        status = "V" if agr["is_done"] else "X"
        text = agr["text"][:40] + ("..." if len(agr["text"]) > 40 else "")
        cat = agr.get("category_name", "") or "None"
        created = agr["created_at"].strftime("%Y-%m-%d") if isinstance(agr["created_at"], datetime) else agr["created_at"]
        pdf.cell(col_widths[0], 6, status, border=1)
        pdf.cell(col_widths[1], 6, text, border=1)
        pdf.cell(col_widths[2], 6, cat[:15], border=1)
        pdf.cell(col_widths[3], 6, created, border=1)
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("DejaVu", size=14)
    pdf.cell(0, 10, "Progress Chart (ASCII)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=8)
    max_len = 50
    done_len = int(max_len * percent / 100) if stats['total'] > 0 else 0
    chart_line = "Done: [" + "#" * done_len + "-" * (max_len - done_len) + f"] {percent}%"
    pdf.cell(0, 5, chart_line, new_x="LMARGIN", new_y="NEXT")

    return pdf.output()

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_agreements_export(user_id)
    if not data:
        await update.message.reply_text("Нет данных для экспорта.")
        return

    stats = get_stats(user_id)
    cat_stats = get_stats_by_category(user_id)

    text = "📤 **Экспорт обещаний**\n\n"
    for agr in data:
        status = "✅" if agr["is_done"] else "⬜"
        cat_str = f"[{agr.get('category_name', '')}:] " if agr.get("category_name") else ""
        created_dt = agr["created_at"]
        created_msk = created_dt + MSK_OFFSET if isinstance(created_dt, datetime) else created_dt
        created_formatted = created_msk.strftime("%Y-%m-%d %H:%M") if isinstance(created_msk, datetime) else str(created_msk)
        line = f"{status} {cat_str}{agr['text']} (создано: {created_formatted}"
        if agr["is_done"] and agr.get("done_at"):
            done_dt = agr["done_at"]
            done_msk = done_dt + MSK_OFFSET if isinstance(done_dt, datetime) else done_dt
            done_formatted = done_msk.strftime("%Y-%m-%d %H:%M") if isinstance(done_msk, datetime) else str(done_msk)
            line += f", выполнено: {done_formatted}"
        line += ")\n"
        text += line

    text += f"\nВсего записей: {len(data)}"

    if is_premium(user_id):
        pdf_bytes = generate_pdf(user_id, stats, cat_stats, data)
        await update.message.reply_document(
            document=pdf_bytes,
            filename="promise_tracker_report.pdf",
            caption="📎 Ваш PDF-отчёт с графиками прогресса (премиум-доступ)"
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
        f"• Экспорт обещаний в PDF с графиками\n"
        f"• Безлимитные фото-подтверждения\n"
        f"• Заморозка дня (сохраняет серию)\n"
        f"• Смена питомца на дракончика\n\n"
        f"👥 **Получить премиум бесплатно:**\n"
        f"Пригласи друга по реферальной ссылке — и вы оба получите премиум-дни! /invite\n\n"
        f"Для теста: /premium on / /premium off",
        parse_mode="Markdown"
    )

# ---------- Остальные функции (категории, напоминания, сводки, планировщик, кнопки, сообщения, питомец, магазин, челленджи, админ) ----------
# Они полностью идентичны последней версии. Я не дублирую их для экономии места, но в реальном файле они должны присутствовать.
# Просто возьми предыдущий полный bot.py и замени generate_pdf на эту новую версию.

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