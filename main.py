import os
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import GymDatabase, GymAIService, USBPN532Reader

# โหลดตัวแปรสภาพแวดล้อมจากไฟล์ .env
load_dotenv()

# สร้าง Instance ของตัวอ่าน NFC ผ่านพอร์ต USB
nfc_scanner = USBPN532Reader()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # เริ่ม Background Worker สแกนหาพอร์ต USB และอ่านบัตรอัตโนมัติ
    nfc_scanner.start()
    yield
    # หยุดการทำงานเมื่อเซิร์ฟเวอร์ปิดตัว
    nfc_scanner.stop()


app = FastAPI(title="Smart Gym Hub & Admin Dashboard", lifespan=lifespan)

# ติดตั้ง Static Files Directory สำหรับ CSS และ JS
static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

db = GymDatabase()
ai = GymAIService()


# ---------------- DATA MODELS ----------------
class RoutineRequest(BaseModel):
    nfc_uid: str
    station_id: str


class UserPayload(BaseModel):
    nfc_uid: str
    name: str
    fitness_level: str
    target_goal: str
    injury_note: Optional[str] = None
    gender: Optional[str] = None


from fastapi.concurrency import run_in_threadpool

# ---------------- API สำหรับ ADMIN LIVE SCAN ----------------
@app.post("/api/trigger-scan")
async def trigger_nfc_scan():
    """จะเริ่มสแกนหาพอร์ตและรอแตะบัตรเฉพาะตอนที่หน้าเว็บส่งคำขอมาเท่านั้น (รอสูงสุด 6 วินาที)"""
    uid, debug_info = await run_in_threadpool(nfc_scanner.scan_single_card, timeout_sec=6.0)
    if uid:
        return {"status": "success", "nfc_uid": uid, "debug": debug_info}
    return {"status": "timeout", "nfc_uid": None, "debug": debug_info}



@app.get("/api/latest-nfc")
def get_latest_nfc():
    """ดึง UID ล่าสุดที่อ่านได้จาก USB PN532 ไปใส่ในฟอร์มของ Admin Dashboard"""
    return {"nfc_uid": nfc_scanner.get_latest_uid()}


@app.post("/api/clear-latest-nfc")
def clear_latest_nfc():
    """เคลียร์ค่า UID ที่ค้างอยู่บนเซิร์ฟเวอร์"""
    nfc_scanner.clear_latest_uid()
    return {"status": "cleared"}



# ---------------- ESP32 ENDPOINT ----------------
@app.post("/api/get-routine")
def get_routine(req: RoutineRequest):
    """รับคำขอจาก ESP32 ประจำ Station เพื่อสร้างหรือดึงแผนการฝึกจาก Gemini"""
    user = db.get_user_by_nfc(req.nfc_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    station = db.get_station(req.station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    # อัปเดตสถานะของเครื่องเล่นเป็น in_use
    db.update_station_status(req.station_id, "in_use", user["user_id"])

    # ตรวจสอบ Cache ในวันปัจจุบันก่อน
    cached_json = db.get_cached_routine(user["user_id"], req.station_id)
    if cached_json:
        return Response(content=cached_json, media_type="application/json")

    # ดึงประวัติการเล่นครั้งล่าสุด และส่งให้ Gemini สร้างตารางฝึกใหม่
    last_history = db.get_last_workout(user["user_id"], req.station_id)
    ai_json = ai.generate_routine(
        dict(user),
        dict(station),
        dict(last_history) if last_history else None
    )

    # แคชผลลัพธ์ไว้ใช้ซ้ำในวันเดียวกัน
    db.save_cached_routine(user["user_id"], req.station_id, ai_json)
    return Response(content=ai_json, media_type="application/json")


# ---------------- ADMIN CRUD ENDPOINTS ----------------
@app.get("/api/users")
def list_users():
    """ดึงรายชื่อสมาชิกทั้งหมด"""
    return db.get_all_users()


@app.post("/api/users")
def create_user(payload: UserPayload):
    """เพิ่มสมาชิกใหม่ลงฐานข้อมูล"""
    user_id = db.add_user(
        nfc_uid=payload.nfc_uid,
        name=payload.name,
        fitness_level=payload.fitness_level,
        target_goal=payload.target_goal,
        injury_note=payload.injury_note,
        gender=payload.gender
    )
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="Failed to add user (NFC UID might already exist)"
        )
    return {"status": "success", "user_id": user_id}


@app.put("/api/users/{user_id}")
def update_user_info(user_id: int, payload: UserPayload):
    """แก้ไขข้อมูลสมาชิกที่มีอยู่"""
    success = db.update_user(
        user_id=user_id,
        nfc_uid=payload.nfc_uid,
        name=payload.name,
        fitness_level=payload.fitness_level,
        target_goal=payload.target_goal,
        injury_note=payload.injury_note,
        gender=payload.gender
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update user")
    return {"status": "success"}


@app.delete("/api/users/{user_id}")
def delete_user_record(user_id: int):
    """ลบสมาชิกออกจากระบบ"""
    success = db.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete user")
    return {"status": "success"}


# ---------------- STATION STATUS ENDPOINTS ----------------
@app.get("/api/stations")
def list_stations():
    """ดึงข้อมูล Station ทั้งหมดพร้อมสถานะความว่าง (idle / in_use) และผู้ใช้งานปัจจุบัน"""
    return db.get_all_stations()


@app.post("/api/stations/{station_id}/reset")
def reset_station(station_id: str):
    """รีเซ็ตสถานะ Station ให้กลับมาว่าง (idle)"""
    success = db.reset_station_status(station_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to reset station status")
    return {"status": "success", "station_id": station_id}


# ---------------- WEB DASHBOARD PAGES ----------------
@app.get("/")
def root():
    """หน้าแรกให้ redirect ไปที่หน้าสถานะ Station"""
    return RedirectResponse(url="/stations")


@app.get("/admin", response_class=HTMLResponse)
def serve_admin_dashboard():
    """แสดงผลหน้า Admin Dashboard (HTML)"""
    html_path = os.path.join(os.path.dirname(__file__), "templates", "admin.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Dashboard template not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/stations", response_class=HTMLResponse)
def serve_stations_page():
    """แสดงผลหน้าตรวจสอบสถานะเครื่องเล่น (Station Live Status)"""
    html_path = os.path.join(os.path.dirname(__file__), "templates", "stations.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Station status template not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)