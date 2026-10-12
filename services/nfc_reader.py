import time
from typing import Optional, List, Tuple
import serial
import serial.tools.list_ports
from adafruit_pn532.uart import PN532_UART


class USBPN532Reader:
    """Adafruit PN532 UART reader with dynamic port scanning on demand."""

    def __init__(self, baudrate: int = 115200):
        self.baudrate = baudrate
        self.latest_scanned_uid: Optional[str] = None

    def _get_candidate_ports(self) -> List[str]:
        """สแกนค้นหารายชื่อพอร์ตทั้งหมดที่มีอยู่ในระบบ ณ ขณะนั้น (ไม่ล็อคพอร์ตตายตัว)"""
        ports = list(serial.tools.list_ports.comports())
        # นำพอร์ตจำพวก USB/ACM/Serial Converter ขึ้นมาก่อน
        usb_ports = [
            p.device for p in ports 
            if any(k in p.device.lower() for k in ["usb", "acm", "ch34", "cp21", "ftdi"])
        ]
        other_ports = [p.device for p in ports if p.device not in usb_ports]
        candidates = usb_ports + other_ports

        # Fallback พอร์ตทั่วไปหากระบบมองไม่เห็นใน list_ports
        for fallback in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]:
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _read_passive_target_fixed(self, pn_driver: PN532_UART, timeout: float = 0.5) -> Optional[bytes]:
        """
        ฟังก์ชันอ่าน passive target ที่แก้ไขบั๊กของไลบรารี Adafruit:
        - เมื่อไม่มีบัตรทาบอยู่ ชิป PN532 จะตอบ response[0] = 0x00 (0 targets found)
          ซึ่งใน adafruit-circuitpython-pn532 ดั้งเดิมไปเช็ค if response[0] != 0x01 จะ throw RuntimeError("More than one card detected!")
        - ฟังก์ชันนี้จะดัก response[0] == 0x00 เป็น 'ไม่พบบัตร' (Return None) อย่างถูกต้อง
        """
        try:
            # 0x4A = _COMMAND_INLISTPASSIVETARGET (max 1 card, 106 kbps Mifare/ISO14443A)
            if not pn_driver.send_command(0x4A, params=[0x01, 0x00], timeout=timeout):
                return None
            response = pn_driver.process_response(0x4A, response_length=64, timeout=timeout)
            if response is None or len(response) == 0:
                return None
            
            # จำนวน target ที่พบ
            num_targets = response[0]
            if num_targets == 0:
                return None  # ยังไม่มีบัตรมาทาบ
            
            # ตรวจสอบความยาว UID (response[5] = ความยาว UID)
            if len(response) > 5:
                uid_len = response[5]
                if uid_len in (4, 7) and len(response) >= 6 + uid_len:
                    return bytes(response[6 : 6 + uid_len])
            return None
        except Exception:
            return None

    def scan_single_card(self, timeout_sec: float = 6.0) -> Tuple[Optional[str], dict]:
        """
        สแกนหาพอร์ต USB ทั้งหมดในระบบ และรออ่านบัตรตาม timeout ที่กำหนด
        ทำงานแบบ On-Demand ทุกครั้งที่กดปุ่มบน Web Dashboard โดยไม่ต้องล็อคพอร์ต
        คืนค่าเป็น (hex_uid, debug_info_dict)
        """
        candidate_ports = self._get_candidate_ports()
        print("\n" + "=" * 55)
        print("🔍 [NFC SCAN TRIGGERED]")
        print(f"👉 Found available ports in system: {candidate_ports}")

        debug_info = {
            "candidate_ports": candidate_ports,
            "connected_port": None,
            "baudrate": None,
            "error": None
        }

        pn532 = None
        uart = None
        active_port = None

        # 1. สแกนหาพอร์ตที่เชื่อมต่อกับบอร์ด PN532
        for port in candidate_ports:
            print(f"🔌 Testing port: {port}...")
            for baud in [self.baudrate, 9600]:
                try:
                    s = serial.Serial(port, baudrate=baud, timeout=0.25)
                    driver = PN532_UART(s, debug=False)
                    # ตรวจสอบการตอบรับของบอร์ด PN532 ด้วย firmware_version
                    ver = driver.firmware_version
                    driver.SAM_configuration()

                    uart = s
                    pn532 = driver
                    active_port = port
                    debug_info["connected_port"] = active_port
                    debug_info["baudrate"] = baud
                    print(f"🎉 Connected to PN532 on port: {active_port} ({baud} baud) [Firmware: {ver}]")
                    break
                except Exception as e:
                    try:
                        if 's' in locals() and s.is_open:
                            s.close()
                    except Exception:
                        pass
                    continue
            if pn532 is not None:
                break

        if pn532 is None or uart is None:
            err_msg = f"No responsive PN532 found on ports {candidate_ports}"
            print(f"❌ {err_msg}")
            debug_info["error"] = err_msg
            print("=" * 55 + "\n")
            return None, debug_info

        # 2. ลูปวนรออ่านการ์ดจนกว่าจะแตะบัตรหรือครบเวลา Timeout
        deadline = time.time() + timeout_sec
        try:
            print(f"⏳ Waiting for card tap on {active_port} (timeout: {timeout_sec}s)...")
            while time.time() < deadline:
                uid_bytes = self._read_passive_target_fixed(pn532, timeout=0.3)
                if uid_bytes:
                    hex_uid = "".join(f"{b:02X}" for b in uid_bytes)
                    self.latest_scanned_uid = hex_uid
                    print(f"💳 Card detected on {active_port}! UID: {hex_uid}")
                    print("=" * 55 + "\n")
                    return hex_uid, debug_info
                time.sleep(0.08)

            print(f"⏰ Scan timed out on {active_port}. No card tapped.")
            print("=" * 55 + "\n")
            return None, debug_info

        except Exception as e:
            print(f"❌ Error during card scan on {active_port}: {e}")
            debug_info["error"] = str(e)
            print("=" * 55 + "\n")
            return None, debug_info
        finally:
            # ปิดพอร์ตเสมอ ไม่ล็อคพอร์ตค้างไว้
            try:
                if uart and uart.is_open:
                    uart.close()
                    print(f"🔒 Closed and released port {active_port}.")
            except Exception:
                pass

    def get_latest_uid(self) -> Optional[str]:
        return self.latest_scanned_uid

    def clear_latest_uid(self):
        self.latest_scanned_uid = None

    def start(self):
        pass

    def stop(self):
        pass