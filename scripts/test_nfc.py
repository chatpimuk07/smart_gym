import os
import sys

# เพิ่ม root directory ลงใน sys.path เพื่อให้สามารถเรียกใช้ services ได้
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import USBPN532Reader

print("=" * 60)
print("🚀 ทดสอบอ่านบัตร NFC (Adafruit PN532 + Dynamic Port Scanning)")
print("=" * 60)

reader = USBPN532Reader()
print("\n👉 กรุณานำบัตร NFC หรือเหรียญ Mifare มาแตะที่ตัวอ่านภายใน 8 วินาที...")
uid, debug_info = reader.scan_single_card(timeout_sec=8.0)

if uid:
    print(f"\n🎉 สำเร็จ! อ่านค่าบัตรได้ UID: {uid}")
else:
    print("\n⏰ หมดเวลา (Timeout) หรือไม่พบบัตร")
    if debug_info.get("error"):
        print(f"⚠️ รายละเอียดข้อผิดพลาด: {debug_info['error']}")
