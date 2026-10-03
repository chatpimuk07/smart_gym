from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from database import GymDatabase
from ai_service import GymAIService

app = FastAPI(title="Smart Gym NFC Hub")

# Initialize shared database and AI services
db = GymDatabase()
ai = GymAIService()


class RoutineRequest(BaseModel):
    nfc_uid: str
    station_id: str


@app.post("/api/get-routine")
def get_routine(req: RoutineRequest):
    # 1. Lookup user identity from NFC UID
    user = db.get_user_by_nfc(req.nfc_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Retrieve station profile
    station = db.get_station(req.station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    # 3. Mark the station status as busy for real-time monitoring
    db.update_station_status(req.station_id, "in_use", user["user_id"])

    # 4. Check daily cache to reduce latency and API token usage
    cached_json = db.get_cached_routine(user["user_id"], req.station_id)
    if cached_json:
        return Response(content=cached_json, media_type="application/json")

    # 5. Retrieve prior session history and trigger AI plan generation
    last_history = db.get_last_workout(user["user_id"], req.station_id)
    ai_json = ai.generate_routine(user, station, last_history)

    # 6. Save result to daily cache and stream back to ESP32
    db.save_cached_routine(user["user_id"], req.station_id, ai_json)
    return Response(content=ai_json, media_type="application/json")