import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from dotenv import find_dotenv, load_dotenv
from middlewares.db import DataBaseSession
from database.engine import create_db, drop_db, session_maker
from handlers.user_private import user_private_router
from handlers.user_group import user_group_router
from handlers.admin_private import admin_private_router

load_dotenv(find_dotenv())

bot = Bot(token=os.getenv('TOKEN'), parse_mode=ParseMode.HTML)
bot.my_admins_list = [int(os.getenv('ADMIN_ID'))]  # Загружаем ID администратора из .env
dp = Dispatcher()

dp.include_router(user_private_router)
dp.include_router(user_group_router)
dp.include_router(admin_private_router)

async def on_startup(bot):
    await create_db()
    print('Бот запущен')

async def on_shutdown(bot):
    print('Бот завершил работу')

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    dp.update.middleware(DataBaseSession(session_pool=session_maker))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())