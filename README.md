# Мост MAX ↔ Telegram

Пересылка сообщений между чатами MAX и Telegram в обе стороны.
Пары настраиваются отдельно: каждый чат MAX — в свою группу TG.
Используйте на свой страх и риск, шанс бана в MAX не нулевой.

## Возможности

**MAX → Telegram**
- текст, фото, видео (в т.ч. кружки), файлы, голосовые, стикеры
- форварды и ответы (цитата)
- служебные события чата: добавили/кикнули, выход, вход по ссылке, смена названия, пин
- пачка сообщений подряд не теряется (очередь, отдельно от websocket)

**Telegram → MAX**
- текст из группы TG уходит только в связанный чат MAX, без имени отправителя
- команды (`/start`, `/status`, …) в MAX не форвардятся
- антилуп: то, что бот сам отправил в MAX, обратно в TG не дублируется

**Мониторинг**
- алерты в Telegram: старт, MAX онлайн, протухший токен, обрыв websocket, ошибка пересылки, падение `main.py` (код + хвост лога)
- `/start` в личку боту — твой user id для `MONITOR_ID` (бот должен уже работать)
- `/status` или `/ping` — пример:

```
статус
MAX: онлайн (ART)
в работе: 12м
последняя MAX->TG: 5с назад
последняя TG->MAX: ещё не было
-111 (Класс 8Б) -> -100123 (Максимум 8б)
-222 (Другой чат) -> -100456 (Моя группа)
```

«ещё не было» = в эту сторону с запуска ничего не ходило. «5с назад» = сколько времени с последней пересылки.
В консоли при коннекте те же пары с названиями.
- `starter.py` рестартит процесс после краша; websocket сам переподключается

## Ограничения

- TG → MAX только текст (фото/файлы из Telegram в MAX не загружаются)
- файл из MAX без прямой ссылки — в TG уйдёт имя файла
- Lottie-стикеры в TG могут не открыться
- `get_token.py` не работает: MAX требует капчу на SMS-логин, токен только из web.max.ru
- один `MAX_TOKEN` = одна сессия: бот и backfill / два инстанса одновременно нельзя

## Требования

- Python 3.10+ (проверялось на 3.14)
- Аккаунт MAX (сначала регистрация в приложении)
- Аккаунт Telegram

## Установка

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`pip` как отдельная команда часто не в PATH — всегда `python -m pip`.

## Токен MAX

Нужен LOGIN-токен веб-клиента (не SMS).

1. Открой [web.max.ru](https://web.max.ru) и войди
2. DevTools → Network → WS (`ws-api.oneme.ru`)
3. Найди пакет opcode `19` (логин/синк) и поле `token`
4. Либо возьми base64 бинарного пакета и декодируй поле `token`

Бот дома и на VPS с одним токеном одновременно не запускай.

## Telegram-бот

1. @BotFather → `/newbot` → скопируй токен
2. @BotFather → `/setprivacy` → **Disable** (иначе бот не видит обычный текст в группе)
3. Напиши боту `/start` в личку (бот должен быть запущен) — пришлёт user id для `MONITOR_ID`

## ID чатов

MAX: открой чат на [web.max.ru](https://web.max.ru), ID в URL (`https://web.max.ru/-123...`).

Telegram:
- личка: `/start` боту — это твой user id. Запасной вариант: [@userinfobot](https://t.me/userinfobot)
- группа: добавь бота **админом**, перешли любое сообщение из группы `@userinfobot` (id отрицательный)

Первая часть `TG_BOT_TOKEN` до `:` — id бота, не чата. Если его поставить в мост, ТГ ответит `403 can't send messages to the bot`.

## `.env`

```
MAX_TOKEN=токен_из_web.max.ru
TG_BOT_TOKEN=123456:AAH...
MONITOR_ID=123456789
BRIDGES=-111:-100123,-222:-100456,-333:-100789
```

`BRIDGES` — пары `чат_MAX:чат_TG` через запятую. Каждая пара — отдельный мост в обе стороны.

Примеры:
- три MAX в три разные TG — как выше
- два MAX в одну TG: `-111:-100123,-222:-100123`

`MONITOR_ID` — куда слать алерты (лучше личка). Если пусто — в первую TG из моста.

Бот должен быть **админом в каждой** TG-группе из `BRIDGES`.

Запасной формат, если `BRIDGES` нет: `MAX_CHAT_IDS=-111,-222` + `TG_CHAT_ID=-100123` (все MAX в одну группу). Если `BRIDGES` задан — эти поля игнорируются.

Файл не коммитить (уже в `.gitignore`).

## Добавить ещё один мост

1. Создай группу в Telegram, добавь бота админом
2. Возьми id MAX-чата и id TG-группы
3. Допиши пару в `BRIDGES`: `...,-новыйMAX:-новаяTG`
4. Рестарт `starter.py`, проверь `/status`

## Запуск

```powershell
python starter.py
```

В консоли: `Имя: ..., Номер: ... | ID: ...` и строки `мост <MAX> (название) -> <TG> (название)`. В `MONITOR_ID` придёт «скрипт запущен» и «MAX онлайн».

Проверка:
1. Напиши в чат MAX → сообщение в **его** группу Telegram
2. Напиши в эту TG-группу (не от бота, не команда) → текст только в связанный MAX
3. `/status` — онлайн, последняя пересылка, пары `id (название)`

Остановка: Ctrl+C.

## История (backfill)

Сначала **останови** `starter.py` (второй коннект вышибет сессию).

Последние 10 сообщений чата (включая форварды, reply, фото, CONTROL):

```powershell
python backfill.py -111 10
```

Все сообщения чата (долго, пауза ~3 с на сообщение из‑за лимита ТГ в группе):

```powershell
python backfill.py -111
```

`chat_id` — MAX-чат из `BRIDGES`. Пишет в ту TG, с которой этот чат связан. Без аргументов берётся дефолтный id из `backfill.py`.

Потом снова `python starter.py`.

## 24/7

Нужен постоянно включённый процесс (NAS, домашний ПК, VPS). Serverless/Render free не подойдёт — нужен живой WebSocket.

Один `MAX_TOKEN` = одна сессия. Когда бот крутится на NAS, `starter.py` на ПК останови.

### Synology (Container Manager)

1. Package Center → **Container Manager** (если нет — Docker)
2. File Station: папка, например `/volume1/docker/max-tg-bridge`
3. Положи туда файлы репо **без** `.venv`. `.env` — тот же, что дома (File Station → загрузить)
4. Container Manager → **Проект** → Создать:
   - путь: эта папка
   - имя: `max-tg-bridge`
   - источник: `docker-compose.yml`
5. Создать проект и запустить. `restart: unless-stopped` — поднимется после ребута NAS

Обновить `.py` или `.env` (новые мосты в `BRIDGES`): залей файл → контейнер **Стоп → Старт**. Stop/Start сам по себе Docker-переменные не обновляет — `.env` читается с диска при старте процесса.

Если правишь `Dockerfile`/`requirements.txt`/`docker-compose.yml` — проект **удалить** (файлы на диске оставить) и **создать заново**. То же самое, если Stop/Start не подхватил новый `BRIDGES`.

Через SSH (Control Panel → Терминал → включить SSH, пользователь admin):

```bash
sudo mkdir -p /volume1/docker/max-tg-bridge
# скопируй файлы (scp / File Station), .env руками
cd /volume1/docker/max-tg-bridge
sudo docker compose up -d --build
sudo docker compose logs -f
```

Если `docker compose` нет: `sudo docker-compose`. Образ `python:3.12-slim` есть для x86_64 и arm64 (плюс-модели и новые ARM). Старый 32-bit ARM — не взлетит.

Firewall DSM: исходящие 443 к `api.telegram.org` и `wss://ws-api.oneme.ru` не режь.

### VPS

Клон репо, `.env` руками, `systemd` с `Restart=always` и `ExecStart=.../python starter.py`. Либо тот же `docker compose up -d`.
