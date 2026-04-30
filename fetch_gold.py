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