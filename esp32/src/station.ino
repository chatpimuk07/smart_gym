#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_PN532.h>
#include <ArduinoJson.h>

// --- ตั้งค่า Wi-Fi ---
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// --- ตั้งค่าปลายทาง Server (Raspberry Pi) ---
const char* server_url = "http://YOUR_SERVER_IP:8000/api/get-routine";
const char* current_station_id = "STATION_CHEST_PRESS";

// กำหนดพิน UART สำหรับ HardwareSerial (Serial2) บน ESP32
#define PN532_RX_PIN 16
#define PN532_TX_PIN 17
#define PN532_RESET_PIN 0  // กำหนดเป็น 0 เมื่อไม่ได้ต่อสาย RST เข้าบอร์ด

// Constructor สำหรับ Hardware UART: (reset_pin, HardwareSerial*)
Adafruit_PN532 nfc(PN532_RESET_PIN, &Serial2);

// ป้องกันการสแกนซ้ำติดกัน (Debounce)
String lastScannedUID = "";
unsigned long lastScanTime = 0;
const unsigned long scanCooldown = 5000; // หน่วงเวลา 5 วินาทีก่อนยอมให้อ่านบัตรเดิมซ้ำ

void sendNfcToServer(String uidStr);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n--- Smart Gym ESP32 NFC (UART Mode) ---");

  // เริ่มต้น Hardware Serial2 สำหรับ PN532 (RX=16, TX=17) ที่ 115200 Baud Rate
  Serial2.begin(115200, SERIAL_8N1, PN532_RX_PIN, PN532_TX_PIN);

  // 1. เชื่อมต่อ Wi-Fi
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected successfully!");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.localIP());

  // 2. เริ่มต้น PN532 โหมด UART
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.println("Error: Didn't find PN532 board. Check UART wiring & DIP switches (Both OFF)!");
    while (1) { delay(1000); }
  }

  Serial.print("Found PN532 chip with firmware version: ");
  Serial.print((versiondata >> 16) & 0xFF, HEX);
  Serial.print('.');
  Serial.println((versiondata >> 8) & 0xFF, HEX);

  // ตั้งค่าให้อ่านการ์ด ISO14443A (Mifare)
  nfc.SAMConfig();
  Serial.println("System Ready. Waiting for NFC tap...");
}

void loop() {
  uint8_t success;
  uint8_t uid[] = { 0, 0, 0, 0, 0, 0, 0 };
  uint8_t uidLength;

  // อ่านการ์ดแบบ Passive (Timeout 100ms เพื่อไม่ให้ loop ค้าง)
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100);

  if (success) {
    // แปลง UID เป็น Hex String ตัวพิมพ์ใหญ่ (เช่น 04A1B2C3)
    String currentUID = "";
    for (uint8_t i = 0; i < uidLength; i++) {
      if (uid[i] < 0x10) currentUID += "0";
      currentUID += String(uid[i], HEX);
    }
    currentUID.toUpperCase();

    unsigned long now = millis();
    if (currentUID != lastScannedUID || (now - lastScanTime > scanCooldown)) {
      lastScannedUID = currentUID;
      lastScanTime = now;

      Serial.println("\n------------------------------------");
      Serial.print("Card Tapped via UART! UID: ");
      Serial.println(currentUID);

      // ยิงข้อมูลขึ้น Raspberry Pi
      sendNfcToServer(currentUID);
    }
  }

  delay(50);
}

void sendNfcToServer(String uidStr) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi Disconnected. Cannot send data.");
    return;
  }

  HTTPClient http;
  http.begin(server_url);
  http.addHeader("Content-Type", "application/json");

  // จัดโครงสร้าง JSON สำหรับ ArduinoJson v7
  JsonDocument doc;
  doc["nfc_uid"] = uidStr;
  doc["station_id"] = current_station_id;

  String requestBody;
  serializeJson(doc, requestBody);

  Serial.println("Sending payload to FastAPI server...");
  int httpResponseCode = http.POST(requestBody);

  if (httpResponseCode > 0) {
    Serial.print("HTTP Response Code: ");
    Serial.println(httpResponseCode);
    String responseBody = http.getString();
    
    if (httpResponseCode == 200) {
      Serial.println("Successfully updated station data!");
      Serial.println("Response payload: " + responseBody);
    } else {
      Serial.println("Server returned error: " + responseBody);
    }
  } else {
    Serial.print("HTTP Request failed: ");
    Serial.println(http.errorToString(httpResponseCode).c_str());
  }

  http.end();
}