import asyncio
import logging
from datetime import datetime, time
from typing import List, Dict
import pytz

from database import Database

logger = logging.getLogger(__name__)

class PostScheduler:
    def __init__(self, db: Database):
        self.db = db
        self.scheduled_tasks = []
        self.timezone = pytz.timezone('Europe/Moscow')  # Настройте под ваш регион
    
    async def schedule_post(self, message_data: Dict, target_channel_id: int, 
                           schedule_time: datetime):
        """Запланировать публикацию поста на определенное время"""
        try:
            delay = (schedule_time - datetime.now(self.timezone)).total_seconds()
            
            if delay <= 0:
                logger.warning("Время публикации уже прошло")
                return False
            
            # Создаем задачу
            task = asyncio.create_task(
                self._publish_scheduled(message_data, target_channel_id, delay)
            )
            self.scheduled_tasks.append(task)
            
            logger.info(f"Пост запланирован на {schedule_time}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка планирования: {e}")
            return False
    
    async def _publish_scheduled(self, message_data: Dict, target_channel_id: int, delay: float):
        """Опубликовать запланированный пост"""
        await asyncio.sleep(delay)
        
        # Здесь должна быть логика публикации
        # Для реализации нужно передать publisher или пересмотреть архитектуру
        logger.info(f"Публикую запланированный пост в {target_channel_id}")
    
    def get_schedule_settings(self) -> Dict:
        """Получить настройки расписания"""
        return {
            'active_hours': list(range(9, 22)),  # с 9 до 21
            'posts_per_hour': 2,  # не более 2 постов в час
            'min_interval': 1800,  # минимум 30 минут между постами
        }
    
    def calculate_best_time(self) -> datetime:
        """Рассчитать лучшее время для публикации"""
        now = datetime.now(self.timezone)
        settings = self.get_schedule_settings()
        
        # Простой алгоритм - следующий час в пределах активного времени
        current_hour = now.hour
        
        for hour in range(current_hour + 1, 24):
            if hour in settings['active_hours']:
                # Следующий час, минута = 0
                return now.replace(hour=hour, minute=0, second=0, microsecond=0)
        
        # Если сегодня нет подходящего времени, на завтра
        tomorrow = now.replace(hour=settings['active_hours'][0], minute=0, 
                              second=0, microsecond=0) + timedelta(days=1)
        return tomorrow
    
    async def stop(self):
        """Остановить все запланированные задачи"""
        for task in self.scheduled_tasks:
            task.cancel()
        
        try:
            await asyncio.gather(*self.scheduled_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        
        logger.info("Планировщик остановлен")