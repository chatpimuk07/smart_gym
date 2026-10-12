import os
import json
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai.errors import APIError


# 1. Define structured JSON output schema using Pydantic
class WorkoutPlan(BaseModel):
    user: str = Field(description="User's display name for greetings")
    exercise: str = Field(description="Short, descriptive exercise name")
    target: str = Field(description="Recommended sets and reps format, e.g., 3 Sets x 10-12 Reps")
    weight: str = Field(description="Recommended working weight with units, e.g., 27.5 kg")
    tip: str = Field(description="Short form cue or safety instruction under 15 words")


# 2. Core service for managing Gemini API interactions
class GymAIService:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-flash-latest"):
        """Initialize the Gemini client using parameter or environment variable."""
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is missing or invalid in environment variables.")
            
        self.client = genai.Client(api_key=key)
        self.model_name = model_name

    def _build_prompt(self, user: dict, station: dict, last_history: Optional[dict] = None) -> str:
        """Construct the prompt using profile, station context, and workout history."""
        if last_history:
            history_text = (
                f"- Previous Working Weight: {last_history.get('weight_kg', 0)} kg "
                f"({last_history.get('sets_completed', 0)} sets x {last_history.get('reps_completed', 0)} reps)"
            )
        else:
            history_text = "- No prior workout history at this machine (First session)"

        return f"""
        You are an elite fitness trainer generating a station-specific workout routine.

        [User Profile]
        - Name: {user.get('name', 'Member')}
        - Fitness Level: {user.get('fitness_level', 'Beginner')}
        - Primary Goal: {user.get('target_goal', 'General Fitness')}
        - Medical Notes / Injury Restrictions: {user.get('injury_note') or 'None'}

        [Current Station]
        - Machine: {station.get('station_name', 'Gym Machine')}
        - Target Muscle Group: {station.get('target_muscles', 'Full Body')}

        [Workout History]
        {history_text}

        [Instructions]
        - Apply progressive overload principles (or set a safe baseline if first session).
        - Keep the tip concise, actionable, and strictly compliant with injury restrictions.
        """

    def generate_routine(self, user: dict, station: dict, last_history: Optional[dict] = None) -> str:
        prompt = self._build_prompt(user, station, last_history)
        
        # ลองโมเดลหลักก่อน และมีโมเดลสำรองเผื่อกรณีที่โมเดลใดโมเดลหนึ่งติด Overloaded/503
        candidate_models = [self.model_name]
        if self.model_name != "gemini-3.1-flash-lite":
            candidate_models.append("gemini-3.1-flash-lite")

        for model in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": WorkoutPlan,
                        "temperature": 0.3
                    }
                )
                if response and response.text:
                    return response.text
            except (APIError, Exception) as e:
                print(f"Gemini API model '{model}' unavailable or overloaded: {e}. Trying next...")

        # แผนสำรองอัตโนมัติเมื่อ Google Service ไม่พร้อมใช้งานทั้งหมด
        print("All Gemini models unavailable. Using fallback routine.")
        fallback_plan = {
            "user": user.get("name", "Member"),
            "exercise": station.get("station_name", "Machine Workout"),
            "target": "3 Sets x 10-12 Reps",
            "weight": f"{last_history.get('weight_kg', 20)} kg" if last_history else "Moderate Weight",
            "tip": "Service busy. Maintain proper form, brace core, and focus on steady tempo."
        }
        return json.dumps(fallback_plan, ensure_ascii=False)