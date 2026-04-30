import os
import requests
from bs4 import BeautifulSoup

# Lấy thông tin từ biến môi trường của GitHub Actions
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def get_gold_price():
    # URL của trang web cần lấy dữ liệu
    url = "https://giavang.org/the-gioi/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        # Gửi yêu cầu tải trang web về
        response = requests.get(url, headers=headers)
        
        # Dùng BeautifulSoup để phân tích mã HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ở đây chúng ta sẽ tìm phần tử chứa giá vàng thế giới.
        # Ví dụ: ta tìm thẻ chứa thông tin, giả sử ta tìm class "gia-vang-class" (Anh có thể inspect trang web để thay đổi class cho phù hợp)
        price_element = soup.find('div', class_='gia-vang-class') # Sẽ cần điều chỉnh tùy theo cấu trúc HTML thực tế
        
        if price_element:
            return f"Giá vàng thế giới hôm nay:\n{price_element.text.strip()}"
        else:
            return "Không tìm thấy dữ liệu giá vàng trên trang, vui lòng kiểm tra lại cấu trúc HTML."
            
    except Exception as e:import os
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
        response = requests.get(url, headers=headers)
        # Phân tích cú pháp HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Lấy toàn bộ text của trang
        page_text = soup.get_text(separator='\n')
        
        # Dùng Regex để tìm giá vàng XAU/USD (VD: 4,547.63 USD)
        pattern = r'(\d{1,3}(?:,\d{3})*\.\d{2})\s*USD'
        matches = re.findall(pattern, page_text)
        
        if matches:
            gold_price = matches[0]
            
            # Tìm thời gian cập nhật trên trang
            time_match = re.search(r'Cập nhật lúc\s*(\d{2}:\d{2}:\d{2}\s*\d{2}/\d{2}/\d{4})', page_text)
            update_time = time_match.group(1) if time_match else "Mới nhất"
            
            # Tìm giá quy đổi sang VNĐ
            vnd_match = re.search(r'giá là\s*([\d\.]+)\s*VNĐ', page_text)
            vnd_price = vnd_match.group(1) if vnd_match else "Không xác định"
            
            result_message = (
                f"🌍 GIÁ VÀNG THẾ GIỚI - XAU/USD\n"
                f"• Giá hiện tại: {gold_price} USD/Ounce\n"
                f"• Cập nhật: {update_time}\n"
                f"• Quy đổi (1 cây vàng): {vnd_price} VNĐ"
            )
            return result_message
        else:
            return "Không tìm thấy dữ liệu giá vàng trên trang. Vui lòng kiểm tra lại."
            
    except Exception as e:
        return f"Đã xảy ra lỗi khi lấy dữ liệu: {e}"

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
        return f"Đã xảy ra lỗi khi lấy dữ liệu: {e}"

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