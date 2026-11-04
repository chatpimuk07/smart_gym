import os
import json
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
    nfc_uid: Optional[str] = None
    name: str
    fitness_level: str
    target_goal: str
    injury_note: Optional[str] = None
    gender: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class RegisterPayload(BaseModel):
    name: str
    username: str
    password: str
    fitness_level: str
    target_goal: str
    injury_note: Optional[str] = None
    gender: Optional[str] = None


class LoginPayload(BaseModel):
    username: str
    password: str


class ChangePasswordPayload(BaseModel):
    user_id: int
    old_password: str
    new_password: str


class LogWorkoutPayload(BaseModel):
    user_id: int
    station_id: str
    exercise_name: str
    weight_kg: float
    sets: int
    reps: int


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

    # 1. ตรวจสอบว่าผู้ใช้คนเดิมแตะบัตรซ้ำที่เครื่องที่กำลังเล่นอยู่หรือไม่ (Tap to Finish / Check-out)
    if station.get("status") == "in_use" and station.get("current_user_id") == user["user_id"]:
        db.reset_station_status(req.station_id)
        finish_response = {
            "status": "session_completed",
            "message": f"คุณ {user.get('name', 'Member')} เล่นเครื่อง {station.get('station_name', '')} เสร็จสิ้นแล้ว สถานะเครื่องเปลี่ยนเป็นว่างเรียบร้อย",
            "station_id": req.station_id,
            "user": user.get("name", "Member"),
            "exercise": station.get("station_name", "Machine Workout"),
            "target": "Session Finished",
            "weight": "Done",
            "tip": "ทำได้ดีมากครับ! กรุณาเช็ดทำความสะอาดเครื่องเล่นสำหรับสมาชิกท่านถัดไป"
        }
        return Response(content=json.dumps(finish_response, ensure_ascii=False), media_type="application/json")

    # 2. ผู้ใช้แตะบัตรเพื่อเริ่มเล่น (Start Workout / Check-in)
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
    """เพิ่มสมาชิกใหม่ลงฐานข้อมูล (Admin)"""
    user_id = db.add_user(
        nfc_uid=payload.nfc_uid,
        name=payload.name,
        fitness_level=payload.fitness_level,
        target_goal=payload.target_goal,
        injury_note=payload.injury_note,
        gender=payload.gender,
        username=payload.username,
        password=payload.password
    )
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="Failed to add user (NFC UID or Username might already exist)"
        )
    return {"status": "success", "user_id": user_id}


@app.put("/api/users/{user_id}")
def update_user_info(user_id: int, payload: UserPayload):
    """แก้ไขข้อมูลสมาชิกที่มีอยู่ (Admin)"""
    success = db.update_user(
        user_id=user_id,
        nfc_uid=payload.nfc_uid,
        name=payload.name,
        fitness_level=payload.fitness_level,
        target_goal=payload.target_goal,
        injury_note=payload.injury_note,
        gender=payload.gender,
        username=payload.username,
        password=payload.password
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


@app.get("/user", response_class=HTMLResponse)
def serve_user_portal():
    """แสดงผลหน้า Member Portal สำหรับผู้ใช้งานทั่วไป (HTML)"""
    html_path = os.path.join(os.path.dirname(__file__), "templates", "user.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="User portal template not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------- MEMBER AUTH & DASHBOARD API ----------------
@app.post("/api/user/register")
def user_register(payload: RegisterPayload):
    """สมาชิกใหม่สมัครสมาชิกเองผ่านหน้าเว็บ"""
    clean_username = payload.username.strip().lower()
    if len(clean_username) < 3:
        raise HTTPException(status_code=400, detail="Username ต้องมีความยาวอย่างน้อย 3 ตัวอักษร")
    if len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีความยาวอย่างน้อย 4 ตัวอักษร")

    user_id = db.add_user(
        nfc_uid="",  # จะสร้างเป็น PENDING_XXXX ให้อัตโนมัติ เพื่อรอมาผูกบัตรที่ยิม
        name=payload.name,
        fitness_level=payload.fitness_level,
        target_goal=payload.target_goal,
        injury_note=payload.injury_note,
        gender=payload.gender,
        username=clean_username,
        password=payload.password
    )
    if not user_id:
        raise HTTPException(status_code=400, detail="Username นี้มีผู้ใช้งานแล้ว หรือข้อมูลไม่ถูกต้อง")
    user = db.get_user_by_id(user_id)
    return {"status": "success", "user": user}


@app.post("/api/user/login")
def user_login(payload: LoginPayload):
    """เข้าสู่ระบบด้วย Username & Password สำหรับสมาชิก"""
    user = db.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    return {"status": "success", "user": user}


@app.post("/api/user/change-password")
def change_user_password_endpoint(payload: ChangePasswordPayload):
    """สมาชิกเปลี่ยนรหัสผ่านของตนเอง"""
    success, msg = db.change_user_password(
        user_id=payload.user_id,
        old_password=payload.old_password,
        new_password=payload.new_password
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}


@app.get("/api/user/{user_id}/summary")
def get_user_summary_endpoint(user_id: int):
    """ดึงข้อมูลโปรไฟล์ แผนฝึก AI วันนี้ และประวัติย่อของสมาชิก"""
    summary = db.get_user_summary(user_id)
    if not summary:
        raise HTTPException(status_code=404, detail="User not found")
    return summary


@app.get("/api/user/{user_id}/history")
def get_user_history_endpoint(user_id: int, limit: int = 50):
    """ดึงประวัติการออกกำลังกายทั้งหมดของสมาชิก"""
    return db.get_user_workout_history(user_id, limit=limit)


@app.post("/api/user/log-workout")
def log_user_workout_endpoint(payload: LogWorkoutPayload):
    """สมาชิกบันทึกผลการออกกำลังกายจริงหลังเล่นเสร็จ"""
    success = db.log_workout(
        user_id=payload.user_id,
        station_id=payload.station_id,
        exercise_name=payload.exercise_name,
        weight_kg=payload.weight_kg,
        sets=payload.sets,
        reps=payload.reps
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to log workout session")
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    app_dir = os.path.dirname(os.path.abspath(__file__))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[app_dir],
        reload_excludes=["venv", ".venv", ".git", "__pycache__", "esp32"]
    )