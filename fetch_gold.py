import os
import requests
from bs4 import BeautifulSoup
import re

# Lấy thông tin từ biến môi trường của GitHub Actions
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_gold_price():
    url = "https://giavang.org/the-gioi/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Lỗi HTTP {response.status_code}: Không thể truy cập trang web."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Tìm thẻ span chứa giá vàng XAU/USD
        price_span = soup.find('span', class_='crypto-price')
        if price_span:
            gold_price = price_span.text.strip()
        else:
            return "Không tìm thấy thẻ giá vàng, vui lòng kiểm tra lại."
            
        # 2. Lấy thời gian cập nhật từ thẻ small
        small_tag = soup.find('small')
        update_time = small_tag.text.strip() if small_tag else "Không xác định"
        
        # 3. Lấy giá VNĐ từ phần text của trang
        text = soup.get_text()
        clean_text = ' '.join(text.split())
        vnd_match = re.search(r'giá là\s*([\d\.]+)\s*VNĐ', clean_text)
        vnd_price = vnd_match.group(1) if vnd_match else "Không xác định"
        
        result_message = (
            f"🌍 GIÁ VÀNG THẾ GIỚI - XAU/USD\n"
            f"• Giá hiện tại: {gold_price} USD/Ounce\n"
            f"• Cập nhật: {update_time}\n"
            f"• Quy đổi (1 cây vàng): {vnd_price} VNĐ"
        )
        return result_message
            
    except Exception as e:
        return f"Lỗi exception: {str(e)}"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Lỗi gửi tin nhắn: {e}")

if __name__ == "__main__":
    msg = get_gold_price()
    send_telegram_message(msg)