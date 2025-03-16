import os
from telegram import Bot
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

class SubscriptionChecker:
    def __init__(self):
        self.bot = Bot(token=os.getenv('CHECK_BOT_TOKEN'))
        
    async def check_subscription(self, channel_username: str, user_id: int) -> bool:
        try:
            # Получаем информацию о канале
            chat = await self.bot.get_chat(f"@{channel_username}")
            # Проверяем подписку
            member = await self.bot.get_chat_member(chat_id=chat.id, user_id=user_id)
            
            return member.status in ['member', 'administrator', 'creator']
            
        except Exception as e:
            logger.error(f"Ошибка при проверке подписки: {e}")
            return False