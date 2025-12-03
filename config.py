import os
from dataclasses import dataclass
from typing import List

@dataclass
class Config:
    # Telethon настройки
    API_ID: int = int(os.getenv('TELEGRAM_API_ID', 0))
    API_HASH: str = os.getenv('TELEGRAM_API_HASH', '')
    SESSION_NAME: str = os.getenv('TELEGRAM_SESSION', 'session')
    
    # Бот настройки
    BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    
    # База данных
    DB_PATH: str = os.getenv('DB_PATH', 'data/bot.db')
    DB_TYPE: str = os.getenv('DB_TYPE', 'sqlite')  # sqlite или postgres
    
    # Настройки приложения
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    CHECK_INTERVAL: int = int(os.getenv('CHECK_INTERVAL', '60'))  # секунды
    MAX_POST_LENGTH: int = int(os.getenv('MAX_POST_LENGTH', '4096'))
    
    # Администраторы
    ADMIN_IDS: List[int] = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []
    
    # Пути
    DATA_DIR: str = os.getenv('DATA_DIR', 'data')
    LOGS_DIR: str = os.getenv('LOGS_DIR', 'logs')
    
    # PostgreSQL (если используется)
    POSTGRES_HOST: str = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT: int = int(os.getenv('POSTGRES_PORT', '5432'))
    POSTGRES_DB: str = os.getenv('POSTGRES_DB', 'telegram_bot')
    POSTGRES_USER: str = os.getenv('POSTGRES_USER', 'postgres')
    POSTGRES_PASSWORD: str = os.getenv('POSTGRES_PASSWORD', '')
    
    def __post_init__(self):
        # Создаем директории
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.LOGS_DIR, exist_ok=True)
        
        # Проверяем обязательные настройки
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не установлен")
        if not self.API_ID or not self.API_HASH:
            raise ValueError("API_ID и API_HASH не установлены")

config = Config()