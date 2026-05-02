import os
import requests
from bs4 import BeautifulSoup
import re
import time
import threading
import telebot
from telebot.types import BotCommand
import gradio as gr

# Lấy thông tin từ biến môi trường
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Quản lý trạng thái
auto_status = {}      # {chat_id: bool}
price_alerts = {}     # {chat_id: {"target": float, "direction": str}}

def get_gold_price():
    url = "https://giavang.org/the-gioi/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None, f"❌ Lỗi HTTP {response.status_code}"
        soup = BeautifulSoup(response.text, 'html.parser')
        price_span = soup.find('span', class_='crypto-price')
        if not price_span: return None, "❌ Không tìm thấy giá vàng"
        
        price_str = price_span.text.strip().replace(',', '')
        current_price = float(price_str)
        small_tag = soup.find('small')
        update_time = small_tag.text.strip() if small_tag else "Không xác định"
        
        # Rút gọn thời gian cập nhật (chỉ lấy Giờ:Phút:Giây)
        time_match = re.search(r'\d{2}:\d{2}:\d{2}', update_time)
        short_time = time_match.group(0) if time_match else update_time

        text = soup.get_text()
        clean_text = ' '.join(text.split())
        vnd_match = re.search(r'giá là\s*([\d\.]+)\s*VNĐ', clean_text)
        vnd_price = vnd_match.group(1) if vnd_match else "Không xác định"
        
        # Định dạng tin nhắn ngắn gọn, giá nằm ngay dòng đầu
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
    try:
        commands = [
            BotCommand("start", "Xem hướng dẫn sử dụng"),
            BotCommand("manual", "Lấy giá vàng ngay"),
            BotCommand("auto", "Bật tự động gửi mỗi 10 phút"),
            BotCommand("stop", "Dừng gửi tự động"),
            BotCommand("checkprice", "Đặt báo động giá"),
            BotCommand("uncheck", "Hủy báo động giá")
        ]
        bot.set_my_commands(commands)
    except Exception as e:
        print(f"Error setting commands: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    print(f"👤 [{message.chat.id}] dùng /start")
    help_text = (
        "<b>Chào mừng bạn đến với Bot Giá Vàng!</b> 🌟\n\n"
        "📜 <b>DANH SÁCH LỆNH:</b>\n"
        "▶️ /manual : Lấy giá ngay lập tức\n"
        "▶️ /auto : Gửi giá tự động mỗi <b>10 phút</b>\n"
        "▶️ /stop : Dừng gửi tự động\n"
        "▶️ /checkprice [giá] : Báo chuông khi đạt giá\n"
        "▶️ /uncheck : Hủy bỏ báo giá\n\n"
        "💡 <i>Nội dung tin nhắn đã được tối ưu để dễ đọc trên thông báo điện thoại.</i>"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['manual'])
def manual_fetch(message):
    print(f"👤 [{message.chat.id}] dùng /manual")
    _, msg = get_gold_price()
    bot.send_message(message.chat.id, msg, parse_mode="HTML")

# --- Logic Auto Send (10 phút) ---
def auto_worker(chat_id):
    while auto_status.get(chat_id, False):
        _, msg = get_gold_price()
        bot.send_message(chat_id, msg, parse_mode="HTML")
        for _ in range(60): 
            if not auto_status.get(chat_id, False): break
            time.sleep(10)

@bot.message_handler(commands=['auto'])
def start_auto(message):
    print(f"👤 [{message.chat.id}] dùng /auto")
    chat_id = message.chat.id
    if auto_status.get(chat_id, False):
        bot.send_message(chat_id, "⚠️ Đã bật tự động rồi.")
    else:
        auto_status[chat_id] = True
        bot.send_message(chat_id, "✅ Đã bật tự động gửi mỗi 10 phút.")
        threading.Thread(target=auto_worker, args=(chat_id,), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop_auto(message):
    print(f"👤 [{message.chat.id}] dùng /stop")
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
                del price_alerts[chat_id]
                break
        time.sleep(60)

@bot.message_handler(commands=['checkprice'])
def set_price_alert(message):
    print(f"👤 [{message.chat.id}] dùng /checkprice")
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
    print(f"👤 [{message.chat.id}] dùng /uncheck")
    if message.chat.id in price_alerts:
        del price_alerts[message.chat.id]
        bot.send_message(message.chat.id, "🚫 Đã hủy báo giá.")
    else:
        bot.send_message(message.chat.id, "⚠️ Chưa đặt báo giá nào.")

def run_bot():
    set_bot_commands()
    print("🤖 Bot đang chạy...")
    bot.infinity_polling()

# Giao diện Gradio để Hugging Face không tắt Space
def dummy_fn():
    return "Bot is running 24/7!"

if __name__ == "__main__":
    # Chạy Telegram Bot trong một thread riêng
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Chạy giao diện Gradio (Hugging Face yêu cầu một web server)
    with gr.Blocks() as demo:
        gr.Markdown("# 🤖 Telegram Gold Price Bot")
        gr.Markdown("Bot is currently running in the background.")
        status = gr.Textbox(label="Status", value="Online")
        refresh = gr.Button("Check Status")
        refresh.click(fn=dummy_fn, outputs=status)
    
    demo.launch(server_name="0.0.0.0", server_port=7860)
