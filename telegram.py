import html
import os
import time
import sys
import requests, json

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CAPTION_LIMIT = 1024

def parse_bridges():
    raw = (os.getenv("BRIDGES") or "").strip()
    pairs = []
    if raw:
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            a, b = part.split(":", 1)
            pairs.append((int(a.strip()), int(b.strip())))
    else:
        max_ids = [int(x) for x in (os.getenv("MAX_CHAT_IDS") or "").split(",") if x.strip()]
        tg = os.getenv("TG_CHAT_ID")
        if max_ids and tg:
            tgid = int(tg)
            pairs = [(m, tgid) for m in max_ids]
    max_to_tg, tg_to_max = {}, {}
    for m, t in pairs:
        max_to_tg[m] = t
        tg_to_max.setdefault(t, []).append(m)
    return max_to_tg, tg_to_max

_tg_titles: dict[int, str] = {}

def tg_chat_title(token: str, chat_id: int) -> str:
    if chat_id in _tg_titles:
        return _tg_titles[chat_id]
    try:
        r = _get(f"https://api.telegram.org/bot{token}/getChat", {"chat_id": chat_id}, timeout=10).json()
        ch = r.get("result") or {}
        title = ch.get("title") or ch.get("first_name") or ch.get("username") or ""
    except Exception as e:
        print("tg_chat_title:", e)
        title = ""
    _tg_titles[chat_id] = title
    return title

def remember_tg_title(chat_id: int, title: str):
    if title:
        _tg_titles[chat_id] = title

def _post(url, **kwargs):
    last = None
    for i in range(3):
        try:
            return requests.post(url, timeout=30, **kwargs)
        except requests.RequestException as e:
            last = e
            time.sleep(1 + i)
    raise last

def unwrap_msg(m: dict) -> tuple[str, list, object]:
    link = m.get("link") or {}
    if link.get("type") == "FORWARD" and link.get("message"):
        src = link["message"]
        return src.get("text") or "", src.get("attaches") or [], src.get("sender") or m.get("sender")
    text = m.get("text") or ""
    if link.get("type") == "REPLY":
        q = (link.get("message") or {}).get("text") or ""
        if q:
            text = f"↪ {q[:300]}\n{text}" if text else f"↪ {q[:300]}"
    return text, m.get("attaches") or [], m.get("sender")

def is_poll(a: dict) -> bool:
    t = a.get("_type")
    p = a.get("poll") if isinstance(a.get("poll"), dict) else a
    if t == "POLL" or p.get("_type") == "POLL":
        return True
    return bool(p.get("answers") or p.get("options") or p.get("pollId"))

def format_poll(a: dict) -> str:
    p = a.get("poll") if isinstance(a.get("poll"), dict) else a
    title = p.get("title") or p.get("question") or a.get("title") or ""
    answers = p.get("answers") or p.get("options") or []
    lines = []
    if title:
        lines.append(f"📊 {html.escape(str(title))}")
    for k in ("subtitle", "description"):
        if p.get(k):
            lines.append(html.escape(str(p[k])))
    total = p.get("voteCount") or p.get("totalCount")
    summed = 0
    for ans in answers:
        if isinstance(ans, str):
            text, n = ans, None
        else:
            text = str(ans.get("text") or ans.get("title") or ans.get("name") or "")
            n = ans.get("count") or ans.get("voteCount") or ans.get("votes")
            if n is None:
                ids = ans.get("voterIds") or ans.get("userIds") or ans.get("voters")
                n = len(ids) if isinstance(ids, list) else None
        if isinstance(n, int):
            summed += n
            lines.append(f"• {html.escape(text)} — {n}")
        else:
            lines.append(f"• {html.escape(text)}")
    if not isinstance(total, int):
        total = summed
    if total:
        lines.append(f"{total} голосов")
    if not lines:
        print("poll dump", {k: p.get(k) for k in list(p)[:20]})
        return "опрос"
    return "\n".join(lines)

def format_control(attach: dict, actor: str, uname) -> str:
    ev = attach.get("event")
    if ev == "add":
        who = ", ".join(uname(i) for i in attach.get("userIds") or [])
        return f"{actor} добавил(а) {who} в чат"
    if ev == "remove":
        return f"{actor} удалил(а) {uname(attach.get('userId'))} из чата"
    if ev == "leave":
        return f"{actor} вышел(а) из чата"
    if ev == "joinByLink":
        return f"{actor} вступил(а) в чат по ссылке"
    if ev == "title":
        return f"{actor} изменил(а) название: {attach.get('title') or ''}"
    if ev == "pin":
        return f"{actor} закрепил(а) сообщение"
    if ev == "system":
        return attach.get("message") or attach.get("shortMessage") or ""
    return ""

def handle_attach(attach: dict) -> str:
    t = attach.get("_type")
    if is_poll(attach):
        return format_poll(attach)
    match t:
        case "CONTROL" | "PHOTO" | "VIDEO" | "AUDIO" | "STICKER" | "WIDGET":
            return ""
        case "FILE":
            return "" if attach_url(attach) else (attach.get("name") or "файл")
        case "UNSUPPORTED":
            if attach.get("audioId") or attach.get("duration"):
                return "голосовое"
            print("unsupported attach", list(attach.keys()))
            return "вложение"
        case _:
            print("unknown attach", t, list(attach.keys()))
            return t or ""

def attach_url(a: dict) -> str | None:
    for k in ("baseUrl", "baseRawUrl", "url", "mp4Url", "MP4_1080"):
        u = a.get(k)
        if u:
            return u
    return None

def _send_media(token, chat_id, method, field, url, caption="", extra=None):
    data = {"chat_id": chat_id, field: url}
    if caption:
        data["caption"] = caption[:CAPTION_LIMIT]
        data["parse_mode"] = "HTML"
    if extra:
        data.update(extra)
    body = _post(f"https://api.telegram.org/bot{token}/{method}", data=data).json()
    if body.get("error_code") == 429:
        time.sleep(body.get("parameters", {}).get("retry_after", 3))
        return _send_media(token, chat_id, method, field, url, caption, extra)
    if not body.get("ok") and caption:
        data.pop("parse_mode", None)
        body = _post(f"https://api.telegram.org/bot{token}/{method}", data=data).json()
    print(body)
    return body

def _send_text(token, chat_id, text, parse=True, reply_to=None):
    if not text:
        return
    data = {"chat_id": chat_id, "text": text}
    if parse:
        data["parse_mode"] = "HTML"
    if reply_to:
        data["reply_to_message_id"] = reply_to
        data["allow_sending_without_reply"] = "true"
    body = _post(f"https://api.telegram.org/bot{token}/sendMessage", data=data).json()
    if body.get("error_code") == 429:
        time.sleep(body.get("parameters", {}).get("retry_after", 3))
        return _send_text(token, chat_id, text, parse, reply_to)
    if not body.get("ok") and parse:
        return _send_text(token, chat_id, text, parse=False, reply_to=reply_to)
    print(body)
    return body

def _msg_ids(body) -> list[int]:
    if not body or not body.get("ok"):
        return []
    r = body.get("result")
    if isinstance(r, list):
        return [x["message_id"] for x in r if isinstance(x, dict) and x.get("message_id")]
    if isinstance(r, dict) and r.get("message_id"):
        return [r["message_id"]]
    return []

TG_REACT = {
    "❤", "👍", "👎", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", "🤬", "😢", "🎉",
    "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳", "🌚", "🌭",
    "💯", "🤣", "⚡", "🍌", "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈",
    "😴", "😭", "🤓", "👻", "👀", "🎃", "🙈", "😇", "😨", "🤝", "✍", "🤗", "🫡",
    "🎅", "🎄", "☃", "💅", "🤪", "🗿", "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊",
    "😎", "👾", "🤷", "😡", "⭐",
}

def _norm_react(e: str) -> str | None:
    e = (e or "").strip()
    if not e:
        return None
    base = e.replace("\ufe0f", "")
    if e in TG_REACT:
        return e
    if base in TG_REACT:
        return base
    if base == "❤" or e in ("❤️", "♥"):
        return "❤"
    return None

def set_tg_reaction(token, chat_id, message_id, emojis: list[str]):
    seen, arr = set(), []
    for e in emojis:
        n = _norm_react(e)
        if n and n not in seen:
            seen.add(n)
            arr.append({"type": "emoji", "emoji": n})
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": json.dumps(arr[:1]),
    }
    body = _post(f"https://api.telegram.org/bot{token}/setMessageReaction", data=data).json()
    if not body.get("ok"):
        print("react fail:", body)
    return body

def send_to_telegram(TG_BOT_TOKEN: str="", TG_CHAT_ID: int = 0, caption: str = "", attachments: list[dict] = []):
    photos, videos, rest = [], [], []
    for a in attachments or []:
        t = a.get("_type")
        u = attach_url(a)
        if t == "PHOTO" and u:
            photos.append(a)
        elif t == "VIDEO" and u:
            videos.append(a)
        else:
            rest.append(a)

    extra = ", ".join(x for a in rest if (x := handle_attach(a)))
    if extra:
        caption = f"{caption}\n\n{extra}" if caption else extra

    album = photos + [v for v in videos if v.get("videoType") != 1]
    notes = [v for v in videos if v.get("videoType") == 1]
    cap_left = caption

    ids = []
    if album:
        overflow = ""
        cap = cap_left
        if cap and len(cap) > CAPTION_LIMIT:
            overflow, cap = cap, ""
        media = []
        for i, a in enumerate(album[:10]):
            kind = "video" if a.get("_type") == "VIDEO" else "photo"
            item = {"type": kind, "media": attach_url(a)}
            if i == 0 and cap:
                item["caption"] = cap
                item["parse_mode"] = "HTML"
            media.append(item)
        body = _post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup",
            data={"chat_id": TG_CHAT_ID, "media": json.dumps(media)},
        ).json()
        if body.get("error_code") == 429:
            time.sleep(body.get("parameters", {}).get("retry_after", 3))
            return send_to_telegram(TG_BOT_TOKEN, TG_CHAT_ID, caption, attachments)
        if not body.get("ok") and cap:
            for it in media:
                it.pop("parse_mode", None)
            body = _post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup",
                data={"chat_id": TG_CHAT_ID, "media": json.dumps(media)},
            ).json()
        print(body)
        ids.extend(_msg_ids(body))
        if overflow:
            ids.extend(_msg_ids(_send_text(TG_BOT_TOKEN, TG_CHAT_ID, overflow)))
        cap_left = ""
        if len(album) > 10:
            ids.extend(send_to_telegram(TG_BOT_TOKEN, TG_CHAT_ID, "", album[10:]) or [])

    sent_cap = bool(album)
    for a in notes:
        ids.extend(_msg_ids(_send_media(TG_BOT_TOKEN, TG_CHAT_ID, "sendVideoNote", "video_note", attach_url(a))))
    for a in rest:
        t, u = a.get("_type"), attach_url(a)
        cap = cap_left if not sent_cap else ""
        if t == "STICKER" and u:
            method, field = ("sendAnimation", "animation") if a.get("mp4Url") or (u or "").endswith(".mp4") else ("sendSticker", "sticker")
            ids.extend(_msg_ids(_send_media(TG_BOT_TOKEN, TG_CHAT_ID, method, field, a.get("mp4Url") or u, cap)))
            sent_cap = True
            cap_left = ""
        elif t == "AUDIO" and u:
            ids.extend(_msg_ids(_send_media(TG_BOT_TOKEN, TG_CHAT_ID, "sendVoice", "voice", u, cap)))
            sent_cap = True
            cap_left = ""
        elif t == "FILE" and u:
            ids.extend(_msg_ids(_send_media(TG_BOT_TOKEN, TG_CHAT_ID, "sendDocument", "document", u, cap)))
            sent_cap = True
            cap_left = ""

    if cap_left:
        ids.extend(_msg_ids(_send_text(TG_BOT_TOKEN, TG_CHAT_ID, cap_left)))
    return ids

def _get(url, params=None, timeout=40):
    last = None
    for i in range(3):
        try:
            return requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            last = e
            time.sleep(1 + i)
    raise last

def drain_updates(token: str) -> int | None:
    r = _get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout": 0, "allowed_updates": json.dumps(["message", "channel_post"])}, timeout=15)
    data = r.json()
    if not data.get("ok") or not data.get("result"):
        return None
    return data["result"][-1]["update_id"] + 1

def get_updates(token: str, offset: int | None = None, timeout: int = 30) -> list:
    params = {"timeout": timeout, "allowed_updates": json.dumps(["message", "channel_post"])}
    if offset is not None:
        params["offset"] = offset
    r = _get(f"https://api.telegram.org/bot{token}/getUpdates", params=params, timeout=timeout + 10)
    data = r.json()
    if not data.get("ok"):
        print(data)
        return []
    return data.get("result") or []

_alert_token = None
_alert_chat = None
_alert_last: dict[str, float] = {}

def setup_alerts(token, chat_id):
    global _alert_token, _alert_chat
    _alert_token = token
    try:
        _alert_chat = int(chat_id) if chat_id else None
    except (TypeError, ValueError):
        _alert_chat = None

def alert(text: str, key: str | None = None, cooldown: int = 60):
    key = key or text
    now = time.time()
    if now - _alert_last.get(key, 0) < cooldown:
        return
    _alert_last[key] = now
    print("ALERT:", text)
    if not _alert_token or not _alert_chat:
        return
    try:
        _send_text(_alert_token, _alert_chat, "⚙️ " + text)
    except Exception as e:
        print("alert fail:", e)
