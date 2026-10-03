import os
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types


# 1. Define structured JSON output schema using Pydantic
class WorkoutPlan(BaseModel):
    user: str = Field(description="User's display name for greetings")
    exercise: str = Field(description="Short, descriptive exercise name")
    target: str = Field(description="Recommended sets and reps format, e.g., 3 Sets x 10-12 Reps")
    weight: str = Field(description="Recommended working weight with units, e.g., 27.5 kg")
    tip: str = Field(description="Short form cue or safety instruction under 15 words")


# 2. Core service for managing Gemini API interactions
class GymAIService:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-3.8-flash"):
        """Initialize the Gemini client using parameter or environment variable."""
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is missing or invalid in environment variables.")
            
        self.client = genai.Client(api_key=key)
        self.model_name = model_name

    def generate_routine(
        self,
        user_info: Dict[str, Any],
        station_info: Dict[str, Any],
        last_history: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a personalized workout plan using user profile and station context.
        Returns a raw JSON string ready for transmission to the microcontroller.
        """
        # Handle cases where the user has no prior history at this specific station
        if last_history:
            history_text = (
                f"- Previous Working Weight: {last_history.get('weight_kg', 0)} kg "
                f"({last_history.get('sets_completed', 0)} sets x {last_history.get('reps_completed', 0)} reps)"
            )
        else:
            history_text = "- No prior workout history at this machine (First session)"

        prompt = f"""
        You are an elite fitness trainer generating a station-specific workout routine.

        [User Profile]
        - Name: {user_info.get('name', 'Member')}
        - Fitness Level: {user_info.get('fitness_level', 'Beginner')}
        - Primary Goal: {user_info.get('target_goal', 'General Fitness')}
        - Medical Notes / Injury Restrictions: {user_info.get('injury_note') or 'None'}

        [Current Station]
        - Machine: {station_info.get('station_name', 'Gym Machine')}
        - Target Muscle Group: {station_info.get('target_muscles', 'Full Body')}

        [Workout History]
        {history_text}

        [Instructions]
        - Apply progressive overload principles (or set a safe baseline if first session).
        - Keep the tip concise, actionable, and strictly compliant with injury restrictions.
        """

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=WorkoutPlan,
                temperature=0.3  # Deterministic output for structured fitness metrics
            )
        )

        return response.text