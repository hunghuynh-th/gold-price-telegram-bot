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

# --- Cấu hình Timeout & API ---
apihelper.READ_TIMEOUT = 60
apihelper.CONNECT_TIMEOUT = 60

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Quản lý trạng thái
auto_status = {}      # {chat_id: bool}
price_alerts = {}     # {chat_id: {"target": float, "direction": str}}
bot_started = False

def get_gold_price():
    url = "https://giavang.org/the-gioi/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=25)
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

# Cấu hình Menu lệnh
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
    except:
        pass

# --- Message Handlers ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "<b>Chào mừng bạn!</b> 🌟\n\n"
        "▶️ /manual : Lấy giá ngay lập tức\n"
        "▶️ /auto : Tự động gửi mỗi 10 phút\n"
        "▶️ /stop : Dừng gửi tự động\n"
        "▶️ /checkprice [giá] : Báo động khi đạt giá\n"
        "▶️ /uncheck : Hủy báo động\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['manual'])
def manual_fetch(message):
    _, msg = get_gold_price()
    bot.send_message(message.chat.id, msg, parse_mode="HTML")

# --- Logic Auto Send (10 phút) ---
def auto_worker(chat_id):
    while auto_status.get(chat_id, False):
        # Chờ 10 phút (chia nhỏ để có thể dừng ngay lập tức)
        for _ in range(60): 
            if not auto_status.get(chat_id, False): return
            time.sleep(10)
        
        if auto_status.get(chat_id, False):
            _, msg = get_gold_price()
            bot.send_message(chat_id, msg, parse_mode="HTML")

@bot.message_handler(commands=['auto'])
def start_auto(message):
    chat_id = message.chat.id
    if auto_status.get(chat_id, False):
        bot.send_message(chat_id, "⚠️ Đã bật tự động rồi.")
    else:
        auto_status[chat_id] = True
        bot.send_message(chat_id, "✅ Đã bật tự động gửi mỗi 10 phút. Đang lấy giá...")
        # Gửi ngay lập tức 1 lần
        _, msg = get_gold_price()
        bot.send_message(chat_id, msg, parse_mode="HTML")
        threading.Thread(target=auto_worker, args=(chat_id,), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop_auto(message):
    auto_status[message.chat.id] = False
    bot.send_message(message.chat.id, "🛑 Đã dừng gửi tự động.")

# --- Logic Price Alert ---
def check_price_worker(chat_id, target, direction):
    while chat_id in price_alerts and price_alerts[chat_id]['target'] == target:
        current, _ = get_gold_price()
        if current:
            triggered = False
            if direction == "UP" and current >= target: triggered = True
            elif direction == "DOWN" and current <= target: triggered = True
            
            if triggered:
                bot.send_message(chat_id, f"🎯 <b>MỤC TIÊU {target} USD ĐÃ ĐẠT!</b>\nGiá hiện tại: <code>{current}</code>", parse_mode="HTML")
                if chat_id in price_alerts: del price_alerts[chat_id]
                break
        time.sleep(60)

@bot.message_handler(commands=['checkprice'])
def set_price_alert(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Nhập giá: /checkprice 2750")
            return
        target = float(args[1])
        current, _ = get_gold_price()
        if not current:
            bot.reply_to(message, "❌ Lỗi lấy giá hiện tại.")
            return
        direction = "UP" if target > current else "DOWN"
        price_alerts[message.chat.id] = {"target": target, "direction": direction}
        bot.send_message(message.chat.id, f"🚀 Đã đặt cảnh báo: <b>{target} USD</b>", parse_mode="HTML")
        threading.Thread(target=check_price_worker, args=(message.chat.id, target, direction), daemon=True).start()
    except ValueError:
        bot.reply_to(message, "❌ Giá không hợp lệ.")

@bot.message_handler(commands=['uncheck'])
def uncheck_price(message):
    if message.chat.id in price_alerts:
        del price_alerts[message.chat.id]
        bot.send_message(message.chat.id, "🚫 Đã hủy báo giá.")
    else:
        bot.send_message(message.chat.id, "⚠️ Chưa đặt báo giá nào.")

def run_bot():
    global bot_started
    if bot_started: return
    bot_started = True
    
    if not BOT_TOKEN: return
    
    try:
        bot.remove_webhook()
    except:
        pass
        
    time.sleep(5)
    set_bot_commands()
    
    print("🤖 Bot đang chạy trên Render...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            if "Conflict" in str(e):
                time.sleep(30)
            else:
                time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 7860))
    with gr.Blocks() as demo:
        gr.Markdown("# 🤖 Telegram Gold Bot")
        gr.Markdown("Bot is running 24/7 on Render.")
    demo.launch(server_name="0.0.0.0", server_port=port)
