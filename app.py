import os
import re
import json
import html
import hmac
import time
import functools
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
import telebot
from telebot import apihelper
from telebot.types import BotCommand

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
apihelper.READ_TIMEOUT = 60
apihelper.CONNECT_TIMEOUT = 60

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TICK_SECRET = os.environ.get("TICK_SECRET", "")
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise SystemExit("Thiếu biến môi trường TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

AUTO_KEY = "gold:auto"      # Redis SET  : các chat_id đang bật /auto
ALERT_KEY = "gold:alerts"   # Redis HASH : chat_id -> {"target":..., "direction":...}


# ---------------------------------------------------------------------------
# Lưu trữ: Upstash Redis (REST). Nếu thiếu biến môi trường thì dùng RAM (mất khi restart)
# ---------------------------------------------------------------------------
class Store:
    def __init__(self):
        self.use_redis = bool(REDIS_URL and REDIS_TOKEN)
        self._auto = set()
        self._alerts = {}
        if not self.use_redis:
            print("⚠️ Chưa cấu hình Upstash Redis: trạng thái chỉ lưu trong RAM, restart là mất.")

    def _cmd(self, *args):
        r = requests.post(
            REDIS_URL,
            headers={"Authorization": f"Bearer {REDIS_TOKEN}"},
            json=list(args),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result")

    # --- auto ---
    def auto_add(self, cid):
        if self.use_redis:
            self._cmd("SADD", AUTO_KEY, str(cid))
        else:
            self._auto.add(cid)

    def auto_remove(self, cid):
        if self.use_redis:
            self._cmd("SREM", AUTO_KEY, str(cid))
        else:
            self._auto.discard(cid)

    def auto_is_on(self, cid):
        if self.use_redis:
            return bool(self._cmd("SISMEMBER", AUTO_KEY, str(cid)))
        return cid in self._auto

    def auto_list(self):
        if self.use_redis:
            return [int(x) for x in (self._cmd("SMEMBERS", AUTO_KEY) or [])]
        return list(self._auto)

    # --- alerts ---
    def alert_set(self, cid, target, direction):
        data = {"target": target, "direction": direction}
        if self.use_redis:
            self._cmd("HSET", ALERT_KEY, str(cid), json.dumps(data))
        else:
            self._alerts[cid] = data

    def alert_exists(self, cid):
        if self.use_redis:
            return self._cmd("HGET", ALERT_KEY, str(cid)) is not None
        return cid in self._alerts

    def alert_del(self, cid):
        if self.use_redis:
            self._cmd("HDEL", ALERT_KEY, str(cid))
        else:
            self._alerts.pop(cid, None)

    def alert_all(self):
        if self.use_redis:
            flat = self._cmd("HGETALL", ALERT_KEY) or []
            return {int(flat[i]): json.loads(flat[i + 1]) for i in range(0, len(flat), 2)}
        return dict(self._alerts)


store = Store()


# ---------------------------------------------------------------------------
# Lấy giá vàng
# ---------------------------------------------------------------------------
def get_gold_price():
    url = "https://giavang.org/the-gioi/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=25)
        if response.status_code != 200:
            return None, f"❌ Lỗi HTTP {response.status_code}"

        soup = BeautifulSoup(response.text, "html.parser")
        price_span = soup.find("span", class_="crypto-price")
        if not price_span:
            return None, "❌ Không tìm thấy giá vàng"

        current_price = float(price_span.text.strip().replace(",", ""))

        small_tag = soup.find("small")
        update_time = small_tag.text.strip() if small_tag else "Không xác định"
        time_match = re.search(r"\d{2}:\d{2}:\d{2}", update_time)
        short_time = time_match.group(0) if time_match else update_time

        clean_text = " ".join(soup.get_text().split())
        vnd_match = re.search(r"giá là\s*([\d\.]+)\s*VNĐ", clean_text)
        vnd_price = vnd_match.group(1) if vnd_match else "Không xác định"

        msg = (
            f"💰 <b>{current_price} USD</b> | {vnd_price} VNĐ\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🌍 Giá Vàng Thế Giới\n"
            f"⏰ Cập nhật: {short_time}"
        )
        return current_price, msg
    except Exception as e:
        return None, f"❌ Lỗi: {html.escape(str(e))}"


# ---------------------------------------------------------------------------
# Gửi tin an toàn: không bao giờ ném exception ra ngoài
# ---------------------------------------------------------------------------
def safe_send(chat_id, text):
    try:
        bot.send_message(chat_id, text, parse_mode="HTML")
        return True
    except apihelper.ApiTelegramException as e:
        print(f"[send] lỗi chat {chat_id}: {e}")
        # 403: user chặn bot, 400: chat không còn tồn tại -> dọn dữ liệu
        if e.error_code in (400, 403):
            try:
                store.auto_remove(chat_id)
                store.alert_del(chat_id)
            except Exception as ex:
                print("[send] dọn dữ liệu lỗi:", ex)
    except Exception as e:
        print(f"[send] lỗi chat {chat_id}: {e}")
    return False


def guard(fn):
    """Bọc handler: lỗi bất ngờ (vd Redis) không làm bot im lặng."""
    @functools.wraps(fn)
    def wrapper(message):
        try:
            fn(message)
        except Exception as e:
            print(f"[handler {fn.__name__}] lỗi: {e}")
            safe_send(message.chat.id, "⚠️ Có lỗi xảy ra, thử lại sau nhé.")
    return wrapper


# ---------------------------------------------------------------------------
# Lệnh Telegram
# ---------------------------------------------------------------------------
def set_bot_commands():
    commands = [
        BotCommand("start", "Xem hướng dẫn sử dụng"),
        BotCommand("manual", "Lấy giá vàng ngay"),
        BotCommand("auto", "Bật tự động gửi định kỳ"),
        BotCommand("stop", "Dừng gửi tự động"),
        BotCommand("checkprice", "Đặt báo động giá"),
        BotCommand("uncheck", "Hủy báo động giá"),
    ]
    try:
        bot.set_my_commands(commands)
    except Exception as e:
        print("set_my_commands lỗi:", e)


@bot.message_handler(commands=["start", "help"])
@guard
def send_welcome(message):
    help_text = (
        "<b>Chào mừng bạn!</b> 🌟\n\n"
        "▶️ /manual : Lấy giá ngay lập tức\n"
        "▶️ /auto : Tự động gửi định kỳ (mỗi ~10 phút)\n"
        "▶️ /stop : Dừng gửi tự động\n"
        "▶️ /checkprice [giá] : Báo động khi đạt giá\n"
        "▶️ /uncheck : Hủy báo động\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")


@bot.message_handler(commands=["manual"])
@guard
def manual_fetch(message):
    _, msg = get_gold_price()
    safe_send(message.chat.id, msg)


@bot.message_handler(commands=["auto"])
@guard
def start_auto(message):
    chat_id = message.chat.id
    if store.auto_is_on(chat_id):
        safe_send(chat_id, "⚠️ Đã bật tự động rồi.")
        return
    store.auto_add(chat_id)
    safe_send(chat_id, "✅ Đã bật tự động gửi định kỳ (~10 phút/lần). Đang lấy giá...")
    _, msg = get_gold_price()
    safe_send(chat_id, msg)


@bot.message_handler(commands=["stop"])
@guard
def stop_auto(message):
    store.auto_remove(message.chat.id)
    safe_send(message.chat.id, "🛑 Đã dừng gửi tự động.")


@bot.message_handler(commands=["checkprice"])
@guard
def set_price_alert(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Nhập giá: /checkprice 2750")
        return
    try:
        target = float(args[1])
    except ValueError:
        bot.reply_to(message, "❌ Giá không hợp lệ.")
        return

    current, _ = get_gold_price()
    if not current:
        bot.reply_to(message, "❌ Lỗi lấy giá hiện tại.")
        return

    direction = "UP" if target > current else "DOWN"
    store.alert_set(message.chat.id, target, direction)
    safe_send(message.chat.id, f"🚀 Đã đặt cảnh báo: <b>{target} USD</b>")


@bot.message_handler(commands=["uncheck"])
@guard
def uncheck_price(message):
    if store.alert_exists(message.chat.id):
        store.alert_del(message.chat.id)
        safe_send(message.chat.id, "🚫 Đã hủy báo giá.")
    else:
        safe_send(message.chat.id, "⚠️ Chưa đặt báo giá nào.")


# ---------------------------------------------------------------------------
# /tick: cron-job.org gọi vào đây để kích hoạt gửi tin
# ---------------------------------------------------------------------------
tick_lock = threading.Lock()


def check_alerts(current):
    for chat_id, a in store.alert_all().items():
        target, direction = a["target"], a["direction"]
        # Kích hoạt khi giá chạm, vượt qua hoặc nằm trong ±3 USD so với mục tiêu
        if direction == "UP":
            near, reached = current >= target - 3, current >= target
        else:
            near, reached = current <= target + 3, current <= target
        if not near:
            continue
        status = "ĐÃ ĐẠT" if reached else "GẦN CHẠM"
        store.alert_del(chat_id)
        safe_send(
            chat_id,
            f"🎯 <b>MỤC TIÊU {target} USD {status}!</b>\nGiá hiện tại: <code>{current}</code>",
        )


def run_tick(only):
    # Nếu tick trước còn đang chạy thì bỏ qua, tránh gửi trùng
    if not tick_lock.acquire(blocking=False):
        print("[tick] bỏ qua: tick trước vẫn đang chạy")
        return
    try:
        start = time.time()
        current, msg = get_gold_price()
        if current is None:
            print("[tick] lấy giá lỗi:", msg)
            return

        sent = 0
        if only in ("all", "auto"):
            for chat_id in store.auto_list():
                if safe_send(chat_id, msg):
                    sent += 1
        if only in ("all", "alert"):
            check_alerts(current)
        print(f"[tick:{only}] giá={current} đã gửi={sent} ({time.time() - start:.1f}s)")
    except Exception as e:
        print("[tick] lỗi:", e)
    finally:
        tick_lock.release()


# ---------------------------------------------------------------------------
# HTTP server nhẹ (thay Gradio)
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _route(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)

        if url.path in ("/", "/health"):
            return self._reply(200, "OK")

        if url.path == "/tick":
            if self.command != "GET":
                return self._reply(405, "method not allowed")
            key = q.get("key", [self.headers.get("X-Tick-Key", "")])[0]
            if not TICK_SECRET or not hmac.compare_digest(key, TICK_SECRET):
                return self._reply(403, "forbidden")
            only = q.get("only", ["all"])[0]
            if only not in ("all", "auto", "alert"):
                only = "all"
            # Trả lời ngay để cron không bị timeout, việc nặng chạy nền
            threading.Thread(target=run_tick, args=(only,), daemon=True).start()
            return self._reply(200, "tick accepted")

        return self._reply(404, "not found")

    do_GET = _route
    do_HEAD = _route

    def log_message(self, *args):
        pass  # không log request để tránh lộ key trong log


# ---------------------------------------------------------------------------
# Polling Telegram (nhận lệnh từ user)
# ---------------------------------------------------------------------------
def run_bot():
    try:
        bot.remove_webhook()
    except Exception:
        pass
    time.sleep(5)
    set_bot_commands()
    print("🤖 Bot đang chạy trên Render...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("[polling] lỗi:", e)
            time.sleep(30 if "Conflict" in str(e) else 10)


if __name__ == "__main__":
    if not TICK_SECRET:
        print("⚠️ Chưa đặt TICK_SECRET: endpoint /tick sẽ từ chối mọi request.")
    threading.Thread(target=run_bot, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()