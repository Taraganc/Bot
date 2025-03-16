import os
from dotenv import load_dotenv

load_dotenv()

config = {
    "welcome_message": "👋 Добро пожаловать!",
    "understand_button": "Понятно ✅",
    "support_link": "https://t.me/support",
    "check_bot_token": os.getenv('CHECK_BOT_TOKEN'),
    "main_channel": "@LabradorFakt",  # Изменили формат
    "registration_link": "https://example.com/register",
    "admin_ids": [1373970155],  # Исправили ID
    "auto_approve": False
}