import logging
import html
import json
from datetime import datetime
from typing import Optional

from telegram import Update, User, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

import config
from database import db
from keyboards import get_main_keyboard, get_user_actions_keyboard, get_admin_keyboard

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
user_cache = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    # Сохраняем пользователя в базе данных
    await db.add_or_update_user(user)
    
    # Отправляем приветственное сообщение
    await update.message.reply_text(
        config.Config.START_MESSAGE,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        config.Config.HELP_MESSAGE,
        parse_mode='Markdown'
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /info"""
    user = update.effective_user
    target_user = None
    
    # Сохраняем пользователя в БД
    await db.add_or_update_user(user)
    
    # Проверяем, есть ли аргументы команды
    if context.args:
        # Пытаемся получить username из аргументов
        username = context.args[0].lstrip('@')
        try:
            # Пытаемся получить пользователя по username
            target_user = await context.bot.get_chat(f"@{username}")
        except Exception as e:
            await update.message.reply_text(f"❌ Пользователь @{username} не найден.")
            return
    
    # Проверяем, есть ли reply
    elif update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    
    # Если нет аргументов и reply, используем отправителя
    else:
        target_user = user
    
    # Получаем информацию о пользователе
    if target_user:
        info_text = await get_user_info_text(target_user)
        
        # Добавляем запрос в историю
        await db.add_request_to_history(
            from_user_id=user.id,
            target_user_id=target_user.id,
            target_username=target_user.username
        )
        
        # Отправляем информацию
        await update.message.reply_text(
            info_text,
            parse_mode='HTML',
            reply_markup=get_user_actions_keyboard(target_user.id),
            disable_web_page_preview=True
        )

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /myinfo"""
    user = update.effective_user
    
    # Сохраняем пользователя в БД
    await db.add_or_update_user(user)
    
    # Получаем информацию о пользователе
    info_text = await get_user_info_text(user)
    
    # Добавляем запрос в историю
    await db.add_request_to_history(
        from_user_id=user.id,
        target_user_id=user.id,
        target_username=user.username
    )
    
    await update.message.reply_text(
        info_text,
        parse_mode='HTML',
        reply_markup=get_user_actions_keyboard(user.id)
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /history"""
    user = update.effective_user
    
    # Получаем историю запросов
    history = await db.get_user_history(user.id, limit=config.Config.MAX_HISTORY_ITEMS)
    
    if not history:
        await update.message.reply_text("📭 История запросов пуста.")
        return
    
    # Формируем сообщение с историей
    history_text = "📜 *История ваших запросов:*\n\n"
    
    for i, item in enumerate(history, 1):
        target_user_id, target_username, request_date, first_name, last_name, username = item
        
        # Форматируем дату
        request_time = datetime.fromisoformat(request_date).strftime("%d.%m.%Y %H:%M")
        
        # Формируем имя пользователя
        if first_name or last_name:
            name = f"{first_name or ''} {last_name or ''}".strip()
        elif username:
            name = f"@{username}"
        else:
            name = f"Пользователь {target_user_id}"
        
        history_text += f"{i}. {name}\n"
        history_text += f"   🆔 `{target_user_id}`\n"
        history_text += f"   🕐 {request_time}\n"
        
        if i < len(history):
            history_text += "\n"
    
    await update.message.reply_text(
        history_text,
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats (только для админов)"""
    user = update.effective_user
    
    if user.id not in config.Config.ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    # Получаем статистику
    stats = await db.get_bot_statistics()
    top_users = await db.get_top_users(limit=5)
    
    # Формируем сообщение со статистикой
    stats_text = "📊 *Статистика бота:*\n\n"
    stats_text += f"👥 Всего пользователей: `{stats['total_users']}`\n"
    stats_text += f"📨 Всего запросов: `{stats['total_requests']}`\n"
    stats_text += f"📈 Запросов сегодня: `{stats['today_requests']}`\n\n"
    
    stats_text += "🏆 *Топ пользователей:*\n"
    for i, (user_id, username, first_name, last_name, request_count) in enumerate(top_users, 1):
        name = f"{first_name or ''} {last_name or ''}".strip() or f"@{username}" or f"ID: {user_id}"
        stats_text += f"{i}. {name}: `{request_count}` запросов\n"
    
    await update.message.reply_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=get_admin_keyboard()
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для рассылки сообщений"""
    user = update.effective_user
    
    if user.id not in config.Config.ADMIN_IDS:
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Использование: /broadcast текст_сообщения")
        return
    
    message_text = ' '.join(context.args)
    
    # Получаем всех пользователей
    all_users = await db.get_all_users()
    
    # Отправляем сообщение пользователям
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(f"🔄 Начинаю рассылку для {len(all_users)} пользователей...")
    
    for user_id, username, first_name in all_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Сообщение от администратора:*\n\n{message_text}",
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ Рассылка завершена!\n"
        f"📤 Отправлено: {sent_count}\n"
        f"❌ Не отправлено: {failed_count}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    
    # Если сообщение переслано
    if update.message.forward_from:
        target_user = update.message.forward_from
        
        # Получаем информацию о пользователе
        info_text = await get_user_info_text(target_user)
        
        # Добавляем запрос в историю
        await db.add_request_to_history(
            from_user_id=user.id,
            target_user_id=target_user.id,
            target_username=target_user.username
        )
        
        await update.message.reply_text(
            info_text,
            parse_mode='HTML',
            reply_markup=get_user_actions_keyboard(target_user.id)
        )
    
    # Если это ответ на сообщение
    elif update.message.reply_to_message and update.message.reply_to_message.from_user:
        # Проверяем, не запрашивает ли пользователь информацию через reply
        if update.message.text.lower() in ['инфо', 'info', 'who', 'кто']:
            target_user = update.message.reply_to_message.from_user
            
            info_text = await get_user_info_text(target_user)
            
            await db.add_request_to_history(
                from_user_id=user.id,
                target_user_id=target_user.id,
                target_username=target_user.username
            )
            
            await update.message.reply_text(
                info_text,
                parse_mode='HTML',
                reply_markup=get_user_actions_keyboard(target_user.id)
            )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    
    if data == "my_stats":
        # Получаем статистику пользователя
        history = await db.get_user_history(user.id, limit=5)
        
        if history:
            stats_text = f"📊 *Ваша статистика:*\n\n"
            stats_text += f"📨 Всего запросов: `{len(history)}`\n\n"
            stats_text += "📜 *Последние запросы:*\n"
            
            for i, item in enumerate(history[:3], 1):
                target_user_id, target_username, request_date, first_name, last_name, username = item
                name = f"{first_name or ''} {last_name or ''}".strip() or f"@{username}" or f"ID: {target_user_id}"
                stats_text += f"{i}. {name}\n"
            
            await query.edit_message_text(
                stats_text,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("📭 У вас пока нет истории запросов.")
    
    elif data == "refresh":
        # Обновляем информацию о пользователе
        await db.add_or_update_user(user)
        info_text = await get_user_info_text(user)
        
        await query.edit_message_text(
            info_text,
            parse_mode='HTML',
            reply_markup=get_user_actions_keyboard(user.id)
        )
    
    elif data.startswith("copy_id_"):
        # Копирование ID пользователя
        user_id = data.split("_")[2]
        await query.edit_message_text(
            f"🆔 ID пользователя: `{user_id}`\n\n"
            "✅ ID скопирован в буфер обмена",
            parse_mode='Markdown'
        )
    
    elif data == "help":
        await query.edit_message_text(
            config.Config.HELP_MESSAGE,
            parse_mode='Markdown'
        )
    
    elif data == "admin_stats":
        if user.id in config.Config.ADMIN_IDS:
            stats = await db.get_bot_statistics()
            stats_text = f"📊 *Статистика бота:*\n\n"
            stats_text += f"👥 Пользователей: `{stats['total_users']}`\n"
            stats_text += f"📨 Запросов: `{stats['total_requests']}`\n"
            stats_text += f"📈 Сегодня: `{stats['today_requests']}`"
            
            await query.edit_message_text(
                stats_text,
                parse_mode='Markdown'
            )
    
    elif data == "user_list":
        if user.id in config.Config.ADMIN_IDS:
            users = await db.get_all_users()
            
            if not users:
                await query.edit_message_text("📭 В базе данных нет пользователей.")
                return
            
            users_text = "👥 *Список пользователей:*\n\n"
            
            for i, (user_id, username, first_name) in enumerate(users[:20], 1):
                name = f"{first_name or ''}".strip() or f"@{username}" or f"ID: {user_id}"
                users_text += f"{i}. {name} (`{user_id}`)\n"
            
            if len(users) > 20:
                users_text += f"\n... и еще {len(users) - 20} пользователей"
            
            await query.edit_message_text(
                users_text,
                parse_mode='Markdown'
            )

async def get_user_info_text(user: User) -> str:
    """Формирование текста с информацией о пользователе"""
    
    # Экранируем HTML-спецсимволы
    def escape_html(text):
        return html.escape(str(text)) if text else ""
    
    # Основная информация
    info_text = "👤 <b>Информация о пользователе</b>\n\n"
    
    # ID
    info_text += f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
    
    # Имя и фамилия
    if user.first_name:
        info_text += f"👤 <b>Имя:</b> {escape_html(user.first_name)}\n"
    if user.last_name:
        info_text += f"📛 <b>Фамилия:</b> {escape_html(user.last_name)}\n"
    
    # Username
    if user.username:
        info_text += f"📱 <b>Username:</b> @{escape_html(user.username)}\n"
    else:
        info_text += "📱 <b>Username:</b> Не установлен\n"
    
    # Премиум
    info_text += f"⭐ <b>Премиум:</b> {'Да' if user.is_premium else 'Нет'}\n"
    
    # Бот
    info_text += f"🤖 <b>Бот:</b> {'Да' if user.is_bot else 'Нет'}\n"
    
    # Язык
    if user.language_code:
        info_text += f"🌐 <b>Язык:</b> {user.language_code.upper()}\n"
    
    # Примерное время регистрации (по ID)
    registration_date = await estimate_registration_date(user.id)
    info_text += f"📅 <b>Регистрация:</b> {registration_date}\n"
    
    # Текущее время
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    info_text += f"🕐 <b>Текущее время:</b> {current_time}\n\n"
    
    # Дополнительная информация
    info_text += "🔗 <b>Ссылки:</b>\n"
    info_text += f"• <a href='tg://user?id={user.id}'>Написать в ЛС</a>\n"
    info_text += f"• <a href='https://t.me/{user.username}'>Профиль в Telegram</a>\n" if user.username else ""
    
    return info_text

async def estimate_registration_date(user_id: int) -> str:
    """Оценка даты регистрации по ID пользователя"""
    # Telegram ID содержат временную метку
    # Упрощенная оценка (примерная)
    timestamp = (user_id >> 32) & 0xFFFFFFFF
    
    if timestamp > 0:
        try:
            reg_date = datetime.fromtimestamp(timestamp)
            return reg_date.strftime("%d.%m.%Y")
        except:
            pass
    
    # Если не удалось определить по ID
    return "Неизвестно"

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке запроса. Попробуйте позже."
            )
        except:
            pass

async def init_database():
    """Инициализация базы данных"""
    await db.create_tables()
    logger.info("База данных инициализирована")

def main():
    """Основная функция запуска бота"""
    # Проверка токена
    if not config.Config.BOT_TOKEN:
        logger.error("Токен бота не установлен! Проверьте файл .env")
        return
    
    # Создаем приложение
    application = Application.builder().token(config.Config.BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    # Добавляем обработчики сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_message
    ))
    
    # Добавляем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Инициализируем базу данных
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Инициализация перед запуском
    import asyncio
    asyncio.run(init_database())
    
    # Запускаем бота
    logger.info("Бот запускается...")
    main()