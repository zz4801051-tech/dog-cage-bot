import logging
import re
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получатели заявок (личка владельца + канал)
RECIPIENT_IDS = [
    7541459251,           # Ваш личный ID
    -1003517179980,       # ID канала
]

# Хранилище для напоминаний
reminder_data = {}  # {user_id: {"status": "waiting", "reminder_count": 0, "last_reminder": datetime, "start_time": datetime}}

# Состояния для квиза
(PORODA, SIZE, KOLESA, ZAMKI, TOP_TYPE, BOTTOM_TYPE, COLOR, MESSENGER, CONTACT) = range(9)
CONSULT_CONTACT = 99

# Клавиатуры
YES_NO_KEYBOARD = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True)
TOP_KEYBOARD = ReplyKeyboardMarkup([
    ["ЛДСП", "Влагостойкая фанера"],
    ["Решётка", "Выдвижные ящики"],
    ["Без верха"]
], resize_keyboard=True)
BOTTOM_KEYBOARD = ReplyKeyboardMarkup([
    ["Влагостойкая фанера", "ЛДСП"],
    ["Металлический поддон", "Без дна"]
], resize_keyboard=True)
COLOR_KEYBOARD = ReplyKeyboardMarkup([["Чёрный", "Белый", "Графит"]], resize_keyboard=True)
MESSENGER_KEYBOARD = ReplyKeyboardMarkup([["WhatsApp", "Telegram", "Viber"]], resize_keyboard=True)
SIZE_KEYBOARD = ReplyKeyboardMarkup([["❓ Не знаю размер, нужна консультация"]], resize_keyboard=True)
BACK_TO_MENU = ReplyKeyboardMarkup([["🏠 В главное меню"]], resize_keyboard=True)

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup([
    ["🔧 Подобрать клетку", "❓ Часто задаваемые вопросы"],
    ["📋 Этапы работы", "📞 Консультация менеджера"]
], resize_keyboard=True)

# Фото цветов
BLACK_PHOTO = "AgACAgIAAxkBAAEocihp07xov281HWldk3D_nD6qw4WgEwACoxhrG2BjmEqSpdMeGu72gAEAAwIAA3gAAzsE"
WHITE_PHOTO = "AgACAgIAAxkBAAEocixp07x2Cpp0FkPv_TpT1eE4VxApJAACpRhrG2BjmEpG9OshztQWEQEAAwIAA3gAAzsE"
GRAPHITE_PHOTO = "AgACAgIAAxkBAAEocipp07xvweObyIbUDcMpQJxnvt1GvQACpBhrG2BjmEoR9aTlxhwdGQEAAwIAA3gAAzsE"


async def send_reminder(application: Application, user_id: int, reminder_type: str):
    """Отправляет напоминание пользователю."""
    if user_id in reminder_data:
        user_info = reminder_data[user_id]
        if user_info["status"] == "waiting":
            user_info["reminder_count"] += 1
            user_info["last_reminder"] = datetime.now()
            
            if reminder_type == "short":
                text = (
                    "🐕 *Напоминание!*\n\n"
                    "Вы запускали бота, но ещё не подобрали клетку для своего питомца.\n\n"
                    "Хотите прямо сейчас подобрать идеальную клетку?\n\n"
                    "Нажмите «🔧 Подобрать клетку» в главном меню.\n\n"
                    "Мы ждём вас! 🏡"
                )
            else:  # long (7 days)
                text = (
                    "🐕 *Давно не виделись!*\n\n"
                    "Вы интересовались клеткой для своей собаки, но так и не подобрали её.\n\n"
                    "Может быть, сейчас самое время?\n\n"
                    "Нажмите «🔧 Подобрать клетку» — мы поможем выбрать идеальный домик для вашего питомца.\n\n"
                    "Ждём вас с нетерпением! ❤️"
                )
            
            try:
                await application.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=MAIN_MENU_KEYBOARD
                )
                logger.info(f"Напоминание ({reminder_type}) отправлено пользователю {user_id} (попытка {user_info['reminder_count']})")
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания {user_id}: {e}")


async def check_reminders(application: Application):
    """Фоновая задача для проверки и отправки напоминаний."""
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту
        now = datetime.now()
        
        for user_id, user_info in reminder_data.items():
            if user_info["status"] != "waiting":
                continue
            
            start_time = user_info.get("start_time")
            last_reminder = user_info.get("last_reminder", start_time)
            reminder_count = user_info.get("reminder_count", 0)
            
            # 1-е напоминание через 30 минут
            if reminder_count == 0 and now - start_time >= timedelta(minutes=30):
                await send_reminder(application, user_id, "short")
            
            # 2-е напоминание через 60 минут
            elif reminder_count == 1 and now - last_reminder >= timedelta(minutes=30):
                await send_reminder(application, user_id, "short")
            
            # 3-е напоминание через 7 дней
            elif reminder_count == 2 and now - start_time >= timedelta(days=7):
                await send_reminder(application, user_id, "long")


def validate_belarus_phone(phone: str) -> bool:
    """Проверяет белорусский номер телефона."""
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    return bool(re.match(r'^\+375\d{9}$', cleaned))


def normalize_phone(phone: str) -> str:
    """Приводит номер к формату +375XXXXXXXXX."""
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    if cleaned.startswith('+375') and len(cleaned) == 13:
        return cleaned
    if cleaned.startswith('8') and len(cleaned) == 11:
        return '+375' + cleaned[1:]
    return cleaned


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    # Записываем пользователя в систему напоминаний
    if user_id not in reminder_data:
        reminder_data[user_id] = {
            "status": "waiting",
            "reminder_count": 0,
            "start_time": datetime.now(),
            "last_reminder": None
        }
    
    await update.message.reply_text(
        "🐕 Добро пожаловать! Я помогу подобрать и заказать клетку для вашей собаки.\n\n"
        "Выберите нужный пункт в меню:",
        reply_markup=MAIN_MENU_KEYBOARD
    )
    return ConversationHandler.END


async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    faq_text = (
        "❓ *Часто задаваемые вопросы:*\n\n"
        "1️⃣ *Размеры клетки?* – зависят от породы. При заказе поможем подобрать.\n"
        "2️⃣ *Сроки изготовления?* – стандарт 5–7 дней, с выдвижными ящиками до 15 дней.\n"
        "3️⃣ *Доставка?* – по РБ к дому 1–2 дня.\n"
        "4️⃣ *Цена?* – зависит от размера и дизайна, уточнит менеджер.\n"
        "5️⃣ *Оплата?* – предоплата 30%, остальное при получении.\n"
        "6️⃣ *Материалы?* – ЛДСП, металл, фанера, мебельный щит.\n"
        "7️⃣ *Расстояние между прутьями?* – 7 см (стандарт), для маленьких – 3–5 см.\n"
        "8️⃣ *Цвета каркаса?* – чёрный, белый, графит (фото в квизе)."
    )
    await update.message.reply_text(faq_text, parse_mode="Markdown")


async def etapy_raboty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    etapy_text = (
        "📋 *Этапы работы:*\n\n"
        "1️⃣ *Консультация и замеры*\n"
        "2️⃣ *Выбор материалов и дизайна*\n"
        "3️⃣ *Согласование размеров*\n"
        "4️⃣ *Изготовление* – 5-7 дней\n"
        "5️⃣ *Доставка* – в разобранном виде"
    )
    await update.message.reply_text(etapy_text, parse_mode="Markdown")


async def consult_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📞 *Консультация менеджера*\n\n"
        "Менеджер свяжется с вами в ближайшее время.\n\n"
        "Оставьте ваш контакт:\n"
        "• +375XXXXXXXXX\n"
        "• или @username",
        parse_mode="Markdown",
        reply_markup=BACK_TO_MENU
    )
    return CONSULT_CONTACT


async def consult_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        await update.message.reply_text("Консультация отменена.", reply_markup=MAIN_MENU_KEYBOARD)
        return ConversationHandler.END

    contact = update.message.text.strip()
    if contact.startswith('@') or validate_belarus_phone(contact):
        if not contact.startswith('@'):
            contact = normalize_phone(contact)
        
        consult_text = f"📞 *ЗАПРОС КОНСУЛЬТАЦИИ*\n\nКонтакт: {contact}"
        for chat_id in RECIPIENT_IDS:
            await context.bot.send_message(chat_id=chat_id, text=consult_text, parse_mode="Markdown")
        
        await update.message.reply_text(
            "✅ Спасибо! Менеджер свяжется с вами.",
            reply_markup=MAIN_MENU_KEYBOARD
        )
    else:
        await update.message.reply_text(
            "❌ Неверный формат. Введите +375XXXXXXXXX или @username.",
            reply_markup=BACK_TO_MENU
        )
        return CONSULT_CONTACT
    
    return ConversationHandler.END


# ---------- КВИЗ ----------
async def quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    # Пользователь начал опрос — отключаем напоминания
    if user_id in reminder_data:
        reminder_data[user_id]["status"] = "in_progress"
    
    context.user_data.clear()
    await update.message.reply_text(
        "✏️ Начнём подбор клетки.\n\nКакая порода вашей собаки?",
        reply_markup=BACK_TO_MENU
    )
    return PORODA


async def poroda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    
    context.user_data["poroda"] = update.message.text
    await update.message.reply_text(
        "Укажите размеры (Д×Ш×В) в см. Пример: 100×70×80\n\n"
        "Если не знаете – нажмите кнопку ниже.",
        reply_markup=SIZE_KEYBOARD
    )
    return SIZE


async def size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Порода?", reply_markup=BACK_TO_MENU)
        return PORODA

    text = update.message.text
    if text == "❓ Не знаю размер, нужна консультация":
        context.user_data["size"] = "❌ Требуется консультация"
        context.user_data["need_consultation"] = True
    else:
        context.user_data["size"] = text
        context.user_data["need_consultation"] = False
    
    await update.message.reply_text("Нужны ли колесики?", reply_markup=YES_NO_KEYBOARD)
    return KOLESA


async def kolesa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Размеры:", reply_markup=SIZE_KEYBOARD)
        return SIZE
    
    context.user_data["kolesa"] = update.message.text
    await update.message.reply_text("Нужны ли замки?", reply_markup=YES_NO_KEYBOARD)
    return ZAMKI


async def zamki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Колесики?", reply_markup=YES_NO_KEYBOARD)
        return KOLESA
    
    context.user_data["zamki"] = update.message.text
    await update.message.reply_text("Тип верха:", reply_markup=TOP_KEYBOARD)
    return TOP_TYPE


async def top_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Замки?", reply_markup=YES_NO_KEYBOARD)
        return ZAMKI
    
    context.user_data["top_type"] = update.message.text
    await update.message.reply_text("Тип дна:", reply_markup=BOTTOM_KEYBOARD)
    return BOTTOM_TYPE


async def bottom_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Тип верха:", reply_markup=TOP_KEYBOARD)
        return TOP_TYPE
    
    context.user_data["bottom_type"] = update.message.text
    
    # Показываем фото цветов
    await update.message.reply_photo(BLACK_PHOTO, caption="⚫ Чёрный")
    await update.message.reply_photo(WHITE_PHOTO, caption="⚪ Белый")
    await update.message.reply_photo(GRAPHITE_PHOTO, caption="🔘 Графит")
    await update.message.reply_text("Выберите цвет каркаса:", reply_markup=COLOR_KEYBOARD)
    return COLOR


async def color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Тип дна:", reply_markup=BOTTOM_KEYBOARD)
        return BOTTOM_TYPE
    
    context.user_data["color"] = update.message.text
    await update.message.reply_text("Выберите мессенджер для связи:", reply_markup=MESSENGER_KEYBOARD)
    return MESSENGER


async def messenger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Цвет:", reply_markup=COLOR_KEYBOARD)
        return COLOR
    
    context.user_data["messenger"] = update.message.text
    await update.message.reply_text(
        "Укажите ваш контакт:\n• +375XXXXXXXXX\n• или @username",
        reply_markup=BACK_TO_MENU
    )
    return CONTACT


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    if update.message.text == "🏠 В главное меню":
        return await cancel(update, context)
    if update.message.text == "Назад":
        await update.message.reply_text("Мессенджер:", reply_markup=MESSENGER_KEYBOARD)
        return MESSENGER

    contact = update.message.text.strip()
    if contact.startswith('@') or validate_belarus_phone(contact):
        if not contact.startswith('@'):
            contact = normalize_phone(contact)
        
        context.user_data["contact"] = contact
        
        order_text = (
            "📦 *НОВАЯ ЗАЯВКА*\n\n"
            f"🐕 Порода: {context.user_data.get('poroda')}\n"
            f"📏 Размеры: {context.user_data.get('size')}\n"
            f"🛞 Колесики: {context.user_data.get('kolesa')}\n"
            f"🔒 Замки: {context.user_data.get('zamki')}\n"
            f"🔝 Верх: {context.user_data.get('top_type')}\n"
            f"🪵 Дно: {context.user_data.get('bottom_type')}\n"
            f"🎨 Цвет: {context.user_data.get('color')}\n"
            f"💬 Мессенджер: {context.user_data.get('messenger')}\n"
            f"📞 Контакт: {contact}\n"
        )
        if context.user_data.get("need_consultation"):
            order_text += "\n⚠️ *Нужна консультация по размерам!*"
        
        for chat_id in RECIPIENT_IDS:
            await context.bot.send_message(chat_id=chat_id, text=order_text, parse_mode="Markdown")
        
        # Пользователь успешно прошёл опрос — отключаем напоминания
        if user_id in reminder_data:
            reminder_data[user_id]["status"] = "completed"
        
        await update.message.reply_text(
            "✅ Заявка отправлена! Менеджер свяжется с вами.\n\nСпасибо! 🐾",
            reply_markup=MAIN_MENU_KEYBOARD
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный формат.\n\nВведите +375XXXXXXXXX или @username",
            reply_markup=BACK_TO_MENU
        )
        return CONTACT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    # Возвращаем статус waiting для напоминаний
    if user_id in reminder_data and reminder_data[user_id]["status"] == "in_progress":
        reminder_data[user_id]["status"] = "waiting"
    
    await update.message.reply_text("Отменено. Главное меню:", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END


async def handle_regular_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == "🔧 Подобрать клетку":
        await quiz_start(update, context)
    elif text == "❓ Часто задаваемые вопросы":
        await faq(update, context)
    elif text == "📋 Этапы работы":
        await etapy_raboty(update, context)
    elif text == "📞 Консультация менеджера":
        await consult_manager(update, context)
    else:
        await update.message.reply_text("Используйте кнопки меню.", reply_markup=MAIN_MENU_KEYBOARD)


def main():
    TOKEN = "8760250614:AAH4MUjhJi5G0L8ZzAWOnhCM4s5NkARYPlc"
    application = Application.builder().token(TOKEN).build()

    quiz_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔧 Подобрать клетку$"), quiz_start)],
        states={
            PORODA: [MessageHandler(filters.TEXT & ~filters.COMMAND, poroda)],
            SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, size)],
            KOLESA: [MessageHandler(filters.TEXT & ~filters.COMMAND, kolesa)],
            ZAMKI: [MessageHandler(filters.TEXT & ~filters.COMMAND, zamki)],
            TOP_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_type)],
            BOTTOM_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bottom_type)],
            COLOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, color)],
            MESSENGER: [MessageHandler(filters.TEXT & ~filters.COMMAND, messenger)],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    consult_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📞 Консультация менеджера$"), consult_manager)],
        states={CONSULT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, consult_contact)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("faq", faq))
    application.add_handler(quiz_conv)
    application.add_handler(consult_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_regular_messages))

    # Запускаем фоновую задачу для напоминаний
    loop = asyncio.get_event_loop()
    loop.create_task(check_reminders(application))

    application.run_polling()


if __name__ == "__main__":
    main()
