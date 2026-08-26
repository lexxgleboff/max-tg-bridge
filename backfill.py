"""Остановить starter.py, потом: python backfill.py [chat_id] [limit]"""
import os, sys, time
from dotenv import load_dotenv
from max import MaxClient as Client
from telegram import send_to_telegram, unwrap_msg, format_control, parse_bridges

load_dotenv()

CHAT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else -72295902829133
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
BATCH = 50

MAX_TOKEN = os.getenv("MAX_TOKEN")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
MAX_TO_TG, _ = parse_bridges()
TG_CHAT_ID = MAX_TO_TG.get(CHAT_ID) or int(os.getenv("TG_CHAT_ID") or 0)
if not TG_CHAT_ID:
    sys.exit(f"нет моста для MAX {CHAT_ID}: проверь BRIDGES")


def load_all(client, chat_id):
    seen, out = set(), []
    from_ts = int(time.time() * 1000)
    while True:
        batch = client.get_history(chat_id, from_ts, BATCH)
        if not batch:
            break
        added = 0
        times = []
        for m in batch:
            mid = m.get("id")
            times.append(m.get("time") or from_ts)
            if mid in seen or m.get("status") == "REMOVED":
                continue
            seen.add(mid)
            out.append(m)
            added += 1
        oldest = min(times)
        if added == 0 or oldest >= from_ts:
            break
        from_ts = oldest
        if LIMIT and len(out) >= LIMIT:
            break
        print(f"история: {len(out)}")
    out.sort(key=lambda m: m.get("time") or 0)
    return out[-LIMIT:] if LIMIT else out


def main():
    print(f"чат {CHAT_ID} → TG {TG_CHAT_ID}")
    print("starter.py должен быть остановлен")
    client = Client(MAX_TOKEN)
    client.connect()
    names = {}

    def uname(uid):
        if uid not in names:
            try:
                u = client.get_user(id=uid, _f=1)
                names[uid] = u.contact.names[0].name if u.contact.names else str(uid)
            except Exception:
                names[uid] = str(uid)
        return names[uid]

    msgs = load_all(client, CHAT_ID)
    print(f"к отправке: {len(msgs)}")
    for i, m in enumerate(msgs, 1):
        try:
            text, attaches, sid = unwrap_msg(m)
            name = uname(sid)
            controls = [a for a in attaches if a.get("_type") == "CONTROL"]
            media = [a for a in attaches if a.get("_type") != "CONTROL"]
            for c in controls:
                t = format_control(c, name, uname)
                if t:
                    send_to_telegram(TG_BOT_TOKEN, TG_CHAT_ID, t)
            if text or media:
                cap = f"<b>{name}</b>\n{text}" if text else f"<b>{name}</b>"
                send_to_telegram(TG_BOT_TOKEN, TG_CHAT_ID, cap, media)
            print(f"{i}/{len(msgs)}")
        except Exception as e:
            print(f"{i}/{len(msgs)} skip: {e}")
        time.sleep(3.1)
    client.disconnect()
    print("готово")


if __name__ == "__main__":
    main()
