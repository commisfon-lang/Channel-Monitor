#!/bin/bash
echo "Остановка Telegram Monitor Bot..."
pkill -f "python main.py"
sleep 2
echo "Бот остановлен"