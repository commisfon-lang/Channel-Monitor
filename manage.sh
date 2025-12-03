#!/bin/bash
SERVICE_NAME="telegram-monitor"

case "$1" in
    start)
        sudo systemctl start $SERVICE_NAME
        echo "Служба запущена"
        ;;
    stop)
        sudo systemctl stop $SERVICE_NAME
        echo "Служба остановлена"
        ;;
    restart)
        sudo systemctl restart $SERVICE_NAME
        echo "Служба перезапущена"
        ;;
    status)
        sudo systemctl status $SERVICE_NAME
        ;;
    logs)
        sudo journalctl -u $SERVICE_NAME -f
        ;;
    enable)
        sudo systemctl enable $SERVICE_NAME
        echo "Автозапуск включен"
        ;;
    disable)
        sudo systemctl disable $SERVICE_NAME
        echo "Автозапуск отключен"
        ;;
    install)
        # Создание службы systemd
        sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Telegram Channel Monitor Bot
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=10
User=$(whoami)
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
ExecStart=$(pwd)/venv/bin/python $(pwd)/main.py

StandardOutput=append:$(pwd)/logs/bot.log
StandardError=append:$(pwd)/logs/bot.error.log

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        echo "Служба установлена"
        ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs|enable|disable|install}"
        exit 1
        ;;
esac