import os
import requests
from bs4 import BeautifulSoup
import re
import time
import threading
import telebot
from telebot import apihelper
from telebot.types import BotCommand
import gradio as gr

# --- Chẩn đoán mạng ---
def diagnose_network():
    print("🌐 Đang kiểm tra kết nối mạng...")
    targets = ["https://www.google.com", "https://api.telegram.org"]
    for target in targets:
        try:
            start = time.time()
            r = requests.get(target, timeout=10)
            print(f"✅ Kết nối đến {target} thành công (Status: {r.status_code}, Time: {time.time()-start:.2f}s)")
        except Exception as e:
            print(f"❌ Kết nối đến {target} thất bại: {e}")

# --- Cấu hình Timeout ---
apihelper.READ_TIMEOUT = 60
apihelper.CONNECT_TIMEOUT = 60

# Lấy Token
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN không tìm thấy!")
else:
    print(f"✅ Token loaded: {BOT_TOKEN[:5]}***{BOT_TOKEN[-5:]}")

bot = telebot.TeleBot(BOT_TOKEN)

# Quản lý trạng thái
auto_status = {}
price_alerts = {}

def get_gold_price():
    url = "https://giavang.org/the-gioi/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code != 200: return None, f"❌ Lỗi HTTP {response.status_code}"
        soup = BeautifulSoup(response.text, 'html.parser')
        price_span = soup.find('span', class_='crypto-price')
        if not price_span: return None, "❌ Không tìm thấy giá vàng"
        
        price_str = price_span.text.strip().replace(',', '')
        current_price = float(price_str)
        small_tag = soup.find('small')
        update_time = small_tag.text.strip() if small_tag else "Không xác định"
        
        time_match = re.search(r'\d{2}:\d{2}:\d{2}', update_time)
        short_time = time_match.group(0) if time_match else update_time

        text = soup.get_text()
        clean_text = ' '.join(text.split())
        vnd_match = re.search(r'giá là\s*([\d\.]+)\s*VNĐ', clean_text)
        vnd_price = vnd_match.group(1) if vnd_match else "Không xác định"
        
        msg = (
            f"💰 <b>{current_price} USD</b> | {vnd_price} VNĐ\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🌍 Giá Vàng Thế Giới\n"
            f"⏰ Cập nhật: {short_time}"
        )
        return current_price, msg
    except Exception as e:
        return None, f"❌ Lỗi: {str(e)}"

def set_bot_commands():
    commands = [
        BotCommand("start", "Xem hướng dẫn sử dụng"),
        BotCommand("manual", "Lấy giá vàng ngay"),
        BotCommand("auto", "Bật tự động gửi mỗi 10 phút"),
        BotCommand("stop", "Dừng gửi tự động"),
        BotCommand("checkprice", "Đặt báo động giá"),
        BotCommand("uncheck", "Hủy báo động giá")
    ]
    try:
        bot.set_my_commands(commands)
        print("✅ Đã thiết lập Menu lệnh.")
    except Exception as e:
        print(f"⚠️ Không thể thiết lập Menu lệnh: {e}. Bot vẫn sẽ tiếp tục chạy.")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "<b>Chào mừng bạn đến với Bot Giá Vàng!</b> 🌟\n\n"
        "▶️ /manual : Lấy giá ngay lập tức\n"
        "▶️ /auto : Gửi giá tự động mỗi 10 phút\n"
        "▶️ /stop : Dừng gửi tự động\n"
        "▶️ /checkprice [giá] : Báo chuông khi đạt giá\n"
        "▶️ /uncheck : Hủy bỏ báo giá\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['manual'])
def manual_fetch(message):
    _, msg = get_gold_price()
    bot.send_message(message.chat.id, msg, parse_mode="HTML")

# --- Polling Loop thủ công ---
def run_bot():
    if not BOT_TOKEN: return
    
    time.sleep(5)
    diagnose_network()
    set_bot_commands()
    
    print("🤖 Bot đang bắt đầu Polling...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ Lỗi Polling: {e}. Thử lại sau 15s...")
            time.sleep(15)

def dummy_fn():
    return "Bot is running!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    with gr.Blocks() as demo:
        gr.Markdown("# 🤖 Telegram Gold Price Bot")
        status = gr.Textbox(label="Status", value="Online")
        refresh = gr.Button("Check Status")
        refresh.click(fn=dummy_fn, outputs=status)
    
    demo.launch(server_name="0.0.0.0", server_port=7860)
