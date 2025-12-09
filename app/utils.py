"""Общие утилиты приложения."""

REQUIRED_PROFILE_FIELDS = ["goal", "level", "location"]


def user_has_profile(user: dict) -> bool:
    """
    Проверяет, заполнил ли пользователь обязательные поля профиля.
    
    Args:
        user: Словарь с данными пользователя
    
    Returns:
        True если все обязательные поля заполнены
    """
    return all(user.get(field) for field in REQUIRED_PROFILE_FIELDS)
