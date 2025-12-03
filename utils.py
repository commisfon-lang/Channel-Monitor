import re
import hashlib
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def extract_channel_info(url: str) -> Optional[Dict[str, str]]:
    """Извлечь информацию о канале из URL"""
    patterns = [
        r't\.me/([^/?]+)',  # t.me/username
        r'telegram\.me/([^/?]+)',  # telegram.me/username
        r'telegram\.dog/([^/?]+)',  # telegram.dog/username
        r'@(\w+)',  # @username
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            username = match.group(1).lstrip('@')
            return {
                'username': username,
                'invite_link': f"https://t.me/{username}"
            }
    
    return None

def generate_message_hash(message_data: Dict) -> str:
    """Сгенерировать хеш сообщения для идентификации"""
    content = f"{message_data.get('text', '')}{message_data.get('caption', '')}"
    media_id = message_data.get('media_id', '')
    
    hash_string = f"{content}:{media_id}"
    return hashlib.md5(hash_string.encode()).hexdigest()

def format_size(bytes_size: int) -> str:
    """Форматировать размер файла"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезать текст с добавлением многоточия"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def validate_url(url: str) -> bool:
    """Проверить валидность URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def escape_html(text: str) -> str:
    """Экранировать HTML-символы"""
    if not text:
        return ""
    
    escape_dict = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }
    
    for char, escape in escape_dict.items():
        text = text.replace(char, escape)
    
    return text

def parse_time_string(time_str: str) -> Optional[Dict[str, int]]:
    """Разобрать строку времени (например, '2h30m')"""
    pattern = r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
    match = re.match(pattern, time_str)
    
    if not match:
        return None
    
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    
    total_seconds = (
        days * 86400 +
        hours * 3600 +
        minutes * 60 +
        seconds
    )
    
    return {
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'seconds': seconds,
        'total_seconds': total_seconds
    }
