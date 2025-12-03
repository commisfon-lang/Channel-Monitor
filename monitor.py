import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Message
from telethon.errors import FloodWaitError

from config import config
from database import Database
from filters import MessageFilter
from publisher import PostPublisher

logger = logging.getLogger(__name__)

class ChannelMonitor:
    def __init__(self):
        self.client = TelegramClient(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH
        )
        self.db = Database()
        self.filter = MessageFilter(self.db)
        self.publisher = PostPublisher(self.db)
        self.is_running = False
        self.handlers = []
    
    async def start(self):
        """Запустить мониторинг"""
        await self.client.start()
        self.is_running = True
        
        logger.info("Мониторинг каналов запущен")
        
        # Загружаем и настраиваем каналы
        await self._setup_monitored_channels()
        
        # Запускаем периодическую проверку старых сообщений
        asyncio.create_task(self._periodic_check())
        
        # Ждем событий
        await self.client.run_until_disconnected()
    
    async def _setup_monitored_channels(self):
        """Настроить отслеживание каналов"""
        channels = self.db.get_source_channels(active_only=True)
        
        for channel_info in channels:
            try:
                channel_id = channel_info['channel_id']
                username = channel_info['username']
                
                # Получаем entity канала
                entity = await self.client.get_entity(channel_id)
                
                # Создаем обработчик новых сообщений
                @self.client.on(events.NewMessage(chats=entity))
                async def handler(event):
                    await self._process_message(event.message, channel_info)
                
                self.handlers.append(handler)
                logger.info(f"Настроен мониторинг канала: {channel_info['title']}")
                
            except Exception as e:
                logger.error(f"Ошибка настройки канала {channel_info.get('title')}: {e}")
                self.db.log_error(
                    error_type='setup_error',
                    error_message=str(e),
                    channel_id=channel_info.get('channel_id')
                )
    
    async def _process_message(self, message: Message, channel_info: Dict):
        """Обработать новое сообщение"""
        try:
            # Проверяем тип чата
            if not isinstance(message.chat, Channel):
                return
            
            # Проверяем дату (не старше 24 часов)
            if message.date and (datetime.now() - message.date).days > 1:
                return
            
            # Проверяем фильтры
            text = message.text or message.caption or ""
            if not self.filter.check_message(text):
                logger.debug(f"Сообщение {message.id} не прошло фильтрацию")
                return
            
            # Проверяем тип медиа (опционально)
            allowed_media_types = ['photo', 'video']  # Можно настроить
            if not self.filter.check_media_type(message, allowed_media_types):
                logger.debug(f"Сообщение {message.id} не подходит по типу медиа")
                return
            
            # Получаем целевые каналы
            target_channels = self.db.get_target_channels(active_only=True)
            if not target_channels:
                logger.warning("Нет активных целевых каналов")
                return
            
            # Публикуем в каждый целевой канал
            for target_channel in target_channels:
                published_id = await self.publisher.publish_message(
                    message=message,
                    target_channel_id=target_channel['channel_id'],
                    source_channel_info=channel_info
                )
                
                if published_id:
                    logger.info(f"Опубликовано {message.id} -> {target_channel['title']}")
            
            # Обновляем последний отсканированный ID
            self.db.update_last_scanned_id(channel_info['channel_id'], message.id)
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait: {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
        
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения {message.id}: {e}")
            self.db.log_error(
                error_type='process_error',
                error_message=str(e),
                channel_id=message.chat.id if message.chat else None,
                message_id=message.id
            )
    
    async def _periodic_check(self):
        """Периодическая проверка старых сообщений"""
        while self.is_running:
            try:
                await asyncio.sleep(config.CHECK_INTERVAL * 10)  # Каждые 10 минут
                
                channels = self.db.get_source_channels(active_only=True)
                for channel_info in channels:
                    await self._check_channel_history(channel_info)
                    
            except Exception as e:
                logger.error(f"Ошибка в периодической проверке: {e}")
                await asyncio.sleep(60)
    
    async def _check_channel_history(self, channel_info: Dict):
        """Проверить историю канала на пропущенные сообщения"""
        try:
            entity = await self.client.get_entity(channel_info['channel_id'])
            last_scanned_id = channel_info['last_scanned_id']
            
            # Получаем сообщения после последнего проверенного
            messages = await self.client.get_messages(
                entity,
                min_id=last_scanned_id,
                limit=50
            )
            
            for message in messages:
                if message.id > last_scanned_id:
                    await self._process_message(message, channel_info)
            
        except Exception as e:
            logger.error(f"Ошибка проверки истории канала {channel_info['title']}: {e}")
    
    async def add_channel(self, channel_identifier: str) -> bool:
        """Добавить канал для мониторинга"""
        try:
            entity = await self.client.get_entity(channel_identifier)
            
            if not isinstance(entity, Channel):
                logger.error("Указанный объект не является каналом")
                return False
            
            # Сохраняем в базу
            success = self.db.add_source_channel(
                channel_id=entity.id,
                username=entity.username,
                title=entity.title,
                invite_link=f"https://t.me/{entity.username}" if entity.username else None
            )
            
            if success:
                # Перезагружаем обработчики
                await self._reload_handlers()
                logger.info(f"Добавлен канал: {entity.title}")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка добавления канала: {e}")
            return False
    
    async def _reload_handlers(self):
        """Перезагрузить обработчики событий"""
        # Удаляем старые обработчики
        for handler in self.handlers:
            self.client.remove_event_handler(handler)
        self.handlers.clear()
        
        # Загружаем заново
        await self._setup_monitored_channels()
    
    async def stop(self):
        """Остановить мониторинг"""
        self.is_running = False
        await self.client.disconnect()
        logger.info("Мониторинг остановлен")