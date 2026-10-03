from database import GymDatabase


def seed_mock_data():
    """Seed initial mock data for users, stations, and prior workout history."""
    db = GymDatabase("gym.db")

    print("--- Seeding Gym Database ---")

    # 1. Mock Users
    # Note: Replace these NFC UIDs with your actual NFC card/sticker UIDs when testing hardware
    users_data = [
        {
            "nfc_uid": "04A1B2C3",
            "name": "Non",
            "fitness_level": "Intermediate",
            "target_goal": "Hypertrophy (Muscle Gain)",
            "injury_note": "Right shoulder impingement (Avoid deep shoulder flare)",
            "gender": "Male"
        },
        {
            "nfc_uid": "A3B4C5D6",
            "name": "Sarah",
            "fitness_level": "Beginner",
            "target_goal": "General Fitness & Core Strength",
            "injury_note": None,
            "gender": "Female"
        },
        {
            "nfc_uid": "E7F8G9H0",
            "name": "Mike",
            "fitness_level": "Advanced",
            "target_goal": "Strength & Powerlifting",
            "injury_note": "Lower back tightness (Keep neutral spine)",
            "gender": "Male"
        }
    ]

    for u in users_data:
        # Check if user already exists to avoid duplicate constraint errors
        existing_user = db.get_user_by_nfc(u["nfc_uid"])
        if not existing_user:
            user_id = db.add_user(
                nfc_uid=u["nfc_uid"],
                name=u["name"],
                fitness_level=u["fitness_level"],
                target_goal=u["target_goal"],
                injury_note=u["injury_note"],
                gender=u["gender"]
            )
            print(f"Added User: {u['name']} (ID: {user_id}, NFC: {u['nfc_uid']})")
        else:
            print(f"User already exists: {u['name']} (NFC: {u['nfc_uid']})")

    # 2. Mock Stations
    stations_data = [
        {
            "station_id": "STATION_CHEST_PRESS",
            "station_name": "Seated Chest Press Machine",
            "target_muscles": "Pectoralis Major, Anterior Deltoids, Triceps"
        },
        {
            "station_id": "STATION_LAT_PULLDOWN",
            "station_name": "Cable Lat Pulldown",
            "target_muscles": "Latissimus Dorsi, Biceps, Upper Back"
        },
        {
            "station_id": "STATION_LEG_EXTENSION",
            "station_name": "Leg Extension Machine",
            "target_muscles": "Quadriceps"
        }
    ]

    for s in stations_data:
        db.register_station(
            station_id=s["station_id"],
            station_name=s["station_name"],
            target_muscles=s["target_muscles"]
        )
        print(f"Registered Station: {s['station_name']} ({s['station_id']})")

    # 3. Mock Prior Workout History (For testing Progressive Overload)
    # Adding historical log for user 'Non' at Chest Press machine
    non_user = db.get_user_by_nfc("04A1B2C3")
    if non_user:
        # Check if history already exists to prevent duplicate test rows
        last_log = db.get_last_workout(non_user["user_id"], "STATION_CHEST_PRESS")
        if not last_log:
            db.log_workout(
                user_id=non_user["user_id"],
                station_id="STATION_CHEST_PRESS",
                exercise_name="Seated Chest Press Machine",
                weight_kg=25.0,
                sets=3,
                reps=10
            )
            print(f"Added baseline history for {non_user['name']} at STATION_CHEST_PRESS (25.0 kg)")
        else:
            print(f"History already exists for {non_user['name']} at STATION_CHEST_PRESS")

    db.close()
    print("--- Database Seeding Completed ---")


if __name__ == "__main__":
    seed_mock_data()