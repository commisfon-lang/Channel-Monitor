import aiosqlite
import json
from datetime import datetime
from config import Config

class Database:
    def __init__(self, db_name=Config.DATABASE_NAME):
        self.db_name = db_name
        
    async def create_tables(self):
        """Создание таблиц в базе данных"""
        async with aiosqlite.connect(self.db_name) as db:
            # Таблица пользователей бота
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    is_premium INTEGER DEFAULT 0,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    request_count INTEGER DEFAULT 0
                )
            ''')
            
            # Таблица истории запросов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS request_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER,
                    target_user_id INTEGER,
                    target_username TEXT,
                    request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_user_id) REFERENCES bot_users (user_id)
                )
            ''')
            
            # Таблица статистики
            await db.execute('''
                CREATE TABLE IF NOT EXISTS statistics (
                    id INTEGER PRIMARY KEY,
                    total_requests INTEGER DEFAULT 0,
                    total_users INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Инициализируем статистику
            await db.execute('''
                INSERT OR IGNORE INTO statistics (id, total_requests, total_users) 
                VALUES (1, 0, 0)
            ''')
            
            await db.commit()
    
    async def add_or_update_user(self, user):
        """Добавление или обновление пользователя бота"""
        async with aiosqlite.connect(self.db_name) as db:
            # Проверяем, существует ли пользователь
            cursor = await db.execute(
                'SELECT user_id FROM bot_users WHERE user_id = ?',
                (user.id,)
            )
            exists = await cursor.fetchone()
            
            if exists:
                # Обновляем информацию
                await db.execute('''
                    UPDATE bot_users 
                    SET username = ?, first_name = ?, last_name = ?,
                        language_code = ?, is_premium = ?, last_active = ?
                    WHERE user_id = ?
                ''', (
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                    1 if user.is_premium else 0,
                    datetime.now().isoformat(),
                    user.id
                ))
            else:
                # Добавляем нового пользователя
                await db.execute('''
                    INSERT INTO bot_users 
                    (user_id, username, first_name, last_name, language_code, is_premium, joined_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    user.language_code,
                    1 if user.is_premium else 0,
                    datetime.now().isoformat()
                ))
                
                # Увеличиваем счетчик пользователей в статистике
                await db.execute('''
                    UPDATE statistics SET total_users = total_users + 1
                    WHERE id = 1
                ''')
            
            await db.commit()
    
    async def add_request_to_history(self, from_user_id, target_user_id, target_username=None):
        """Добавление запроса в историю"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                INSERT INTO request_history 
                (from_user_id, target_user_id, target_username, request_date)
                VALUES (?, ?, ?, ?)
            ''', (from_user_id, target_user_id, target_username, datetime.now().isoformat()))
            
            # Увеличиваем счетчик запросов у пользователя
            await db.execute('''
                UPDATE bot_users 
                SET request_count = request_count + 1,
                    last_active = ?
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), from_user_id))
            
            # Увеличиваем общий счетчик запросов
            await db.execute('''
                UPDATE statistics SET total_requests = total_requests + 1
                WHERE id = 1
            ''')
            
            await db.commit()
    
    async def get_user_history(self, user_id, limit=10):
        """Получение истории запросов пользователя"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('''
                SELECT 
                    h.target_user_id,
                    h.target_username,
                    h.request_date,
                    u.first_name,
                    u.last_name,
                    u.username
                FROM request_history h
                LEFT JOIN bot_users u ON h.target_user_id = u.user_id
                WHERE h.from_user_id = ?
                ORDER BY h.request_date DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = await cursor.fetchall()
            return rows
    
    async def get_bot_statistics(self):
        """Получение статистики бота"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('SELECT * FROM statistics WHERE id = 1')
            stats = await cursor.fetchone()
            
            cursor = await db.execute('SELECT COUNT(*) FROM bot_users')
            total_users = await cursor.fetchone()
            
            cursor = await db.execute('''
                SELECT COUNT(DISTINCT date(request_date)) 
                FROM request_history 
                WHERE date(request_date) = date('now')
            ''')
            today_requests = await cursor.fetchone()
            
            return {
                'total_requests': stats[1] if stats else 0,
                'total_users': total_users[0] if total_users else 0,
                'today_requests': today_requests[0] if today_requests else 0
            }
    
    async def get_top_users(self, limit=10):
        """Получение топ пользователей по количеству запросов"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('''
                SELECT user_id, username, first_name, last_name, request_count
                FROM bot_users
                ORDER BY request_count DESC
                LIMIT ?
            ''', (limit,))
            
            rows = await cursor.fetchall()
            return rows
    
    async def get_all_users(self):
        """Получение всех пользователей бота"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('SELECT user_id, username, first_name FROM bot_users')
            rows = await cursor.fetchall()
            return rows

# Создаем глобальный экземпляр базы данных
db = Database()