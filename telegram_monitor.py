#!/usr/bin/env python3
"""
Telegram Channel Monitor Bot - упрощенная версия
Запуск: python telegram_monitor.py
"""

import asyncio
import logging
import sqlite3
import json
import re
import os
from datetime import datetime
from typing import Optional, Dict, List, Any

# Импорты библиотек
try:
    from telethon import TelegramClient, events
    from telethon.tl.types import Channel, Message
    from telethon.errors import FloodWaitError
    from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
    from telegram.constants import ParseMode
    from telegram.error import TelegramError, RetryAfter
except ImportError:
    print("Установите необходимые библиотеки:")
    print("pip install python-telegram-bot telethon python-dotenv")
    exit(1)

# ============================================================================
# КОНФИГУРАЦИЯ (можно менять через переменные окружения)
# ============================================================================

class Config:
    # Telegram API (получить на https://my.telegram.org)
    API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
    API_HASH = os.getenv('TELEGRAM_API_HASH', '')
    
    # Бот токен (получить у @BotFather)
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # ID администраторов (через запятую)
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
    
    # Настройки приложения
    SESSION_NAME = os.getenv('TELEGRAM_SESSION', 'telegram_monitor')
    DB_PATH = os.getenv('DB_PATH', 'telegram_bot.db')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))
    
    # Фильтры по умолчанию (через запятую)
    DEFAULT_INCLUDE_FILTERS = os.getenv('INCLUDE_FILTERS', '').split(',')
    DEFAULT_EXCLUDE_FILTERS = os.getenv('EXCLUDE_FILTERS', 'реклама,спам,купить,продам').split(',')

# ============================================================================
# БАЗА ДАННЫХ SQLite
# ============================================================================

class Database:
    def __init__(self, db_path='telegram_bot.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Отслеживаемые каналы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE,
                    username TEXT,
                    title TEXT,
                    invite_link TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Целевые каналы
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS target_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE,
                    username TEXT,
                    title TEXT,
                    invite_link TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Фильтры
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filter_type TEXT CHECK(filter_type IN ('include', 'exclude')),
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Опубликованные посты
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS published_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_channel_id INTEGER,
                    source_message_id INTEGER,
                    target_channel_id INTEGER,
                    published_message_id INTEGER,
                    publish_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_channel_id, source_message_id, target_channel_id)
                )
            ''')
            
            # Добавляем фильтры по умолчанию, если их нет
            cursor.execute("SELECT COUNT(*) FROM filters")
            if cursor.fetchone()[0] == 0:
                for value in Config.DEFAULT_INCLUDE_FILTERS:
                    if value:
                        cursor.execute(
                            "INSERT INTO filters (filter_type, value) VALUES ('include', ?)",
                            (value.strip(),)
                        )
                for value in Config.DEFAULT_EXCLUDE_FILTERS:
                    if value:
                        cursor.execute(
                            "INSERT INTO filters (filter_type, value) VALUES ('exclude', ?)",
                            (value.strip(),)
                        )
            
            conn.commit()
    
    def add_source_channel(self, channel_id, username, title, invite_link=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO source_channels 
                (channel_id, username, title, invite_link) 
                VALUES (?, ?, ?, ?)
            ''', (channel_id, username, title, invite_link))
            return cursor.lastrowid
    
    def get_source_channels(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM source_channels WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    def add_target_channel(self, channel_id, username, title, invite_link=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO target_channels 
                (channel_id, username, title, invite_link) 
                VALUES (?, ?, ?, ?)
            ''', (channel_id, username, title, invite_link))
            return cursor.lastrowid
    
    def get_target_channels(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM target_channels WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    def add_filter(self, filter_type, value):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO filters (filter_type, value) VALUES (?, ?)",
                (filter_type, value)
            )
            return cursor.lastrowid
    
    def get_filters(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM filters")
            return [dict(row) for row in cursor.fetchall()]
    
    def add_published_post(self, source_channel_id, source_message_id, target_channel_id, published_message_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO published_posts 
                    (source_channel_id, source_message_id, target_channel_id, published_message_id)
                    VALUES (?, ?, ?, ?)
                ''', (source_channel_id, source_message_id, target_channel_id, published_message_id))
                return True
            except sqlite3.IntegrityError:
                return False  # Пост уже опубликован
    
    def is_post_published(self, source_channel_id, source_message_id, target_channel_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM published_posts 
                WHERE source_channel_id = ? 
                AND source_message_id = ? 
                AND target_channel_id = ?
            ''', (source_channel_id, source_message_id, target_channel_id))
            return cursor.fetchone() is not None

# ============================================================================
# ОСНОВНОЙ КЛАСС БОТА
# ============================================================================

class TelegramMonitorBot:
    def __init__(self):
        self.config = Config
        self.db = Database(self.config.DB_PATH)
        self.monitor = None
        self.bot = None
        self.app = None
        self.logger = self.setup_logging()
        
        # Проверка конфигурации
        self.check_config()
    
    def setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    def check_config(self):
        """Проверка обязательных настроек"""
        if not self.config.API_ID or not self.config.API_HASH:
            self.logger.error("API_ID и API_HASH не установлены!")
            self.logger.error("Получите их на https://my.telegram.org")
            self.logger.error("И установите в переменные окружения:")
            self.logger.error("export TELEGRAM_API_ID=ваш_id")
            self.logger.error("export TELEGRAM_API_HASH=ваш_hash")
            exit(1)
        
        if not self.config.BOT_TOKEN:
            self.logger.error("BOT_TOKEN не установлен!")
            self.logger.error("Получите у @BotFather в Telegram")
            self.logger.error("И установите в переменные окружения:")
            self.logger.error("export TELEGRAM_BOT_TOKEN=ваш_токен")
            exit(1)
        
        if not self.config.ADMIN_IDS:
            self.logger.warning("ADMIN_IDS не установлены! Бот будет доступен всем")
    
    def check_message_filters(self, text: str) -> bool:
        """Проверить сообщение по фильтрам"""
        if not text:
            return False
        
        filters = self.db.get_filters()
        text_lower = text.lower()
        
        # Проверяем включающие фильтры
        include_filters = [f['value'].lower() for f in filters if f['filter_type'] == 'include']
        if include_filters:
            if not any(filt in text_lower for filt in include_filters):
                return False
        
        # Проверяем исключающие фильтры
        exclude_filters = [f['value'].lower() for f in filters if f['filter_type'] == 'exclude']
        if exclude_filters:
            if any(filt in text_lower for filt in exclude_filters):
                return False
        
        return True
    
    async def format_message(self, message, source_channel) -> str:
        """Форматировать сообщение для публикации"""
        parts = []
        
        # Источник
        if source_channel.get('title'):
            if source_channel.get('username'):
                parts.append(f"📢 <b>Из:</b> <a href='https://t.me/{source_channel['username']}'>{source_channel['title']}</a>")
            else:
                parts.append(f"📢 <b>Из:</b> {source_channel['title']}")
        
        # Текст сообщения
        text = message.text or message.caption or ""
        if text:
            # Обрезаем длинный текст
            if len(text) > 3500:
                text = text[:3500] + "..."
            parts.append(text)
        
        # Хештеги
        hashtags = re.findall(r'#\w+', text)
        if hashtags:
            parts.append(" ".join(set(hashtags)[:3]))
        
        # Ссылка на оригинал
        if source_channel.get('username') and message.id:
            parts.append(f"🔗 <a href='https://t.me/{source_channel['username']}/{message.id}'>Оригинал</a>")
        
        # Время
        if message.date:
            time_str = message.date.strftime("%d.%m.%Y %H:%M")
            parts.append(f"🕐 {time_str}")
        
        return "\n\n".join(parts)
    
    async def publish_message(self, message, source_channel_info) -> bool:
        """Опубликовать сообщение во все целевые каналы"""
        try:
            target_channels = self.db.get_target_channels()
            if not target_channels:
                self.logger.warning("Нет целевых каналов для публикации")
                return False
            
            caption = await self.format_message(message, source_channel_info)
            success_count = 0
            
            for target in target_channels:
                # Проверяем, не публиковали ли уже
                if self.db.is_post_published(message.chat.id, message.id, target['channel_id']):
                    self.logger.debug(f"Пост уже опубликован в канале {target['title']}")
                    continue
                
                try:
                    # Определяем тип сообщения и отправляем
                    if message.photo:
                        # Отправляем фото
                        sent = await self.bot.send_photo(
                            chat_id=target['channel_id'],
                            photo=message.photo[-1].file_id,  # Самое качественное
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                    elif message.video:
                        # Отправляем видео
                        sent = await self.bot.send_video(
                            chat_id=target['channel_id'],
                            video=message.video.file_id,
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                    elif message.document:
                        # Отправляем документ
                        sent = await self.bot.send_document(
                            chat_id=target['channel_id'],
                            document=message.document.file_id,
                            caption=caption,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        # Только текст
                        sent = await self.bot.send_message(
                            chat_id=target['channel_id'],
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True
                        )
                    
                    # Сохраняем в базу
                    if sent:
                        self.db.add_published_post(
                            source_channel_id=message.chat.id,
                            source_message_id=message.id,
                            target_channel_id=target['channel_id'],
                            published_message_id=sent.message_id
                        )
                        success_count += 1
                        self.logger.info(f"Опубликовано в {target['title']}")
                    
                except Exception as e:
                    self.logger.error(f"Ошибка публикации в {target['title']}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Ошибка при публикации: {e}")
            return False
    
    async def process_new_message(self, event, channel_info):
        """Обработать новое сообщение из канала"""
        try:
            message = event.message
            
            # Проверяем что это канал
            if not isinstance(message.chat, Channel):
                return
            
            # Проверяем текст по фильтрам
            text = message.text or message.caption or ""
            if not self.check_message_filters(text):
                self.logger.debug(f"Сообщение не прошло фильтрацию: {message.id}")
                return
            
            # Публикуем сообщение
            await self.publish_message(message, channel_info)
            
        except Exception as e:
            self.logger.error(f"Ошибка обработки сообщения: {e}")
    
    async def setup_monitor(self):
        """Настроить мониторинг каналов"""
        self.logger.info("Настройка мониторинга каналов...")
        
        # Создаем клиент Telethon
        self.monitor = TelegramClient(
            self.config.SESSION_NAME,
            self.config.API_ID,
            self.config.API_HASH
        )
        
        await self.monitor.start()
        
        # Настраиваем обработчики для каждого канала
        channels = self.db.get_source_channels()
        for channel in channels:
            try:
                entity = await self.monitor.get_entity(channel['channel_id'])
                
                @self.monitor.on(events.NewMessage(chats=entity))
                async def handler(event):
                    await self.process_new_message(event, channel)
                
                self.logger.info(f"Мониторинг канала: {channel['title']}")
                
            except Exception as e:
                self.logger.error(f"Ошибка настройки канала {channel['title']}: {e}")
    
    # ============================================================================
    # КОМАНДЫ ТЕЛЕГРАМ БОТА
    # ============================================================================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        
        # Проверка прав администратора
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
            [InlineKeyboardButton("📋 Каналы", callback_data='channels')],
            [InlineKeyboardButton("🎭 Фильтры", callback_data='filters')],
            [InlineKeyboardButton("➕ Добавить канал", callback_data='add_channel')],
            [InlineKeyboardButton("🎯 Добавить целевой канал", callback_data='add_target')],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 <b>Telegram Channel Monitor Bot</b>\n\n"
            "Я мониторю каналы и перепубликую посты в ваши каналы.\n"
            "Используйте кнопки ниже для управления:",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
<b>📖 Справка по командам:</b>

/start - Главное меню
/help - Эта справка
/stats - Статистика
/channels - Список каналов
/filters - Список фильтров

<b>Как добавить канал:</b>
1. Добавьте канал для отслеживания: /add_channel @username
2. Добавьте целевой канал (куда публиковать): /add_target @username

<b>Фильтры:</b>
Фильтры автоматически добавляются из переменных окружения
INCLUDE_FILTERS и EXCLUDE_FILTERS
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats"""
        user_id = update.effective_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Статистика каналов
            cursor.execute("SELECT COUNT(*) FROM source_channels")
            source_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM target_channels")
            target_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM published_posts")
            published_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM filters")
            filters_count = cursor.fetchone()[0]
        
        stats_text = f"""
<b>📊 Статистика бота:</b>

📡 Отслеживаемых каналов: {source_count}
🎯 Целевых каналов: {target_count}
📤 Опубликовано постов: {published_count}
🎭 Фильтров: {filters_count}

<b>Активные каналы:</b>
"""
        # Добавляем список каналов
        source_channels = self.db.get_source_channels()
        for i, channel in enumerate(source_channels, 1):
            stats_text += f"{i}. {channel['title']}\n"
            if channel.get('username'):
                stats_text += f"   @{channel['username']}\n"
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)
    
    async def channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /channels"""
        user_id = update.effective_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        source_channels = self.db.get_source_channels()
        target_channels = self.db.get_target_channels()
        
        text = "<b>📋 Отслеживаемые каналы:</b>\n\n"
        
        for i, channel in enumerate(source_channels, 1):
            text += f"{i}. {channel['title']}\n"
            if channel.get('username'):
                text += f"   @{channel['username']}\n"
            text += "\n"
        
        text += "<b>🎯 Целевые каналы:</b>\n\n"
        
        for i, channel in enumerate(target_channels, 1):
            text += f"{i}. {channel['title']}\n"
            if channel.get('username'):
                text += f"   @{channel['username']}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def filters_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /filters"""
        user_id = update.effective_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        filters = self.db.get_filters()
        
        text = "<b>🎭 Активные фильтры:</b>\n\n"
        
        include_filters = [f for f in filters if f['filter_type'] == 'include']
        exclude_filters = [f for f in filters if f['filter_type'] == 'exclude']
        
        text += "<b>Включающие (должны быть в тексте):</b>\n"
        for filt in include_filters:
            text += f"✅ {filt['value']}\n"
        
        text += "\n<b>Исключающие (не должны быть в тексте):</b>\n"
        for filt in exclude_filters:
            text += f"❌ {filt['value']}\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    
    async def add_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /add_channel"""
        user_id = update.effective_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /add_channel @username\n"
                "Пример: /add_channel @python_news"
            )
            return
        
        channel_username = context.args[0].replace('@', '')
        
        try:
            if not self.monitor:
                await update.message.reply_text("Мониторинг еще не запущен. Подождите...")
                return
            
            # Получаем информацию о канале
            entity = await self.monitor.get_entity(f"@{channel_username}")
            
            # Сохраняем в базу
            self.db.add_source_channel(
                channel_id=entity.id,
                username=entity.username,
                title=entity.title,
                invite_link=f"https://t.me/{entity.username}"
            )
            
            # Перезагружаем мониторинг
            await self.setup_monitor()
            
            await update.message.reply_text(
                f"✅ Канал <b>{entity.title}</b> (@{entity.username}) добавлен для отслеживания!",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")
    
    async def add_target_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /add_target"""
        user_id = update.effective_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        if not context.args:
            await update.message.reply_text(
                "Использование: /add_target @username\n"
                "Пример: /add_target @my_channel\n\n"
                "Сначала добавьте бота как администратора в целевой канал!"
            )
            return
        
        channel_username = context.args[0].replace('@', '')
        
        try:
            # Пробуем получить информацию о канале через бота
            chat = await self.bot.get_chat(f"@{channel_username}")
            
            # Сохраняем в базу
            self.db.add_target_channel(
                channel_id=chat.id,
                username=chat.username,
                title=chat.title,
                invite_link=f"https://t.me/{chat.username}"
            )
            
            await update.message.reply_text(
                f"✅ Целевой канал <b>{chat.title}</b> (@{chat.username}) добавлен!",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка: {str(e)[:200]}\n\n"
                "Убедитесь что:\n"
                "1. Бот добавлен как администратор в канал\n"
                "2. Бот имеет права на отправку сообщений"
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if self.config.ADMIN_IDS and user_id not in self.config.ADMIN_IDS:
            return
        
        data = query.data
        
        if data == 'stats':
            await self.stats_command(update, context)
        elif data == 'channels':
            await self.channels_command(update, context)
        elif data == 'filters':
            await self.filters_command(update, context)
        elif data == 'add_channel':
            await query.edit_message_text(
                "Отправьте команду: /add_channel @username\n"
                "Пример: /add_channel @python_news"
            )
        elif data == 'add_target':
            await query.edit_message_text(
                "Отправьте команду: /add_target @username\n"
                "Пример: /add_target @my_channel\n\n"
                "⚠️ Сначала добавьте бота как администратора в целевой канал!"
            )
    
    async def setup_bot(self):
        """Настроить Telegram бота"""
        self.logger.info("Настройка Telegram бота...")
        
        # Создаем бота
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.app = Application.builder().token(self.config.BOT_TOKEN).build()
        
        # Регистрируем обработчики команд
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("channels", self.channels_command))
        self.app.add_handler(CommandHandler("filters", self.filters_command))
        self.app.add_handler(CommandHandler("add_channel", self.add_channel_command))
        self.app.add_handler(CommandHandler("add_target", self.add_target_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Запускаем бота
        await self.app.initialize()
        await self.app.start()
        
        self.logger.info("Бот запущен и готов к работе!")
    
    async def run(self):
        """Запустить бота и мониторинг"""
        self.logger.info("Запуск Telegram Monitor Bot...")
        
        try:
            # Запускаем бота
            await self.setup_bot()
            
            # Настраиваем мониторинг
            await self.setup_monitor()
            
            # Получаем информацию о боте
            bot_info = await self.bot.get_me()
            self.logger.info(f"Бот: @{bot_info.username}")
            
            # Отправляем сообщение администраторам
            for admin_id in self.config.ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=f"✅ Бот @{bot_info.username} запущен и готов к работе!\n"
                             f"Используйте /start для управления."
                    )
                except:
                    pass
            
            self.logger.info("Бот успешно запущен! Мониторинг каналов активен.")
            
            # Бесконечный цикл
            await asyncio.Event().wait()
            
        except KeyboardInterrupt:
            self.logger.info("Остановка по запросу пользователя...")
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Корректное завершение работы"""
        self.logger.info("Завершение работы...")
        
        try:
            if self.monitor:
                await self.monitor.disconnect()
                self.logger.info("Мониторинг остановлен")
            
            if self.app:
                await self.app.stop()
                await self.app.shutdown()
                self.logger.info("Бот остановлен")
        except Exception as e:
            self.logger.error(f"Ошибка при завершении: {e}")
        
        self.logger.info("Работа завершена.")

# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

def main():
    """Главная функция запуска"""
    print("=" * 50)
    print("Telegram Channel Monitor Bot")
    print("=" * 50)
    
    # Создаем и запускаем бота
    bot = TelegramMonitorBot()
    
    # Запускаем асинхронный цикл
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\nБот остановлен пользователем")
    except Exception as e:
        print(f"Ошибка запуска: {e}")

if __name__ == "__main__":
    main()