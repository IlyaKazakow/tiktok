"""
Telegram бот для автомоечного сервиса с антикоррозийной защитой
"""

import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = "YOUR_BOT_TOKEN_HERE"

# Conversation states
START, CHOOSE_TYPE, NEW_CLASS, USED_SERVICES, CONFIRM, GET_NAME, GET_PHONE, CONTACT_METHOD = range(8)

# Car classes with prices (in rubles)
CAR_CLASSES = {
    "A": {"price": 28000, "description": "Мини-класс (до 3.6м)\nПримеры: Smart, Kia Picanto"},
    "B": {"price": 32000, "description": "Компакт-класс (3.6-4.1м)\nПримеры: VW Polo, Kia Rio, Solaris"},
    "C": {"price": 35000, "description": "Средний класс (4.1-4.4м)\nПримеры: VW Golf, Toyota Corolla"},
    "D": {"price": 40000, "description": "Бизнес-класс (4.4m+)\nПримеры: BMW 3, Mercedes, Camry"},
}

# Services
SERVICES = {
    "full": "Полный комплекс защиты",
    "rust": "Очистка от ржавчины",
    "coating": "Антикоррозийная обработка",
}

# Mercasol Body info
MERCASOL_INFO = """
🛡️ **Mercasol Body** — профессиональный состав для защиты днища и скрытых полостей
• Покрытие днища автомобиля
• Обработка арок (внешние и внутренние)
• Защита порогов и лонжеронов
• Герметизация дверей и капота
• Артикул: MB-100 (тестовый)
• Высокая адгезия, влагостойкость
"""


# ─── Обработчики ────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие и выбор типа авто"""
    user = update.effective_user

    welcome = f"""👋 Привет, {user.first_name}!

🚗 Добро пожаловать в сервис антикоррозийной защиты автомобилей!

Мы предлагаем:
• Профессиональную защиту от коррозии
• Обработку днища и скрытых полостей
• Восстановление кузова
• Фото/видео документацию работ

Выберите тип вашего автомобиля:"""

    keyboard = [
        [
            InlineKeyboardButton("🆕 Новое авто", callback_data="type_new"),
            InlineKeyboardButton("♻️ БУ авто", callback_data="type_used"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome, reply_markup=reply_markup)
    return CHOOSE_TYPE


async def choose_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора типа авто"""
    query = update.callback_query
    await query.answer()

    choice = query.data.split("_")[1]  # "new" или "used"
    context.user_data["car_type"] = choice

    if choice == "new":
        # Выбор класса для нового авто
        keyboard = [
            [
                InlineKeyboardButton(f"🅰️ Класс A\n{CAR_CLASSES['A']['description']}", callback_data="class_A"),
                InlineKeyboardButton(f"🅱️ Класс B\n{CAR_CLASSES['B']['description']}", callback_data="class_B"),
            ],
            [
                InlineKeyboardButton(f"🅲️ Класс C\n{CAR_CLASSES['C']['description']}", callback_data="class_C"),
                InlineKeyboardButton(f"🅳️ Класс D\n{CAR_CLASSES['D']['description']}", callback_data="class_D"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="🚗 Выберите класс вашего автомобиля:",
            reply_markup=reply_markup,
        )
        return NEW_CLASS

    else:  # used
        # Выбор услуг для БУ авто
        keyboard = [
            [InlineKeyboardButton(f"✓ {SERVICES['full']}", callback_data="service_full")],
            [InlineKeyboardButton(f"✓ {SERVICES['rust']}", callback_data="service_rust")],
            [InlineKeyboardButton(f"✓ {SERVICES['coating']}", callback_data="service_coating")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            text="🛠️ Какие услуги вас интересуют? (БУ авто)",
            reply_markup=reply_markup,
        )
        return USED_SERVICES


async def new_class_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Новое авто - класс выбран"""
    query = update.callback_query
    await query.answer()

    car_class = query.data.split("_")[1]  # A, B, C, D
    context.user_data["car_class"] = car_class

    price = CAR_CLASSES[car_class]["price"]

    details = f"""
✅ Выбран класс: **{car_class}** ({CAR_CLASSES[car_class]['description']})

💰 **Стоимость полного комплекса: {price:,} ₽**

📋 **Включено:**
1. Разборка необходимых элементов
2. Мойка кузова
3. Сушка
4. {MERCASOL_INFO}
5. Обработка скрытых полостей:
   • Лонжероны
   • Пороги
   • Двери
   • Капот
   • Крышка багажника
6. Финальная сушка
7. Сборка
8. Фото/видео документация каждого этапа

Готовы заказать? 📞
"""

    keyboard = [
        [
            InlineKeyboardButton("✅ Да, заказать", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Отмена", callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=details, reply_markup=reply_markup, parse_mode="Markdown")
    return CONFIRM


async def used_service_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """БУ авто - услуга выбрана"""
    query = update.callback_query
    await query.answer()

    service = query.data.split("_")[1]  # full, rust, coating
    context.user_data["service"] = service

    service_name = SERVICES[service]

    details = f"""
✅ Выбрана услуга: **{service_name}**

📋 **Описание:**
"""

    if service == "full":
        details += """Полный комплекс защиты включает:
• Разборка необходимых элементов
• Очистка кузова
• Обработка днища составом Mercasol Body
• Герметизация скрытых полостей
• Сушка и сборка
• Фото/видео документация

**💰 Цена обсуждается после осмотра автомобиля**"""

    elif service == "rust":
        details += """Очистка от ржавчины включает:
• Диагностика поражённых участков
• Механическая и химическая очистка
• Нанесение защитного покрытия
• Фото до/после

**💰 Цена обсуждается после осмотра автомобиля**"""

    else:  # coating
        details += """Антикоррозийная обработка включает:
• Нанесение защитного состава
• Обработка скрытых полостей
• Сушка и контроль качества
• Гарантия защиты

**💰 Цена обсуждается после осмотра автомобиля**"""

    keyboard = [
        [
            InlineKeyboardButton("✅ Продолжить", callback_data="continue_yes"),
            InlineKeyboardButton("❌ Отмена", callback_data="continue_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=details, reply_markup=reply_markup, parse_mode="Markdown")
    return CONFIRM


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение заказа - просим имя"""
    query = update.callback_query
    await query.answer()

    if "no" in query.data:
        await query.edit_message_text("❌ Заказ отменён. Можете начать заново с /start")
        return ConversationHandler.END

    # Спрашиваем имя
    await query.edit_message_text(
        "Как вас зовут? 👤",
    )

    return GET_NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем имя пользователя"""
    name = update.message.text
    context.user_data["name"] = name

    # Спрашиваем как связаться
    keyboard = [
        [
            InlineKeyboardButton("📱 Поделиться контактом", callback_data="contact_share"),
            InlineKeyboardButton("✏️ Ввести номер вручную", callback_data="contact_manual"),
        ],
        [
            InlineKeyboardButton("💬 Перейти в чат", callback_data="contact_chat"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Спасибо, {name}! 😊\n\n"
        "Как вы хотите связаться с нами?",
        reply_markup=reply_markup,
    )

    return CONTACT_METHOD


async def contact_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор способа связи"""
    query = update.callback_query
    await query.answer()

    method = query.data.split("_")[1]  # share, manual, chat

    if method == "share":
        # Предлагаем поделиться контактом
        keyboard = [[KeyboardButton("📱 Поделиться контактом", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await query.edit_message_text(
            "Нажмите кнопку ниже, чтобы поделиться номером телефона:"
        )
        await update.effective_chat.send_message(
            "👇",
            reply_markup=reply_markup,
        )
        return GET_PHONE

    elif method == "manual":
        # Просим ввести номер вручную
        await query.edit_message_text(
            "📞 Пожалуйста, введите ваш номер телефона:\n\n"
            "Формат: +7 (XXX) XXX-XX-XX или 89XXXXXXXXX"
        )
        return GET_PHONE

    else:  # chat
        # Отправляем в личный чат
        msg = f"""
✅ **Спасибо за заказ!**

👤 Имя: {context.user_data.get('name', 'N/A')}
🚗 Тип авто: {'Новое' if context.user_data.get('car_type') == 'new' else 'БУ'}
"""
        if context.user_data.get("car_type") == "new":
            msg += f"📊 Класс: {context.user_data.get('car_class', 'N/A')}\n"
            msg += f"💰 Цена: {CAR_CLASSES[context.user_data.get('car_class', 'A')]['price']:,} ₽\n"
        else:
            msg += f"🛠️ Услуга: {SERVICES.get(context.user_data.get('service', 'full'), 'N/A')}\n"

        msg += f"""
📍 Нам потребуется осмотреть автомобиль.
📅 Свяжемся с вами в ближайшее время!

💬 Наш чат: @auto_protect_chat
☎️ Телефон: +7-XXX-XXX-XX-XX
"""

        await query.edit_message_text(msg, parse_mode="Markdown")
        return ConversationHandler.END


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем номер телефона"""
    phone = None

    if update.message.contact:
        # Получили контакт через кнопку
        phone = update.message.contact.phone_number
    else:
        # Получили текст с номером
        phone = update.message.text

    context.user_data["phone"] = phone

    # Финальное сообщение
    msg = f"""
✅ **Спасибо за заказ!**

👤 Имя: {context.user_data.get('name', 'N/A')}
📞 Телефон: {phone}
🚗 Тип авто: {'Новое' if context.user_data.get('car_type') == 'new' else 'БУ'}
"""

    if context.user_data.get("car_type") == "new":
        msg += f"📊 Класс: {context.user_data.get('car_class', 'N/A')}\n"
        msg += f"💰 Цена: {CAR_CLASSES[context.user_data.get('car_class', 'A')]['price']:,} ₽\n"
    else:
        msg += f"🛠️ Услуга: {SERVICES.get(context.user_data.get('service', 'full'), 'N/A')}\n"

    msg += f"""
📝 Данные получены! Спасибо за заказ.
📅 Свяжемся с вами в ближайшее время!

💬 Наш чат: @auto_protect_chat
☎️ Телефон: +7-XXX-XXX-XX-XX
"""

    await update.message.reply_text(msg, parse_mode="Markdown")

    # Логируем данные (в боевом варианте - сохраняем в БД)
    logger.info(f"Заказ: {context.user_data}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена"""
    await update.message.reply_text("❌ Отменено. Введите /start для начала")
    return ConversationHandler.END


def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_TYPE: [CallbackQueryHandler(choose_type)],
            NEW_CLASS: [CallbackQueryHandler(new_class_selected)],
            USED_SERVICES: [CallbackQueryHandler(used_service_selected)],
            CONFIRM: [CallbackQueryHandler(confirm_order)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            CONTACT_METHOD: [CallbackQueryHandler(contact_method)],
            GET_PHONE: [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    # Run bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
