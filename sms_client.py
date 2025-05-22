import socket
import json
import time

# Nếu bạn muốn gửi tin nhắn từ script khác, hãy sử dụng socket để giao tiếp
class SMSClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
    
    def send_message(self, phone_number, message):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.host, self.port))
            
            data = {
                'action': 'send_sms',
                'phone': phone_number,
                'message': message
            }
            
            sock.send(json.dumps(data).encode() + b'\n')
            response = sock.recv(1024).decode()
            sock.close()
            
            return json.loads(response)
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

# Hoặc sử dụng file để giao tiếp
class FileSMSClient:
    def __init__(self, queue_file='/tmp/sms_queue.txt'):
        self.queue_file = queue_file
    
    def send_message(self, phone_number, message):
        try:
            with open(self.queue_file, 'a', encoding='utf-8') as f:
                f.write(f"{phone_number}|{message}\n")
            print(f"Đã thêm tin nhắn vào hàng đợi: {phone_number}")
            return True
        except Exception as e:
            print(f"Lỗi ghi file: {e}")
            return False

# Sử dụng với MESSAGE_INFO
if __name__ == '__main__':
    try:
        from MESSAGE_INFO import MESSAGE
        
        client = FileSMSClient()
        result = client.send_message("+84977426274", MESSAGE)
        
        if result:
            print("Tin nhắn đã được thêm vào hàng đợi thành công!")
            print(f"Nội dung: {MESSAGE}")
        else:
            print("Lỗi khi thêm tin nhắn vào hàng đợi!")
            
    except ImportError:
        print("Không tìm thấy MESSAGE_INFO.py")
        
        # Test với tin nhắn mẫu
        client = FileSMSClient()
        test_message = "Đây là tin nhắn test từ SMS Client"
        client.send_message("+84977426274", test_message)