#!/usr/bin/env python3
"""
Скрипт автоматической установки бота
"""

import os
import sys
import subprocess

def run_command(command):
    """Выполнить команду"""
    print(f"Выполняю: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Ошибка: {result.stderr}")
    return result.returncode

def main():
    print("=== Установка Telegram Monitor Bot ===")
    print()
    
    # 1. Проверка Python
    print("1. Проверка Python...")
    if sys.version_info < (3, 7):
        print("Ошибка: Требуется Python 3.7 или выше")
        return 1
    
    # 2. Создание директории
    print("\n2. Создание директории...")
    os.makedirs("telegram_monitor", exist_ok=True)
    os.chdir("telegram_monitor")
    
    # 3. Копирование файлов
    print("\n3. Копирование файлов...")
    files_to_copy = ["telegram_monitor.py", "requirements.txt", ".env.example"]
    
    for file in files_to_copy:
        if not os.path.exists(file):
            print(f"  Файл {file} не найден в текущей директории")
    
    # 4. Установка зависимостей
    print("\n4. Установка зависимостей...")
    if run_command(f"{sys.executable} -m pip install --upgrade pip") != 0:
        return 1
    
    if run_command(f"{sys.executable} -m pip install -r requirements.txt") != 0:
        return 1
    
    # 5. Настройка .env файла
    print("\n5. Настройка конфигурации...")
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            import shutil
            shutil.copy(".env.example", ".env")
            print("  Создан .env файл из примера")
            print("  Отредактируйте файл .env и добавьте свои данные:")
            print("  - TELEGRAM_API_ID и TELEGRAM_API_HASH с my.telegram.org")
            print("  - TELEGRAM_BOT_TOKEN от @BotFather")
            print("  - ADMIN_IDS (ваш ID в Telegram)")
        else:
            print("  Создайте файл .env вручную")
    
    # 6. Инструкция по запуску
    print("\n" + "="*50)
    print("Установка завершена!")
    print("\nДальнейшие шаги:")
    print("1. Отредактируйте файл .env:")
    print("   nano .env")
    print("\n2. Запустите бота:")
    print("   python telegram_monitor.py")
    print("\n3. При первом запуске введите номер телефона и код")
    print("\n4. Управление ботом через Telegram команды")
    print("   /start - меню управления")
    print("="*50)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())