import subprocess
import time
import sys, os
import datetime
import html
import threading
from telegram import setup_alerts, alert
from dotenv import load_dotenv

load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
MONITOR_ID = os.getenv("MONITOR_ID") or os.getenv("TG_CHAT_ID")
setup_alerts(TG_BOT_TOKEN, MONITOR_ID)

def run_with_restart():
    while True:
        try:
            print(f"[{datetime.datetime.now()}] Запуск main.py...")
            process = subprocess.Popen(
                [sys.executable, "-u", "main.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            err_buf = []

            def _read_out():
                for line in process.stdout:
                    sys.stdout.write(line)
                    err_buf.append(line)
                    if len(err_buf) > 80:
                        err_buf.pop(0)

            threading.Thread(target=_read_out, daemon=True).start()
            code = process.wait()
            tail = "".join(err_buf)[-1500:]
            alert(
                f"main.py упал (код {code})\n<pre>{html.escape(tail) or 'нет вывода'}</pre>",
                key="crash",
                cooldown=20,
            )
            print(f"[{datetime.datetime.now()}] упал код {code}, рестарт 3с")
            time.sleep(3)
        except KeyboardInterrupt:
            print(f"\n[{datetime.datetime.now()}] остановлено")
            try:
                process.terminate()
            except Exception:
                pass
            break
        except Exception as e:
            print(f"[{datetime.datetime.now()}] {e}")
            alert(f"starter: {e}", key="starter", cooldown=60)
            time.sleep(3)

if __name__ == "__main__":
    run_with_restart()
