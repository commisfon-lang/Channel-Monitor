#!/bin/bash
# Управление ботом через systemd или напрямую

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$PROJECT_DIR/bot.pid"
LOG_FILE="$PROJECT_DIR/logs/bot.log"
ERROR_FILE="$PROJECT_DIR/logs/bot.error.log"

start_bot() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "Бот уже запущен (PID: $(cat $PID_FILE))"
        return 1
    fi
    
    cd "$PROJECT_DIR"
    source venv/bin/activate
    nohup python main.py >> "$LOG_FILE" 2>> "$ERROR_FILE" &
    PID=$!
    echo $PID > "$PID_FILE"
    echo "Бот запущен с PID: $PID"
    echo "Логи: tail -f $LOG_FILE"
}

stop_bot() {
    if [ ! -f "$PID_FILE" ]; then
        echo "PID файл не найден"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        sleep 2
        echo "Бот остановлен (PID: $PID)"
        rm -f "$PID_FILE"
    else
        echo "Процесс не существует"
        rm -f "$PID_FILE"
    fi
}

restart_bot() {
    stop_bot
    sleep 2
    start_bot
}

status_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo "✅ Бот запущен (PID: $PID)"
            echo "📊 Память: $(ps -p $PID -o rss=) KB"
            echo "📈 Время работы: $(ps -p $PID -o etime=)"
        else
            echo "❌ PID файл есть, но процесс не запущен"
        fi
    else
        echo "❌ Бот не запущен"
    fi
}

show_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "Лог файл не найден: $LOG_FILE"
    fi
}

show_errors() {
    if [ -f "$ERROR_FILE" ]; then
        tail -f "$ERROR_FILE"
    else
        echo "Файл ошибок не найден: $ERROR_FILE"
    fi
}

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        status_bot
        ;;
    logs)
        show_logs
        ;;
    errors)
        show_errors
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|errors}"
        exit 1
        ;;
esac