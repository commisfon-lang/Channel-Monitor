import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MessageFilter:
    def __init__(self, db):
        self.db = db
        self.filters_cache = None
        self.cache_time = None
    
    def _load_filters(self):
        """Загрузить фильтры из базы данных"""
        filters = self.db.get_filters(active_only=True)
        self.filters_cache = filters
        return filters
    
    def get_filters(self):
        """Получить актуальные фильтры"""
        return self._load_filters()
    
    def check_message(self, text: str, filters: Optional[List[Dict]] = None) -> bool:
        """
        Проверить сообщение по фильтрам.
        Возвращает True, если сообщение проходит фильтрацию.
        """
        if not text:
            return False
        
        if filters is None:
            filters = self.get_filters()
        
        if not filters:
            return True  # Нет фильтров = пропускаем все
        
        text_to_check = text
        passes_all_filters = True
        
        for filter_item in filters:
            filter_type = filter_item['filter_type']
            value = filter_item['value']
            case_sensitive = filter_item['is_case_sensitive']
            
            if not case_sensitive:
                text_to_check = text.lower()
                value = value.lower()
            else:
                text_to_check = text
            
            if filter_type == 'include':
                # Должно содержать ключевое слово
                if value not in text_to_check:
                    logger.debug(f"Сообщение не содержит '{value}'")
                    passes_all_filters = False
                    break
            
            elif filter_type == 'exclude':
                # Не должно содержать ключевое слово
                if value in text_to_check:
                    logger.debug(f"Сообщение содержит исключающее слово '{value}'")
                    passes_all_filters = False
                    break
            
            elif filter_type == 'regex':
                # Должно соответствовать регулярному выражению
                try:
                    pattern = re.compile(value, 0 if case_sensitive else re.IGNORECASE)
                    if not pattern.search(text):
                        logger.debug(f"Сообщение не соответствует regex '{value}'")
                        passes_all_filters = False
                        break
                except re.error as e:
                    logger.error(f"Ошибка в регулярном выражении '{value}': {e}")
                    continue
        
        return passes_all_filters
    
    def extract_keywords(self, text: str) -> List[str]:
        """Извлечь ключевые слова из текста (для тегов)"""
        # Простая реализация - можно улучшить
        words = re.findall(r'\b\w{3,}\b', text.lower())
        return list(set(words))
    
    def check_media_type(self, message, allowed_types: List[str] = None) -> bool:
        """Проверить тип медиа"""
        if not allowed_types:
            return True
        
        media_type = self.get_media_type(message)
        return media_type in allowed_types if media_type else False
    
    @staticmethod
    def get_media_type(message) -> Optional[str]:
        """Определить тип медиа в сообщении"""
        if message.photo:
            return 'photo'
        elif message.video:
            return 'video'
        elif message.document:
            # Можно уточнить тип документа
            if message.document.mime_type:
                if 'image' in message.document.mime_type:
                    return 'image'
                elif 'video' in message.document.mime_type:
                    return 'video'
                elif 'audio' in message.document.mime_type:
                    return 'audio'
            return 'document'
        elif message.audio:
            return 'audio'
        elif message.voice:
            return 'voice'
        elif message.sticker:
            return 'sticker'
        elif message.poll:
            return 'poll'
        elif message.location:
            return 'location'
        elif message.contact:
            return 'contact'
        return None
