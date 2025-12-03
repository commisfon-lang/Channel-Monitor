import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
import json

from config import config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_path = config.DB_PATH
        self.init_db()
    
    def get_connection(self):
        """Получить соединение с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    @contextmanager
    def get_cursor(self):
        """Контекстный менеджер для работы с курсором"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """Инициализация базы данных"""
        with self.get_cursor() as cursor:
            # Таблица отслеживаемых каналов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS source_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE,
                    username TEXT,
                    title TEXT,
                    invite_link TEXT,
                    last_scanned_id INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица целевых каналов
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
            
            # Таблица фильтров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    filter_type TEXT CHECK(filter_type IN ('include', 'exclude', 'regex')),
                    value TEXT,
                    is_case_sensitive BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица опубликованных постов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS published_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_channel_id INTEGER,
                    source_message_id INTEGER,
                    target_channel_id INTEGER,
                    published_message_id INTEGER,
                    publish_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'success',
                    metadata TEXT,  -- JSON с дополнительной информацией
                    UNIQUE(source_channel_id, source_message_id, target_channel_id)
                )
            ''')
            
            # Таблица статистики
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE DEFAULT CURRENT_DATE,
                    source_channel_id INTEGER,
                    posts_scanned INTEGER DEFAULT 0,
                    posts_published INTEGER DEFAULT 0,
                    UNIQUE(date, source_channel_id)
                )
            ''')
            
            # Таблица ошибок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT,
                    error_message TEXT,
                    channel_id INTEGER,
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индексы для оптимизации
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_channels_active ON source_channels(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_published_posts_source ON published_posts(source_channel_id, source_message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_published_posts_date ON published_posts(publish_date)')
    
    # Методы для работы с исходными каналами
    def add_source_channel(self, channel_id: int, username: str, title: str, invite_link: str = None) -> bool:
        """Добавить канал для отслеживания"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('''
                    INSERT OR REPLACE INTO source_channels 
                    (channel_id, username, title, invite_link, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (channel_id, username, title, invite_link, datetime.now()))
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления канала: {e}")
            return False
    
    def get_source_channels(self, active_only: bool = True) -> List[Dict]:
        """Получить список отслеживаемых каналов"""
        with self.get_connection() as conn:
            query = 'SELECT * FROM source_channels'
            if active_only:
                query += ' WHERE is_active = 1'
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    def update_last_scanned_id(self, channel_id: int, last_message_id: int):
        """Обновить ID последнего проверенного сообщения"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                UPDATE source_channels 
                SET last_scanned_id = ?, updated_at = ?
                WHERE channel_id = ?
            ''', (last_message_id, datetime.now(), channel_id))
    
    # Методы для работы с целевыми каналами
    def add_target_channel(self, channel_id: int, username: str, title: str, invite_link: str = None) -> bool:
        """Добавить целевой канал"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('''
                    INSERT OR REPLACE INTO target_channels 
                    (channel_id, username, title, invite_link)
                    VALUES (?, ?, ?, ?)
                ''', (channel_id, username, title, invite_link))
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления целевого канала: {e}")
            return False
    
    def get_target_channels(self, active_only: bool = True) -> List[Dict]:
        """Получить список целевых каналов"""
        with self.get_connection() as conn:
            query = 'SELECT * FROM target_channels'
            if active_only:
                query += ' WHERE is_active = 1'
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    # Методы для работы с фильтрами
    def add_filter(self, name: str, filter_type: str, value: str, is_case_sensitive: bool = False) -> bool:
        """Добавить фильтр"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute('''
                    INSERT INTO filters (name, filter_type, value, is_case_sensitive)
                    VALUES (?, ?, ?, ?)
                ''', (name, filter_type, value, is_case_sensitive))
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления фильтра: {e}")
            return False
    
    def get_filters(self, active_only: bool = True) -> List[Dict]:
        """Получить список фильтров"""
        with self.get_connection() as conn:
            query = 'SELECT * FROM filters'
            if active_only:
                query += ' WHERE is_active = 1'
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    # Методы для работы с опубликованными постами
    def add_published_post(self, source_channel_id: int, source_message_id: int, 
                          target_channel_id: int, published_message_id: int, 
                          metadata: dict = None) -> bool:
        """Добавить запись об опубликованном посте"""
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            with self.get_cursor() as cursor:
                cursor.execute('''
                    INSERT INTO published_posts 
                    (source_channel_id, source_message_id, target_channel_id, 
                     published_message_id, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (source_channel_id, source_message_id, target_channel_id, 
                      published_message_id, metadata_json))
                
                # Обновляем статистику
                cursor.execute('''
                    INSERT OR REPLACE INTO statistics 
                    (date, source_channel_id, posts_published)
                    VALUES (date('now'), ?, 
                    COALESCE((SELECT posts_published FROM statistics 
                              WHERE date = date('now') AND source_channel_id = ?), 0) + 1)
                ''', (source_channel_id, source_channel_id))
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления записи о публикации: {e}")
            return False
    
    def is_post_published(self, source_channel_id: int, source_message_id: int, 
                         target_channel_id: int) -> bool:
        """Проверить, опубликован ли пост"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT id FROM published_posts 
                WHERE source_channel_id = ? 
                AND source_message_id = ? 
                AND target_channel_id = ?
            ''', (source_channel_id, source_message_id, target_channel_id))
            return cursor.fetchone() is not None
    
    # Статистика
    def get_statistics(self, days: int = 7) -> Dict:
        """Получить статистику за последние N дней"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    date,
                    SUM(posts_scanned) as total_scanned,
                    SUM(posts_published) as total_published
                FROM statistics
                WHERE date >= date('now', ?)
                GROUP BY date
                ORDER BY date DESC
            ''', (f'-{days} days',))
            
            stats = cursor.fetchall()
            return {
                'days': days,
                'total_scanned': sum(row['total_scanned'] for row in stats),
                'total_published': sum(row['total_published'] for row in stats),
                'daily_stats': [dict(row) for row in stats]
            }
    
    # Ошибки
    def log_error(self, error_type: str, error_message: str, 
                  channel_id: int = None, message_id: int = None):
        """Записать ошибку в базу"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO errors (error_type, error_message, channel_id, message_id)
                VALUES (?, ?, ?, ?)
            ''', (error_type, error_message, channel_id, message_id))
