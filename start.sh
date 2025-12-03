#!/bin/bash
cd "$(dirname "$0")"

# Создаем директории если их нет
mkdir -p data logs session

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "Ошибка: Файл .env не найден!"
    echo "Создайте файл .env на основе .env.example"
    exit 1
fi

# Проверяем наличие виртуального окружения
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Запускаем бота
echo "Запуск Telegram Monitor Bot..."
python main.py