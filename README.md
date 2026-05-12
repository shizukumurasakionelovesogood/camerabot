# Telegram Laptop Camera Controller

Старый ноутбук на Windows 11 работает как удаленная камера, а управление идет через Telegram-бота и минималистичную Telegram Mini App панель.

Проект не требует VPS: бот на ноутбуке сам подключается к Telegram Bot API через long polling. Если Mini App не может достучаться до локального FastAPI с телефона, она отправляет команду через `Telegram.WebApp.sendData`, а бот на ноутбуке выполняет ее и присылает результат в Telegram.

## Важно о безопасности и законе

Используйте проект только для своей камеры, своего помещения и с согласия людей, которые могут попасть в кадр. Не используйте его для скрытого наблюдения, записи без разрешения или доступа к чужим устройствам.

Бот игнорирует всех пользователей, кроме `OWNER_TELEGRAM_ID`.

## Возможности

- `/start` - меню и кнопка открытия панели
- `/photo` - сделать фото и отправить в Telegram
- `/video 5`, `/video 10`, `/video 30` - записать видео и отправить
- `/status` - онлайн-статус ноутбука, статус камеры, последняя команда, uptime
- `/restart` - переоткрыть камеру и проверить доступность
- `/help` - список команд
- Inline keyboard:
  - `📸 Photo`
  - `🎥 Video 5s`
  - `🎥 Video 10s`
  - `🎥 Video 30s`
  - `📡 Status`
  - `🌐 Open Panel`
- Mini App:
  - статус ноутбука и камеры
  - `Take Photo`
  - выбор длительности видео: 5s, 10s, 15s, 30s, 60s
  - `Record`
  - `Refresh Status`

## Установка на Windows 11

1. Установите Python 3.11+:
   - https://www.python.org/downloads/windows/
   - при установке включите `Add python.exe to PATH`

2. Создайте Telegram-бота:
   - откройте `@BotFather`
   - выполните `/newbot`
   - сохраните токен бота

3. Узнайте свой Telegram user id:
   - можно написать `@userinfobot`
   - скопируйте числовой `id`

4. В папке проекта создайте виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Если PowerShell запрещает запуск скриптов, выполните:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

5. Установите зависимости:

```powershell
pip install -r requirements.txt
```

6. Создайте `.env` из примера:

```powershell
copy .env.example .env
```

Заполните:

```env
BOT_TOKEN=123456:ABC...
OWNER_TELEGRAM_ID=123456789
CAMERA_INDEX=0
```

7. Запустите:

```powershell
python bot.py
```

Бот запустит long polling и локальный FastAPI сервер.

## Mini App и локальная панель

Локальная панель доступна на ноутбуке:

```text
http://127.0.0.1:8000/webapp/
```

Если телефон находится в той же Wi-Fi сети, можно попробовать открыть панель по IP ноутбука:

```text
http://<IP-ноутбука>:8000/webapp/
```

Для этого в `.env` поставьте:

```env
API_HOST=0.0.0.0
```

Telegram Mini App кнопка `Open Panel` требует HTTPS URL. Без VPS можно разместить только статические файлы `webapp/index.html`, `webapp/styles.css`, `webapp/app.js` на GitHub Pages, Cloudflare Pages или другом бесплатном статическом хостинге, а backend все равно останется локальным на ноутбуке.

В `.env` укажите:

```env
MINI_APP_URL=https://your-static-site.example/webapp/
```

Если Mini App открыта на телефоне и не может обратиться к локальному `http://127.0.0.1:8000`, она автоматически отправит команду через Telegram WebApp data. Результат придет в чат с ботом.

## ffmpeg

По умолчанию видео пишется через OpenCV в `.mp4` с кодеком `mp4v`. Обычно этого достаточно.

Если на старом ноутбуке OpenCV не может создать MP4 или Telegram плохо принимает видео, установите ffmpeg:

```powershell
winget install Gyan.FFmpeg
```

Или через Chocolatey:

```powershell
choco install ffmpeg
```

После установки перезапустите PowerShell. Текущая версия проекта не требует ffmpeg напрямую, но он полезен для диагностики и конвертации видео.

## Переменные окружения

| Переменная | Описание | По умолчанию |
| --- | --- | --- |
| `BOT_TOKEN` | токен Telegram-бота | обязательно |
| `OWNER_TELEGRAM_ID` | ваш Telegram user id | обязательно |
| `MINI_APP_URL` | HTTPS URL Mini App для кнопки Telegram | пусто |
| `CAMERA_INDEX` | индекс камеры OpenCV | `0` |
| `API_HOST` | host FastAPI | `127.0.0.1` |
| `API_PORT` | port FastAPI | `8000` |
| `DB_PATH` | путь SQLite базы | `camera_controller.sqlite3` |
| `TEMP_DIR` | временная папка фото/видео | `temp` |
| `START_API` | запускать FastAPI вместе с ботом | `true` |

## Файлы

- `bot.py` - Telegram bot, polling, inline keyboard, WebApp fallback
- `api.py` - FastAPI локальный backend и static hosting для `webapp/`
- `camera.py` - работа с OpenCV камерой
- `storage.py` - SQLite лог команд
- `webapp/index.html` - Mini App markup
- `webapp/styles.css` - iOS-like glass UI
- `webapp/app.js` - Mini App логика и fallback через Telegram

## Диагностика

- Камера занята: закройте Zoom, Teams, OBS, браузерные вкладки с камерой.
- Неверный `CAMERA_INDEX`: попробуйте `0`, `1`, `2`.
- Телефон не видит локальный API: это нормально для `localhost`; используйте fallback через Telegram Mini App data или откройте панель с ноутбука.
- Windows Firewall может спросить разрешение для Python, если `API_HOST=0.0.0.0`.
