import serial
import time
import re
import random
import threading
import os
from smspdudecoder.fields import SMSDeliver
from io import StringIO
from collections import defaultdict
from datetime import timezone, timedelta
from queue import Queue

class SMSHandlerWithFileQueue:
    def __init__(self, port='/dev/ttyUSB2', baudrate=115200, timeout=3, queue_file='/tmp/sms_queue.txt'):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.queue_file = queue_file
        self.ser = None
        self.is_listening = False
        self.multipart_messages = defaultdict(lambda: defaultdict(dict))
        self.message_buffer = defaultdict(list)
        
    def connect(self):
        """Kết nối tới modem"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self.ser.write(b'AT+CMGF=0\r')
            time.sleep(1)
            self.ser.write(b'AT+CNMI=2,2,0,0,0\r')
            time.sleep(1)
            print(f"Đã kết nối tới modem trên {self.port}")
            return True
        except Exception as e:
            print(f"Lỗi kết nối modem: {e}")
            return False
    
    def disconnect(self):
        """Ngắt kết nối modem"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Đã ngắt kết nối modem")
    
    def _send_pdu_sms(self, phone_number, message):
        """Gửi SMS bằng PDU mode"""
        try:
            print(f"Đang gửi tin nhắn tới {phone_number}: {message[:50]}...")
            
            # Chuẩn hóa số điện thoại
            phone_number = phone_number.lstrip("+").replace(" ", "")
            if len(phone_number) % 2 != 0:
                phone_number += 'F'
            swapped_number = ''.join([phone_number[i+1] + phone_number[i] for i in range(0, len(phone_number), 2)])
            
            max_single_length = 70
            if len(message) <= max_single_length:
                # Tin nhắn đơn
                ucs2_msg = message.encode('utf-16-be').hex().upper()
                pdu_length = len(ucs2_msg) // 2
                
                pdu = "001100"
                pdu += f"0C91{swapped_number}0008AA{pdu_length:02X}{ucs2_msg}"
                
                self.ser.write(b'AT+CMGF=0\r')
                time.sleep(0.5)
                pdu_length_for_cmgs = (len(pdu) // 2) - 1
                cmd = f'AT+CMGS={pdu_length_for_cmgs}\r'
                self.ser.write(cmd.encode())
                time.sleep(0.5)
                self.ser.write((pdu + "\x1a").encode())
                time.sleep(2)
                
                print(f"✓ Đã gửi tin nhắn đơn thành công")
            else:
                # Tin nhắn multipart
                max_part_length = 67
                total_parts = (len(message) + max_part_length - 1) // max_part_length
                ref_number = random.randint(0, 255)
                
                print(f"Gửi tin nhắn dài ({len(message)} ký tự) thành {total_parts} phần:")
                
                for part_num in range(1, total_parts + 1):
                    start = (part_num - 1) * max_part_length
                    end = start + max_part_length
                    part = message[start:end]
                    
                    udh = [0x05, 0x00, 0x03, ref_number, total_parts, part_num]
                    udh_hex = ''.join(f"{x:02X}" for x in udh)
                    
                    ucs2_part = part.encode('utf-16-be').hex().upper()
                    user_data = udh_hex + ucs2_part
                    user_data_length = len(user_data) // 2
                    
                    pdu = "005100"
                    pdu += f"0C91{swapped_number}0008AA{user_data_length:02X}{user_data}"
                    
                    self.ser.write(b'AT+CMGF=0\r')
                    time.sleep(0.5)
                    pdu_length_for_cmgs = (len(pdu) // 2) - 1
                    cmd = f'AT+CMGS={pdu_length_for_cmgs}\r'
                    self.ser.write(cmd.encode())
                    time.sleep(0.5)
                    self.ser.write((pdu + "\x1a").encode())
                    time.sleep(3)
                    
                    print(f"  ✓ Đã gửi phần {part_num}/{total_parts}")
                
                print(f"✓ Hoàn thành gửi tin nhắn multipart")
            
            # Khôi phục chế độ nhận tin nhắn
            self.ser.write(b'AT+CNMI=2,2,0,0,0\r')
            time.sleep(0.5)
            
            return True
            
        except Exception as e:
            print(f"✗ Lỗi gửi SMS: {e}")
            return False
    
    def _process_file_queue(self):
        """Xử lý hàng đợi tin nhắn từ file"""
        while self.is_listening:
            try:
                if os.path.exists(self.queue_file):
                    with open(self.queue_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if lines:
                        # Xử lý tin nhắn đầu tiên
                        line = lines[0].strip()
                        if '|' in line:
                            phone_number, message = line.split('|', 1)
                            print(f"Đang xử lý tin nhắn từ file queue...")
                            
                            if self._send_pdu_sms(phone_number, message):
                                # Xóa tin nhắn đã gửi thành công
                                remaining_lines = lines[1:]
                                with open(self.queue_file, 'w', encoding='utf-8') as f:
                                    f.writelines(remaining_lines)
                                print(f"Đã xóa tin nhắn khỏi queue")
                            else:
                                print(f"Gửi tin nhắn thất bại, giữ lại trong queue")
                                time.sleep(10)  # Chờ 10 giây trước khi thử lại
                        else:
                            # Dòng không hợp lệ, xóa nó
                            remaining_lines = lines[1:]
                            with open(self.queue_file, 'w', encoding='utf-8') as f:
                                f.writelines(remaining_lines)
                    else:
                        time.sleep(1)  # Không có tin nhắn, chờ 1 giây
                else:
                    time.sleep(1)  # File không tồn tại, chờ 1 giây
            except Exception as e:
                print(f"Lỗi xử lý file queue: {e}")
                time.sleep(5)
    
    def parse_pdu_raw(self, pdu_hex):
        """Phân tích PDU thô để tìm thông tin multipart"""
        try:
            pdu_bytes = bytes.fromhex(pdu_hex)
            smsc_len = pdu_bytes[0]
            offset = 1 + smsc_len
            
            pdu_type = pdu_bytes[offset]
            offset += 1
            
            sender_len = pdu_bytes[offset]
            offset += 1
            sender_type = pdu_bytes[offset]
            offset += 1
            
            sender_digits = (sender_len + 1) // 2
            offset += sender_digits
            offset += 1  # PID
            offset += 1  # DCS
            offset += 7  # Timestamp
            
            udl = pdu_bytes[offset]
            offset += 1
            
            udhi = (pdu_type & 0x40) != 0
            
            if udhi and offset < len(pdu_bytes):
                udhl = pdu_bytes[offset]
                offset += 1
                
                udh_end = offset + udhl
                while offset < udh_end:
                    iei = pdu_bytes[offset]
                    offset += 1
                    iedl = pdu_bytes[offset]
                    offset += 1
                    
                    if iei == 0x00 and iedl == 3:
                        ref_num = pdu_bytes[offset]
                        total_parts = pdu_bytes[offset + 1]
                        seq_num = pdu_bytes[offset + 2]
                        return (ref_num, total_parts, seq_num)
                    
                    offset += iedl
            
            return None
        except Exception as e:
            print(f"Lỗi phân tích PDU thô: {e}")
            return None
    
    def listen_sms(self):
        """Lắng nghe tin nhắn SMS"""
        print("Đang lắng nghe tin nhắn mới từ modem...")
        print(f"File queue: {self.queue_file}")
        self.is_listening = True
        
        # Khởi động thread xử lý file queue
        queue_thread = threading.Thread(target=self._process_file_queue, daemon=True)
        queue_thread.start()
        
        while self.is_listening:
            try:
                line = self.ser.readline()
                if line:
                    text = line.decode(errors='ignore').strip()
                    if text.startswith('+CMT:'):
                        pdu_line = self.ser.readline().decode(errors='ignore').strip()
                        if re.fullmatch(r'[0-9A-Fa-f]+', pdu_line):
                            try:
                                sms = SMSDeliver.decode(StringIO(pdu_line))
                                sender = sms['sender']['number']
                                scts = sms['scts'].astimezone(timezone(timedelta(hours=7)))
                                content = sms['user_data']['data']
                                
                                # Kiểm tra multipart
                                multipart_info = self.parse_pdu_raw(pdu_line)
                                
                                if multipart_info:
                                    ref_num, total_parts, seq_num = multipart_info
                                    print(f"📱 Nhận phần {seq_num}/{total_parts} (ref: {ref_num}) từ {sender}")
                                    
                                    self.multipart_messages[sender][ref_num][seq_num] = content
                                    
                                    if 'timestamp' not in self.multipart_messages[sender][ref_num]:
                                        self.multipart_messages[sender][ref_num]['timestamp'] = scts
                                    else:
                                        if scts < self.multipart_messages[sender][ref_num]['timestamp']:
                                            self.multipart_messages[sender][ref_num]['timestamp'] = scts
                                    
                                    received_parts = [k for k in self.multipart_messages[sender][ref_num] if isinstance(k, int)]
                                    
                                    if len(received_parts) == total_parts:
                                        full_message = ''
                                        for i in range(1, total_parts + 1):
                                            if i in self.multipart_messages[sender][ref_num]:
                                                full_message += self.multipart_messages[sender][ref_num][i]
                                        
                                        timestamp = self.multipart_messages[sender][ref_num]['timestamp']
                                        
                                        print(f"\n{'='*60}")
                                        print(f"📨 TIN NHẮN HOÀN CHỈNH")
                                        print(f"Số người gửi: {sender}")
                                        print(f"Thời gian: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                                        print(f"Nội dung: {full_message}")
                                        print(f"{'='*60}\n")
                                        
                                        del self.multipart_messages[sender][ref_num]
                                else:
                                    # Sử dụng phương pháp ghép theo thời gian
                                    self.message_buffer[sender].append({
                                        'time': scts,
                                        'content': content,
                                        'timestamp': time.time()
                                    })
                                    
                                    current_time = time.time()
                                    recent_messages = [msg for msg in self.message_buffer[sender] 
                                                     if current_time - msg['timestamp'] <= 3]
                                    
                                    if len(recent_messages) >= 2:
                                        recent_messages.sort(key=lambda x: x['time'])
                                        full_content = ''.join([msg['content'] for msg in recent_messages])
                                        earliest_time = recent_messages[0]['time']
                                        
                                        print(f"\n{'='*60}")
                                        print(f"📨 TIN NHẮN ĐƯỢC GHÉP")
                                        print(f"Số người gửi: {sender}")
                                        print(f"Thời gian: {earliest_time.strftime('%Y-%m-%d %H:%M:%S')}")
                                        print(f"Nội dung: {full_content}")
                                        print(f"{'='*60}\n")
                                        
                                        self.message_buffer[sender] = []
                                    elif len(recent_messages) == 1 and current_time - recent_messages[0]['timestamp'] > 2:
                                        # Tin nhắn đơn sau 2 giây chờ
                                        msg = recent_messages[0]
                                        print(f"\n📱 Tin nhắn đơn:")
                                        print(f"Số người gửi: {sender}")
                                        print(f"Thời gian: {msg['time'].strftime('%Y-%m-%d %H:%M:%S')}")
                                        print(f"Nội dung: {msg['content']}\n")
                                        self.message_buffer[sender] = []
                                    
                                    # Dọn dẹp tin nhắn cũ
                                    self.message_buffer[sender] = [msg for msg in self.message_buffer[sender] 
                                                                 if current_time - msg['timestamp'] <= 10]
                                        
                            except Exception as e:
                                print(f"Lỗi phân tích PDU: {e}")
            except Exception as e:
                if self.is_listening:
                    print(f"Lỗi đọc serial: {e}")
                break
            time.sleep(0.05)
    
    def stop_listening(self):
        """Dừng lắng nghe"""
        self.is_listening = False
        print("Đã dừng lắng nghe tin nhắn")
    
    def add_to_queue(self, phone_number, message):
        """Thêm tin nhắn vào file queue"""
        try:
            with open(self.queue_file, 'a', encoding='utf-8') as f:
                f.write(f"{phone_number}|{message}\n")
            print(f"✓ Đã thêm tin nhắn vào queue: {phone_number}")
            return True
        except Exception as e:
            print(f"✗ Lỗi thêm tin nhắn vào queue: {e}")
            return False
    
    def get_queue_status(self):
        """Kiểm tra trạng thái hàng đợi"""
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                return len(lines)
            return 0
        except Exception as e:
            print(f"Lỗi kiểm tra queue: {e}")
            return -1

# Tạo service daemon
def run_sms_service():
    """Chạy SMS service như một daemon"""
    sms_handler = SMSHandlerWithFileQueue('/dev/ttyUSB2')
    
    if sms_handler.connect():
        try:
            print("🚀 SMS Service đã khởi động!")
            print("📁 Sử dụng file queue:", sms_handler.queue_file)
            print("📱 Đang lắng nghe tin nhắn và xử lý queue...")
            print("⏹️  Nhấn Ctrl+C để dừng service")
            
            sms_handler.listen_sms()
            
        except KeyboardInterrupt:
            print("\n⏹️  Đang dừng SMS Service...")
            sms_handler.stop_listening()
        finally:
            sms_handler.disconnect()
            print("✅ SMS Service đã dừng")
    else:
        print("❌ Không thể kết nối tới modem!")

# Sử dụng
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'service':
            # Chạy như service
            run_sms_service()
        elif sys.argv[1] == 'send':
            # Gửi tin nhắn từ command line
            if len(sys.argv) >= 4:
                phone = sys.argv[2]
                message = ' '.join(sys.argv[3:])
                
                handler = SMSHandlerWithFileQueue()
                if handler.add_to_queue(phone, message):
                    print(f"✅ Tin nhắn đã được thêm vào queue")
                else:
                    print(f"❌ Lỗi thêm tin nhắn vào queue")
            else:
                print("Sử dụng: python sms_handler.py send <số_điện_thoại> <tin_nhắn>")
        elif sys.argv[1] == 'status':
            # Kiểm tra trạng thái queue
            handler = SMSHandlerWithFileQueue()
            count = handler.get_queue_status()
            if count >= 0:
                print(f"📊 Số tin nhắn trong queue: {count}")
            else:
                print("❌ Lỗi kiểm tra queue")
        else:
            print("Tham số không hợp lệ!")
            print("Sử dụng:")
            print("  python sms_handler.py service        # Chạy service")
            print("  python sms_handler.py send <sdt> <msg>  # Gửi tin nhắn")
            print("  python sms_handler.py status         # Kiểm tra queue")
    else:
        # Chạy interactive mode
        print("🎛️  SMS Handler Interactive Mode")
        print("Nhập 'help' để xem danh sách lệnh")
        
        handler = SMSHandlerWithFileQueue('/dev/ttyUSB2')
        
        if handler.connect():
            try:
                # Khởi động listener trong thread riêng
                listen_thread = threading.Thread(target=handler.listen_sms, daemon=True)
                listen_thread.start()
                
                while True:
                    cmd = input("sms> ").strip().lower()
                    if cmd == 'quit' or cmd == 'exit':
                        break
                    elif cmd == 'help':
                        print("📋 Danh sách lệnh:")
                        print("  send         - Gửi tin nhắn")
                        print("  status       - Kiểm tra queue")
                        print("  help         - Hiển thị trợ giúp")
                        print("  quit/exit    - Thoát chương trình")
                    elif cmd == 'send':
                        phone = input("📞 Nhập số điện thoại: ").strip()
                        message = input("💬 Nhập nội dung tin nhắn: ").strip()
                        handler.add_to_queue(phone, message)
                    elif cmd == 'status':
                        count = handler.get_queue_status()
                        if count >= 0:
                            print(f"📊 Số tin nhắn trong queue: {count}")
                        else:
                            print("❌ Lỗi kiểm tra queue")
                    elif cmd.strip() == '':
                        continue
                    else:
                        print(f"❓ Lệnh không xác định: {cmd}")
                
                handler.stop_listening()
                
            except KeyboardInterrupt:
                print("\n⏹️  Đang dừng...")
                handler.stop_listening()
            finally:
                handler.disconnect()
        else:
            print("❌ Không thể kết nối tới modem!")