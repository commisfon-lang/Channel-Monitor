import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode

from config import config
from database import Database
from monitor import ChannelMonitor

logger = logging.getLogger(__name__)

class ManagementBot:
    def __init__(self, monitor: ChannelMonitor):
        self.monitor = monitor
        self.db = Database()
        self.application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Регистрируем обработчики
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настроить обработчики команд"""
        # Команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("channels", self.channels_command))
        self.application.add_handler(CommandHandler("filters", self.filters_command))
        self.application.add_handler(CommandHandler("add_channel", self.add_channel_command))
        self.application.add_handler(CommandHandler("add_target", self.add_target_command))
        self.application.add_handler(CommandHandler("add_filter", self.add_filter_command))
        
        # Callback-обработчики
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Обработчики сообщений
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
    
    async def start(self):
        """Запустить бота"""
        await self.application.initialize()
        await self.application.start()
        logger.info("Бот управления запущен")
    
    async def stop(self):
        """Остановить бота"""
        await self.application.stop()
        await self.application.shutdown()
    
    # Команды бота
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        if user_id not in config.ADMIN_IDS:
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Статистика", callback_data='stats'),
                InlineKeyboardButton("📋 Каналы", callback_data='channels')
            ],
            [
                InlineKeyboardButton("🎭 Фильтры", callback_data='filters'),
                InlineKeyboardButton("➕ Добавить канал", callback_data='add_channel')
            ],
            [
                InlineKeyboardButton("🎯 Целевые каналы", callback_data='targets'),
                InlineKeyboardButton("⚙️ Настройки", callback_data='settings')
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 <b>Бот мониторинга Telegram-каналов</b>\n\n"
            "Используйте кнопки ниже для управления:",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
<b>📖 Справка по командам:</b>

<b>Основные команды:</b>
/start - Главное меню
/stats - Статистика
/channels - Список каналов
/filters - Список фильтров

<b>Добавление:</b>
/add_channel - Добавить канал для отслеживания
/add_target - Добавить целевой канал
/add_filter - Добавить фильтр

<b>Формат фильтров:</b>
+слово - включать посты с этим словом
-слово - исключать посты с этим словом
/regex выражение - регулярное выражение

<b>Примеры:</b>
/add_channel @python_news
/add_filter +python
/add_filter -спам
        """
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        stats = self.db.get_statistics(days=7)
        
        text = f"""
<b>📊 Статистика за последние 7 дней:</b>

Всего отсканировано: {stats['total_scanned']}
Всего опубликовано: {stats['total_published']}

<b>По дням:</b>
"""
        for day_stat in stats['daily_stats'][:5]:  # Последние 5 дней
            date = day_stat['date']
            scanned = day_stat['total_scanned']
            published = day_stat['total_published']
            text += f"{date}: 📨 {scanned} | 📤 {published}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /channels"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        source_channels = self.db.get_source_channels(active_only=False)
        target_channels = self.db.get_target_channels(active_only=False)
        
        text = "<b>📋 Отслеживаемые каналы:</b>\n\n"
        
        for i, channel in enumerate(source_channels, 1):
            status = "✅" if channel['is_active'] else "❌"
            text += f"{i}. {status} {channel['title']}\n"
            if channel['username']:
                text += f"   @{channel['username']}\n"
            text += f"   ID: {channel['channel_id']}\n"
            text += f"   Последнее: {channel['last_scanned_id']}\n\n"
        
        text += "<b>🎯 Целевые каналы:</b>\n\n"
        
        for i, channel in enumerate(target_channels, 1):
            status = "✅" if channel['is_active'] else "❌"
            text += f"{i}. {status} {channel['title']}\n"
            if channel['username']:
                text += f"   @{channel['username']}\n"
            text += f"   ID: {channel['channel_id']}\n\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def filters_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /filters"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        filters = self.db.get_filters(active_only=False)
        
        text = "<b>🎭 Фильтры:</b>\n\n"
        
        for i, filter_item in enumerate(filters, 1):
            status = "✅" if filter_item['is_active'] else "❌"
            case = "Aa" if filter_item['is_case_sensitive'] else "a"
            filter_type = {
                'include': 'Включать',
                'exclude': 'Исключать',
                'regex': 'Regex'
            }.get(filter_item['filter_type'], filter_item['filter_type'])
            
            text += f"{i}. {status} {filter_type}: {filter_item['value']} [{case}]\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def add_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /add_channel"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /add_channel @username или ссылка на канал"
            )
            return
        
        channel_identifier = context.args[0]
        
        # Сохраняем в контекст для следующего шага
        context.user_data['adding_channel'] = channel_identifier
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f'confirm_add_{channel_identifier}'),
                InlineKeyboardButton("❌ Нет", callback_data='cancel_add')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"Добавить канал <code>{channel_identifier}</code> для отслеживания?",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def add_target_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /add_target"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /add_target @username или перешлите сообщение из канала"
            )
            return
        
        channel_identifier = context.args[0]
        
        # Для упрощения, просто добавляем
        try:
            # Здесь нужно получить информацию о канале
            # В реальности используйте forward_from_chat или подобное
            await update.message.reply_text(
                "Добавьте бота как администратора в канал, затем отправьте сообщение оттуда."
            )
            
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    async def add_filter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /add_filter"""
        user_id = update.effective_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "Использование: /add_filter [тип] [значение]\n"
                "Типы: + (включить), - (исключить), regex\n"
                "Примеры:\n"
                "/add_filter + python\n"
                "/add_filter - спам\n"
                "/add_filter regex python.*django"
            )
            return
        
        filter_type_char = context.args[0]
        value = " ".join(context.args[1:])
        
        # Определяем тип фильтра
        if filter_type_char == '+':
            filter_type = 'include'
        elif filter_type_char == '-':
            filter_type = 'exclude'
        elif filter_type_char.lower() == 'regex':
            filter_type = 'regex'
        else:
            await update.message.reply_text("Неверный тип фильтра. Используйте +, - или regex")
            return
        
        # Добавляем фильтр
        success = self.db.add_filter(
            name=f"Фильтр {filter_type}",
            filter_type=filter_type,
            value=value
        )
        
        if success:
            await update.message.reply_text(f"✅ Фильтр добавлен: {filter_type} '{value}'")
        else:
            await update.message.reply_text("❌ Ошибка при добавлении фильтра")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if user_id not in config.ADMIN_IDS:
            return
        
        data = query.data
        
        if data == 'stats':
            await self.stats_command(update, context)
        elif data == 'channels':
            await self.channels_command(update, context)
        elif data == 'filters':
            await self.filters_command(update, context)
        elif data.startswith('confirm_add_'):
            channel_identifier = data.replace('confirm_add_', '')
            try:
                success = await self.monitor.add_channel(channel_identifier)
                if success:
                    await query.edit_message_text(f"✅ Канал {channel_identifier} добавлен")
                else:
                    await query.edit_message_text(f"❌ Ошибка при добавлении канала")
            except Exception as e:
                await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
        elif data == 'cancel_add':
            await query.edit_message_text("❌ Добавление отменено")
        elif data == 'targets':
            target_channels = self.db.get_target_channels()
            text = "<b>🎯 Целевые каналы:</b>\n\n"
            for i, channel in enumerate(target_channels, 1):
                text += f"{i}. {channel['title']}\n"
                if channel['username']:
                    text += f"   @{channel['username']}\n"
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        elif data == 'settings':
            await query.edit_message_text(
                "⚙️ <b>Настройки:</b>\n\n"
                "Измените настройки в файле .env",
                parse_mode=ParseMode.HTML
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        # Обработка пересланных сообщений для добавления каналов
        if update.message.forward_from_chat:
            chat = update.message.forward_from_chat
            if chat.type == 'channel':
                await update.message.reply_text(
                    f"Канал: {chat.title}\n"
                    f"Username: @{chat.username}\n"
                    f"ID: {chat.id}\n\n"
                    f"Добавить для отслеживания? Используйте /add_channel @{chat.username}"
                )
