import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ваш токен
TOKEN = "8455579686:AAFV9mGYG_cIraCM6pFY66MBzDh4wkjRKvQ"
# ---------- ОБРАБОТЧИК /start ----------
async def start(update: Update, context: CallbackContext) -> None:
    welcome_text = (
        "Здравствуйте!👋🏻\n"
        "Перед началом работы ознакомьтесь с информацией <a href='https://everyjob.ru/welcomepartners'>на сайте </a> "
        "и подтвердите согласие на документы 🗂\n\n"
        "📂 <a href='https://drive.google.com/file/d/1f4jOFz9Ezo0tRe1RcHWZXf5YZqaX05RG/view?usp=sharing'>Правила сервиса</a>\n"
        "📂 <a href='https://drive.google.com/file/d/1IWtjBwaaKdJ3zy5hLLT636nVTYTeJVsK/view?usp=sharing'>Публичная оферта</a>\n"
        "📂 <a href='https://drive.google.com/file/d/1IWtjBwaaKdJ3zy5hLLT636nVTYTeJVsK/view?usp=sharing'>Оферта на чат-бот</a>\n"
        "📂 <a href='https://drive.google.com/file/d/1_8XIB0jVy3HIk1nAzpGoWrLuFbSfkuzI/view?usp=sharing'>Политика конфиденциальности и обработки данных</a>\n"
        "📂 <a href='https://drive.google.com/file/d/1MhT7MtvnI0D4rHpvRgyWxNRZfjL_mZlG/view?usp=sharing'>Согласие на обработку персональных данных</a>\n\n"
        "• Для подтверждения нажмите кнопку <u><b><i>Подтверждаю документы</i></b></u> \n"
        "• По любым вопросам обращайтесь к куратору партнерского отдела по кнопке <u><b><i>Обратиться к куратору</i></b></u>" )
    
    # Кнопка подтверждения
    keyboard = [
    [InlineKeyboardButton("Подтверждаю документы", callback_data='confirm_docs')],
    [InlineKeyboardButton("Обратиться к куратору", url="https://t.me/m/JaGJY3vvNTdi")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=reply_markup,
        parse_mode='HTML',
        disable_web_page_preview=False
    )

# ---------- ОБРАБОТЧИК НАЖАТИЙ НА КНОПКИ ----------
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'confirm_docs':
        # Документы подтверждены (курсивом)
        await query.message.reply_text("_Документы подтверждены_ ✔️ \n"
                                       "Еще немного и вы готовы к изучению материалов и полноценной работе", parse_mode='Markdown')
        
        # Следующий шаг - регистрация
        reg_text = (
            "Следующий шаг - <b>регистрация в партнерском кабинете.</b>\n"
            "<b>После регистрации потребуется подтверждение.</b> \n"
            "Поэтому, пожалуйста, вернитесь в чат и нажмите <u><b><i>Я зарегистрировался</i></b></u> \n"
            "Если что-то не получилось - ничего страшного.\n"
            "Нажмите <u><b><i>Не получилось зарегистрироваться</i></b></u>"
        )
        
        # Кнопка с ССЫЛКОЙ на регистрацию
        keyboard = [[
            InlineKeyboardButton(
                "Пройти регистрацию", 
                url="https://partners-app.yandex.ru/team_ref/b31c762ac7e54db383acc4423dfe6b86?locale=ru")],
                [InlineKeyboardButton("Я зарегистрировался и жду активацию", callback_data='registered_waiting')],
                [InlineKeyboardButton("Не получилось зарегистрироваться", url="https://t.me/m/fuvfwIcDZmNi")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(reg_text, reply_markup=reply_markup, parse_mode='HTML')
        
        # После нажатия на кнопку-ссылку показываем выбор варианта
       
        
        # Кнопки выбора варианта
        keyboard = [
            [InlineKeyboardButton("Я зарегистрировался и жду активацию", callback_data='registered_waiting')],
            [InlineKeyboardButton("Не получилось зарегистрироваться", callback_data='registration_failed')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
       
    
    elif data == 'registered_waiting':
        # Инструкция по базе знаний
        instruction_text = (
            "И последнее - <b>Ознакомьтесь с нашей базой знаний по кнопке ниже.</b> \n"
            "На странице авторизации нажмите зарегистрироваться, введите имя, почту и пароль.\n"
            "<b>После регистрации потребуется подтверждение.</b>\n"
            "Поэтому, пожалуйста, вернитесь в чат и нажмите <u><b><i>Я зарегистрировался в Базе знаний</i></b></u> \n"
            "Если что-то не получилось - ничего страшного.\n"
            "Нажмите <u><b><i>Не получилось зарегистрироваться</i></b></u>"
        )
        
        # Кнопка с ССЫЛКОЙ на базу знаний
        keyboard = [
                   [InlineKeyboardButton("База знаний", url="https://everyjob.ru/members/courses/library")],
                   [InlineKeyboardButton("Я зарегистрировался в Базе знаний и жду активацию", url="https://t.me/m/Ly1aUdIpMGUy")],
                   [InlineKeyboardButton("Не получилось зарегистрироваться", url="https://t.me/m/ejiILQwuYTAy")]

]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(instruction_text, reply_markup=reply_markup,
        parse_mode='HTML')
        
        # После нажатия на кнопку-ссылку показываем выбор варианта
        
        
        # Кнопки для базы знаний
        keyboard = [
            [
                InlineKeyboardButton(
                    "Я зарегистрировался в Базе Знаний и жду подтверждения", 
                    url="https://t.me/m/Ly1aUdIpMGUy"
                )
            ],
            [
                InlineKeyboardButton(
                    "Не получилось зарегистироваться", 
                    url="https://t.me/m/ejiILQwuYTAy"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
            
    elif data == 'registration_failed':
        # Кнопка с ССЫЛКОЙ для тех, у кого не получилось
        keyboard = [[
            InlineKeyboardButton(
                "Не получилось зарегистрироваться", 
                url="https://t.me/m/fuvfwIcDZmNi"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)


# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------
def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН!")
    print("Команда для начала: /start")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
