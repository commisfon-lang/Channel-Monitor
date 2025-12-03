#!/usr/bin/env python3
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager

from config import config
from monitor import ChannelMonitor
from bot import ManagementBot
from database import Database

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{config.LOGS_DIR}/bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class Application:
    def __init__(self):
        self.db = Database()
        self.monitor = ChannelMonitor()
        self.bot = ManagementBot(self.monitor)
        self.is_running = False
    
    async def start(self):
        """Запустить приложение"""
        logger.info("Запуск приложения...")
        self.is_running = True
        
        # Устанавливаем обработчики сигналов
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        
        try:
            # Запускаем бота и монитор параллельно
            monitor_task = asyncio.create_task(self.monitor.start())
            bot_task = asyncio.create_task(self.bot.start())
            
            # Ждем завершения
            await asyncio.gather(monitor_task, bot_task)
            
        except asyncio.CancelledError:
            logger.info("Приложение остановлено по запросу")
        except Exception as e:
            logger.error(f"Ошибка в приложении: {e}", exc_info=True)
        finally:
            await self.cleanup()
    
    async def stop(self):
        """Остановить приложение"""
        if not self.is_running:
            return
        
        logger.info("Остановка приложения...")
        self.is_running = False
        
        # Отменяем все задачи
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def cleanup(self):
        """Очистка ресурсов"""
        logger.info("Очистка ресурсов...")
        
        try:
            await self.bot.stop()
            await self.monitor.stop()
        except Exception as e:
            logger.error(f"Ошибка при очистке: {e}")
        
        logger.info("Приложение остановлено")

async def main():
    """Главная функция"""
    app = Application()
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал KeyboardInterrupt")
        await app.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Проверяем наличие обязательных настроек
    if config.API_ID == 0 or not config.API_HASH:
        logger.error("Не установлены API_ID и/или API_HASH")
        logger.error("Создайте файл .env на основе .env.example")
        sys.exit(1)
    
    if not config.BOT_TOKEN:
        logger.error("Не установлен BOT_TOKEN")
        sys.exit(1)
    
    # Запускаем приложение
    asyncio.run(main())