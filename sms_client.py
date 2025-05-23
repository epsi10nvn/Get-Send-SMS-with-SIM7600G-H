import socket
import json
import time
import os
import base64
from datetime import datetime

# Client giao tiếp qua Socket
class SMSClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
    
    def send_message(self, phone_number, message):
        """Gửi tin nhắn qua socket connection"""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)  # Set timeout để tránh treo
            sock.connect((self.host, self.port))
            
            data = {
                'action': 'send_sms',
                'phone': phone_number,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
            
            # Gửi dữ liệu
            message_data = json.dumps(data, ensure_ascii=False).encode('utf-8') + b'\n'
            sock.send(message_data)
            
            # Nhận phản hồi
            response = sock.recv(1024).decode('utf-8')
            return json.loads(response)
            
        except socket.timeout:
            return {'status': 'error', 'message': 'Connection timeout'}
        except ConnectionRefusedError:
            return {'status': 'error', 'message': 'Server không phản hồi'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if sock:
                sock.close()

# Client giao tiếp qua File
class FileSMSClient:
    def __init__(self, queue_file='/tmp/sms_queue.txt', use_json=False):
        self.queue_file = queue_file
        self.use_json = use_json  # True: dùng JSON, False: dùng Base64 encoding
        # Tạo thư mục nếu chưa tồn tại
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
    
    def send_message(self, phone_number, message):
        """Ghi tin nhắn vào file queue"""
        try:
            # Validate số điện thoại
            if not self._validate_phone(phone_number):
                print(f"Số điện thoại không hợp lệ: {phone_number}")
                return False
            
            # Validate tin nhắn
            if not message or len(message.strip()) == 0:
                print("Tin nhắn không được để trống")
                return False
            
            # Phương pháp 1: Sử dụng JSON (khuyến nghị)
            if hasattr(self, 'use_json') and self.use_json:
                return self._write_json_format(phone_number, message)
            else:
                # Phương pháp 2: Encode Base64 để tránh conflict
                return self._write_encoded_format(phone_number, message)
            
        except PermissionError:
            print(f"Lỗi: Không có quyền ghi file {self.queue_file}")
            return False
        except Exception as e:
            print(f"Lỗi ghi file: {e}")
            return False
    
    def _write_json_format(self, phone_number, message):
        """Ghi dưới dạng JSON - an toàn nhất"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'phone': phone_number,
                'message': message.strip()
            }
            
            json_line = json.dumps(data, ensure_ascii=False) + '\n'
            
            with open(self.queue_file, 'a', encoding='utf-8') as f:
                f.write(json_line)
            
            print(f"✓ Đã thêm tin nhắn vào hàng đợi (JSON): {phone_number}")
            return True
            
        except Exception as e:
            print(f"Lỗi ghi JSON: {e}")
            return False
    
    def _write_encoded_format(self, phone_number, message):
        """Ghi dưới dạng encoded - tương thích với format cũ"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Encode message bằng base64 để tránh conflict với delimiter
            encoded_message = base64.b64encode(message.strip().encode('utf-8')).decode('ascii')
            
            # Format: timestamp|phone|base64_message|END
            line = f"{timestamp}|{phone_number}|{encoded_message}|END\n"
            
            with open(self.queue_file, 'a', encoding='utf-8') as f:
                f.write(line)
            
            print(f"✓ Đã thêm tin nhắn vào hàng đợi (Encoded): {phone_number}")
            return True
            
        except Exception as e:
            print(f"Lỗi ghi encoded: {e}")
            return False
    
    def _validate_phone(self, phone_number):
        """Kiểm tra tính hợp lệ của số điện thoại"""
        if not phone_number:
            return False
        
        # Loại bỏ khoảng trắng và ký tự đặc biệt
        clean_phone = phone_number.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Kiểm tra định dạng cơ bản
        if clean_phone.startswith('+84'):
            return len(clean_phone) >= 12 and clean_phone[3:].isdigit()
        elif clean_phone.startswith('84'):
            return len(clean_phone) >= 11 and clean_phone[2:].isdigit()
        elif clean_phone.startswith('0'):
            return len(clean_phone) >= 10 and clean_phone[1:].isdigit()
        
        return False
    
    def read_queue_messages(self):
        """Đọc và parse các tin nhắn từ queue file"""
        try:
            if not os.path.exists(self.queue_file):
                return []
            
            messages = []
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        if self.use_json:
                            # Parse JSON format
                            data = json.loads(line)
                            messages.append(data)
                        else:
                            # Parse encoded format
                            parts = line.split('|')
                            if len(parts) >= 4 and parts[-1] == 'END':
                                timestamp = parts[0]
                                phone = parts[1]
                                encoded_msg = parts[2]
                                
                                # Decode base64 message
                                decoded_msg = base64.b64decode(encoded_msg.encode('ascii')).decode('utf-8')
                                
                                messages.append({
                                    'timestamp': timestamp,
                                    'phone': phone,
                                    'message': decoded_msg
                                })
                            else:
                                print(f"Dòng {line_num}: Format không hợp lệ")
                                
                    except (json.JSONDecodeError, base64.binascii.Error) as e:
                        print(f"Dòng {line_num}: Lỗi parse - {e}")
                        continue
            
            return messages
            
        except Exception as e:
            print(f"Lỗi đọc queue: {e}")
            return []
    
    def get_queue_status(self):
        """Lấy thông tin trạng thái hàng đợi"""
        try:
            if not os.path.exists(self.queue_file):
                return {'count': 0, 'size': 0, 'format': 'N/A'}
            
            messages = self.read_queue_messages()
            file_size = os.path.getsize(self.queue_file)
            
            return {
                'count': len(messages), 
                'size': file_size,
                'format': 'JSON' if self.use_json else 'Base64'
            }
            
        except Exception as e:
            print(f"Lỗi đọc file queue: {e}")
            return {'count': -1, 'size': -1, 'format': 'Error'}

# Hàm utility để test
def test_clients():
    """Test cả hai loại client"""
    print("=== TEST SMS CLIENTS ===\n")
    
    # Test message có ký tự đặc biệt
    problematic_message = """Chào bạn!
Đây là tin nhắn có:
- Dấu | (pipe) 
- Xuống dòng \n
- Ký tự đặc biệt: @#$%^&*()
Kết thúc tin nhắn."""
    
    print("1. Test FileSMSClient với JSON format:")
    json_client = FileSMSClient(queue_file='/tmp/sms_queue_json.txt', use_json=True)
    result = json_client.send_message("+84357259001", problematic_message)
    if result:
        status = json_client.get_queue_status()
        print(f"   Queue status: {status['count']} tin nhắn, {status['size']} bytes, Format: {status['format']}")
        
        # Đọc lại để kiểm tra
        messages = json_client.read_queue_messages()
        if messages:
            print(f"   ✓ Đọc lại thành công: {len(messages[0]['message'])} ký tự")
    
    print("\n2. Test FileSMSClient với Base64 format:")
    b64_client = FileSMSClient(queue_file='/tmp/sms_queue_b64.txt', use_json=False)
    result = b64_client.send_message("+84357259001", problematic_message)
    if result:
        status = b64_client.get_queue_status()
        print(f"   Queue status: {status['count']} tin nhắn, {status['size']} bytes, Format: {status['format']}")
        
        # Đọc lại để kiểm tra
        messages = b64_client.read_queue_messages()
        if messages:
            print(f"   ✓ Đọc lại thành công: {len(messages[0]['message'])} ký tự")
    
    print("\n3. So sánh nội dung:")
    if len(json_client.read_queue_messages()) > 0 and len(b64_client.read_queue_messages()) > 0:
        json_msg = json_client.read_queue_messages()[0]['message']
        b64_msg = b64_client.read_queue_messages()[0]['message']
        print(f"   Nội dung giống nhau: {json_msg == b64_msg == problematic_message}")
    
    # Test SMSClient
    print("\n4. Test SMSClient:")
    socket_client = SMSClient()
    result = socket_client.send_message("+84357259001", problematic_message)
    print(f"   Socket result: {result}")

# Main execution
if __name__ == '__main__':
    try:
        # Thử import MESSAGE từ MESSAGE_INFO
        from MESSAGE_INFO import MESSAGE
        
        print("Tìm thấy MESSAGE_INFO.py")
        
        # Sử dụng JSON format (khuyến nghị) hoặc Base64 format
        client = FileSMSClient(use_json=True)  # Thay đổi thành False nếu muốn dùng Base64
        result = client.send_message("+84357259001", MESSAGE)
        
        if result:
            print("✓ Tin nhắn đã được thêm vào hàng đợi thành công!")
            print(f"Nội dung: {MESSAGE[:100]}{'...' if len(MESSAGE) > 100 else ''}")
            
            # Hiển thị trạng thái queue
            status = client.get_queue_status()
            print(f"Trạng thái hàng đợi: {status['count']} tin nhắn")
        else:
            print("✗ Lỗi khi thêm tin nhắn vào hàng đợi!")
            
    except ImportError:
        print("Không tìm thấy MESSAGE_INFO.py - Chạy test mode")
        test_clients()
    except Exception as e:
        print(f"Lỗi không mong muốn: {e}")
        test_clients()