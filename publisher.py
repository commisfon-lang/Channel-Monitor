import asyncio
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from telegram import Bot, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.error import TelegramError, RetryAfter
from telegram.constants import ParseMode

from config import config
from database import Database

logger = logging.getLogger(__name__)

class PostPublisher:
    def __init__(self, db: Database):
        self.db = db
        self.bot = Bot(token=config.BOT_TOKEN)
        self.parse_mode = ParseMode.HTML
    
    async def publish_message(self, message, target_channel_id: int, 
                             source_channel_info: Dict[str, Any]) -> Optional[int]:
        """
        Опубликовать сообщение в целевом канале.
        Возвращает ID опубликованного сообщения или None в случае ошибки.
        """
        try:
            # Проверяем, не публиковали ли уже
            if self.db.is_post_published(message.chat.id, message.id, target_channel_id):
                logger.info(f"Пост {message.id} уже опубликован в канале {target_channel_id}")
                return None
            
            # Формируем контент
            caption = self._format_caption(message, source_channel_info)
            media_group = self._prepare_media(message)
            
            # Отправляем сообщение
            if media_group and len(media_group) > 1:
                # Группа медиа
                published_messages = await self.bot.send_media_group(
                    chat_id=target_channel_id,
                    media=media_group
                )
                published_message_id = published_messages[0].message_id if published_messages else None
            elif media_group:
                # Одиночное медиа
                media = media_group[0]
                if isinstance(media, InputMediaPhoto):
                    sent_message = await self.bot.send_photo(
                        chat_id=target_channel_id,
                        photo=media.media,
                        caption=media.caption,
                        parse_mode=self.parse_mode
                    )
                elif isinstance(media, InputMediaVideo):
                    sent_message = await self.bot.send_video(
                        chat_id=target_channel_id,
                        video=media.media,
                        caption=media.caption,
                        parse_mode=self.parse_mode
                    )
                elif isinstance(media, InputMediaDocument):
                    sent_message = await self.bot.send_document(
                        chat_id=target_channel_id,
                        document=media.media,
                        caption=media.caption,
                        parse_mode=self.parse_mode
                    )
                else:
                    sent_message = None
                published_message_id = sent_message.message_id if sent_message else None
            else:
                # Только текст
                sent_message = await self.bot.send_message(
                    chat_id=target_channel_id,
                    text=caption,
                    parse_mode=self.parse_mode,
                    disable_web_page_preview=True
                )
                published_message_id = sent_message.message_id
            
            # Сохраняем в базу данных
            if published_message_id:
                metadata = {
                    'source_channel_title': source_channel_info.get('title'),
                    'source_channel_username': source_channel_info.get('username'),
                    'message_date': message.date.isoformat() if message.date else None,
                    'has_media': bool(media_group),
                    'media_types': self._get_media_types(message)
                }
                
                self.db.add_published_post(
                    source_channel_id=message.chat.id,
                    source_message_id=message.id,
                    target_channel_id=target_channel_id,
                    published_message_id=published_message_id,
                    metadata=metadata
                )
                
                logger.info(f"Успешно опубликовано сообщение {message.id} -> {published_message_id}")
                return published_message_id
            
        except RetryAfter as e:
            logger.warning(f"Лимит запросов. Ждем {e.retry_after} секунд")
            await asyncio.sleep(e.retry_after)
            return await self.publish_message(message, target_channel_id, source_channel_info)
        
        except TelegramError as e:
            logger.error(f"Ошибка Telegram при публикации: {e}")
            self.db.log_error(
                error_type='publish_error',
                error_message=str(e),
                channel_id=target_channel_id,
                message_id=message.id
            )
        
        except Exception as e:
            logger.error(f"Неожиданная ошибка при публикации: {e}")
            self.db.log_error(
                error_type='unexpected_error',
                error_message=str(e),
                channel_id=target_channel_id,
                message_id=message.id
            )
        
        return None
    
    def _format_caption(self, message, source_channel_info: Dict[str, Any]) -> str:
        """Форматировать подпись для публикации"""
        caption_parts = []
        
        # Добавляем заголовок
        if source_channel_info.get('title'):
            channel_title = source_channel_info['title']
            channel_link = self._get_channel_link(source_channel_info)
            
            if channel_link:
                caption_parts.append(f"📢 <b>Из:</b> <a href='{channel_link}'>{channel_title}</a>")
            else:
                caption_parts.append(f"📢 <b>Из:</b> {channel_title}")
        
        # Добавляем текст сообщения
        text = message.text or message.caption or ""
        if text:
            # Обрезаем если слишком длинный
            max_length = config.MAX_POST_LENGTH - 200  # Оставляем место для подписи
            if len(text) > max_length:
                text = text[:max_length] + "..."
            caption_parts.append(text)
        
        # Добавляем ссылку на оригинал
        original_link = self._get_original_link(message, source_channel_info)
        if original_link:
            caption_parts.append(f"🔗 <a href='{original_link}'>Оригинал</a>")
        
        # Добавляем хештеги
        hashtags = self._extract_hashtags(message)
        if hashtags:
            caption_parts.append(" ".join(hashtags))
        
        # Добавляем время публикации
        if message.date:
            time_str = message.date.strftime("%d.%m.%Y %H:%M")
            caption_parts.append(f"🕐 {time_str}")
        
        return "\n\n".join(filter(None, caption_parts))
    
    def _prepare_media(self, message):
        """Подготовить медиа для отправки"""
        media_group = []
        caption = self._format_caption(message, {})
        
        if message.media:
            if message.photo:
                media_group.append(InputMediaPhoto(
                    media=message.photo[-1].file_id,  # Самое качественное фото
                    caption=caption,
                    parse_mode=self.parse_mode
                ))
            elif message.video:
                media_group.append(InputMediaVideo(
                    media=message.video.file_id,
                    caption=caption,
                    parse_mode=self.parse_mode
                ))
            elif message.document:
                media_group.append(InputMediaDocument(
                    media=message.document.file_id,
                    caption=caption,
                    parse_mode=self.parse_mode
                ))
            
            # Обработка группы медиа (если есть)
            if hasattr(message, 'grouped_id') and message.grouped_id:
                # Здесь нужно получить все сообщения группы
                # Для простоты пока обрабатываем только первое
                pass
        
        return media_group
    
    def _get_channel_link(self, channel_info: Dict[str, Any]) -> Optional[str]:
        """Получить ссылку на канал"""
        if channel_info.get('invite_link'):
            return channel_info['invite_link']
        elif channel_info.get('username'):
            return f"https://t.me/{channel_info['username']}"
        return None
    
    def _get_original_link(self, message, channel_info: Dict[str, Any]) -> Optional[str]:
        """Получить ссылку на оригинальное сообщение"""
        if channel_info.get('username') and message.id:
            return f"https://t.me/{channel_info['username']}/{message.id}"
        return None
    
    def _extract_hashtags(self, message) -> List[str]:
        """Извлечь хештеги из сообщения"""
        text = message.text or message.caption or ""
        hashtags = re.findall(r'#\w+', text)
        return list(set(hashtags))[:5]  # Не более 5 хештегов
    
    def _get_media_types(self, message) -> List[str]:
        """Получить типы медиа в сообщении"""
        types = []
        if message.photo:
            types.append('photo')
        if message.video:
            types.append('video')
        if message.document:
            types.append('document')
        if message.audio:
            types.append('audio')
        return types
