from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard():
    """Основная клавиатура"""
    keyboard = [
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("🔄 Обновить информацию", callback_data="refresh")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_user_actions_keyboard(user_id):
    """Клавиатура действий с пользователем"""
    keyboard = [
        [
            InlineKeyboardButton("📨 Написать", url=f"tg://user?id={user_id}"),
            InlineKeyboardButton("🆔 Копировать ID", callback_data=f"copy_id_{user_id}")
        ],
        [InlineKeyboardButton("📊 Статистика пользователя", callback_data=f"user_stats_{user_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard():
    """Клавиатура администратора"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="user_list")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")],
        [InlineKeyboardButton("🔄 Обновить кэш", callback_data="refresh_cache")]
    ]
    return InlineKeyboardMarkup(keyboard)