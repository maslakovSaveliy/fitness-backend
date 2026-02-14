from pydantic import BaseModel, Field
from typing import Literal


AllowedReps = Literal[5, 8, 10, 12, 15, 20]
AllowedSets = Literal[2, 3, 4, 5, 6]


class ExerciseAIOutput(BaseModel):
    name: str
    weight_kg: int = Field(ge=0, le=300)
    sets: AllowedSets
    reps: AllowedReps


class WorkoutAIOutput(BaseModel):
    title: str
    muscle_groups: list[str]
    exercises: list[ExerciseAIOutput]
    calories_burned: int
    wellbeing_advice: str | None = None


class WorkoutMetadataAIOutput(BaseModel):
    title: str
    muscle_groups: list[str]
    calories_burned: int


class ManualWorkoutAnalysisAIOutput(BaseModel):
    improved_description: str
    calories_burned: int
    post_workout_advice: str


class FoodAnalysisAIOutput(BaseModel):
    description: str
    calories: int
    proteins: int
    fats: int
    carbs: int


class MenuItemAIOutput(BaseModel):
    name: str
    calories: int
    proteins: int
    fats: int
    carbs: int


class MenuSectionAIOutput(BaseModel):
    type: Literal["breakfast", "lunch", "dinner", "snacks"]
    title: str
    time_range: str
    items: list[MenuItemAIOutput]


class DailyMenuAIOutput(BaseModel):
    target_calories: int
    target_proteins: int
    target_fats: int
    target_carbs: int
    sections: list[MenuSectionAIOutput]
    tip_of_day: str
