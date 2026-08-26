from max import MaxClient as Client
from filters import filters
from classes import Message
from telegram import send_to_telegram, drain_updates, get_updates, format_control, setup_alerts, alert, parse_bridges, tg_chat_title, remember_tg_title
import os, time, html, sys
from dotenv import load_dotenv
import threading

load_dotenv()

MAX_TOKEN = os.getenv("MAX_TOKEN")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
MAX_TO_TG, TG_TO_MAX = parse_bridges()
MONITOR_ID = os.getenv("MONITOR_ID") or ""
ALERT_CHAT = int(MONITOR_ID) if MONITOR_ID.strip() else next(iter(MAX_TO_TG.values()), None)
if not MAX_TOKEN or not TG_BOT_TOKEN or not MAX_TO_TG or not ALERT_CHAT:
    print("Ошибка в .env: нужны MAX_TOKEN, TG_BOT_TOKEN и BRIDGES (или MAX_CHAT_IDS+TG_CHAT_ID)")
    sys.exit(1)

setup_alerts(TG_BOT_TOKEN, ALERT_CHAT)
client = Client(MAX_TOKEN)

_sent_lock = threading.Lock()
_sent_to_max = []
STATE = {"up": time.time(), "last_max": None, "last_tg": None, "ok": False}

def remember_max_out(max_id: int, text: str):
    with _sent_lock:
        _sent_to_max.append((max_id, text, time.time()))

def is_max_echo(max_id: int, text: str) -> bool:
    now = time.time()
    with _sent_lock:
        _sent_to_max[:] = [(i, t, ts) for i, t, ts in _sent_to_max if now - ts < 20]
        return any(i == max_id and t == text for i, t, _ in _sent_to_max)

def _dur(ts):
    if not ts:
        return "0с"
    s = int(time.time() - ts)
    if s < 60:
        return f"{s}с"
    if s < 3600:
        return f"{s // 60}м"
    return f"{s // 3600}ч {(s % 3600) // 60}м"

def _ago(ts):
    if not ts:
        return "ещё не было"
    return _dur(ts) + " назад"

def _lab(cid, name):
    n = html.escape(name) if name else "?"
    return f"<code>{cid}</code> ({n})"

def refresh_names():
    try:
        if client._connected:
            client.get_chat_titles(list(MAX_TO_TG))
    except Exception as e:
        print("max titles:", e)
    for t in set(MAX_TO_TG.values()):
        try:
            tg_chat_title(TG_BOT_TOKEN, t)
        except Exception as e:
            print("tg title:", e)

def status_text():
    refresh_names()
    me = ""
    if client.me and client.me.contact.names:
        me = client.me.contact.names[0].name
    lines = [_lab(m, client._chat_titles.get(m, "")) + " -> " + _lab(t, tg_chat_title(TG_BOT_TOKEN, t)) for m, t in MAX_TO_TG.items()]
    return (
        f"<b>статус</b>\n"
        f"MAX: {'онлайн' if client._connected else 'оффлайн'}"
        + (f" ({me})" if me else "") + "\n"
        f"в работе: {_dur(STATE['up'])}\n"
        f"последняя MAX->TG: {_ago(STATE['last_max'])}\n"
        f"последняя TG->MAX: {_ago(STATE['last_tg'])}\n"
        + "\n".join(lines)
    )

@client.on_connect
def onconnect():
    STATE["ok"] = True
    name = "?"
    if client.me and client.me.contact.names:
        name = client.me.contact.names[0].name
        print(f"Имя: {name}, Номер: {client.me.contact.phone} | ID: {client.me.contact.id}")
    alert(f"MAX онлайн: {name}", key="max_up", cooldown=20)
    threading.Thread(target=_log_bridges, daemon=True).start()

def _log_bridges():
    refresh_names()
    for m, t in MAX_TO_TG.items():
        print(f"мост {m} ({client._chat_titles.get(m) or '?'}) -> {t} ({tg_chat_title(TG_BOT_TOKEN, t) or '?'})")

def _uname(client, uid):
    try:
        u = client.get_user(id=uid, _f=1)
        if u.contact.names:
            return u.contact.names[0].name
    except Exception:
        pass
    return str(uid)

client._on_disconnect = lambda: alert("MAX websocket оборван, переподключаюсь", key="ws_down", cooldown=30)
client._on_auth_error = lambda e: alert(f"MAX токен невалиден: {e}\nОбнови MAX_TOKEN в .env (web.max.ru)", key="auth", cooldown=300)
client._on_error = lambda e: alert(str(e), key=str(e)[:50], cooldown=120)

@client.on_message(filters.any())
def onmessage(client: Client, message: Message):
    if is_max_echo(message.chat.id, message.text):
        return
    tg_id = MAX_TO_TG.get(message.chat.id)
    if tg_id and message.status != "REMOVED":
        msg_text = message.text
        msg_attaches = message.attaches
        name = "?"
        if message.user and message.user.contact.names:
            name = message.user.contact.names[0].name
        elif message.sender:
            name = str(message.sender)
        if "link" in message.kwargs.keys():
            if "type" in message.kwargs["link"]:
                if message.kwargs["link"]["type"] == "REPLY":
                    q = (message.kwargs["link"].get("message") or {}).get("text") or ""
                    if q:
                        msg_text = f"<i>↪ {html.escape(q[:300])}</i>\n{msg_text or ''}"
                if message.kwargs["link"]["type"] == "FORWARD":
                    msg_text = message.kwargs["link"]["message"]["text"]
                    msg_attaches = message.kwargs["link"]["message"]["attaches"]
                    forwarded_msg_author = client.get_user(id=message.kwargs["link"]["message"]["sender"], _f=1)
                    name = f"{name}\n(Переслано: {forwarded_msg_author.contact.names[0].name})"

        controls = [a for a in msg_attaches if a.get("_type") == "CONTROL"]
        media = [a for a in msg_attaches if a.get("_type") != "CONTROL"]
        try:
            for c in controls:
                t = format_control(c, name, lambda uid, cl=client: _uname(cl, uid))
                if t:
                    send_to_telegram(TG_BOT_TOKEN, tg_id, t)
            if msg_text or media:
                send_to_telegram(
                    TG_BOT_TOKEN,
                    tg_id,
                    f"<b>{name}</b>\n{msg_text}" if msg_text else f"<b>{name}</b>",
                    media
                )
            STATE["last_max"] = time.time()
        except Exception as e:
            alert(f"отправка в TG: {e}", key="tg_send", cooldown=120)

def tg_poll():
    offset = None
    try:
        offset = drain_updates(TG_BOT_TOKEN)
    except Exception as e:
        print("TG drain:", e)
        alert(f"TG getUpdates: {e}", key="tg_drain", cooldown=120)
    while True:
        try:
            for upd in get_updates(TG_BOT_TOKEN, offset):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post")
                if not msg:
                    continue
                chat_id = msg.get("chat", {}).get("id")
                remember_tg_title(chat_id, (msg.get("chat") or {}).get("title") or "")
                fr = msg.get("from") or {}
                text = (msg.get("text") or msg.get("caption") or "").strip()
                cmd = text.split("@")[0]
                if cmd == "/start":
                    uid = fr.get("id") or chat_id
                    send_to_telegram(
                        TG_BOT_TOKEN, chat_id,
                        f"твой user id: <code>{uid}</code>\n"
                        f"вставь в .env:\n<code>MONITOR_ID={uid}</code>\n"
                        f"потом /status"
                    )
                    continue
                if cmd in ("/status", "/ping"):
                    send_to_telegram(TG_BOT_TOKEN, chat_id, status_text())
                    continue
                max_ids = TG_TO_MAX.get(chat_id)
                if not max_ids:
                    continue
                if fr.get("is_bot") or text.startswith("/"):
                    continue
                if msg.get("photo") and not text:
                    text = "[фото]"
                if not text:
                    continue
                for max_id in max_ids:
                    remember_max_out(max_id, text)
                    client.send_text(max_id, text)
                STATE["last_tg"] = time.time()
        except Exception as e:
            print("TG poll:", e)
            alert(f"TG poll: {e}", key="tg_poll", cooldown=120)
            time.sleep(5)

try:
    client.run()
except ValueError as e:
    alert(str(e), key="boot", cooldown=10)
    raise
threading.Thread(target=tg_poll, name="TgPoll", daemon=True).start()
alert("скрипт запущен, жду MAX…", key="boot", cooldown=10)
threading.Event().wait()
