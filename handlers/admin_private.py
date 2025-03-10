from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import orm_add_banner_description, orm_add_category, orm_add_product, orm_add_key, orm_get_keys, orm_update_key
from common.texts_for_db import banners_data, categories, products
from keyboards.inline import get_admin_order_btns

admin_private_router = Router()

class AdminStates(StatesGroup):
    adding_key = State()
    editing_payment = State()

@admin_private_router.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id not in message.bot.my_admins_list:
        await message.answer("У вас нет прав администратора!")
        return
    await message.answer("Панель администратора:\n/add_key - Добавить ключ\n/edit_payment - Редактировать инструкцию по оплате")

@admin_private_router.message(Command("add_key"))
async def add_key_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in message.bot.my_admins_list:
        return
    await message.answer("Введите данные ключа в формате: <product_id>|<key_value>|<description>|<expiry_date YYYY-MM-DD> (или оставьте пустым для файла)")
    await state.set_state(AdminStates.adding_key)

@admin_private_router.message(AdminStates.adding_key)
async def process_add_key(message: types.Message, session: AsyncSession, state: FSMContext):
    try:
        product_id, key_value, description, expiry_date = message.text.split("|")
        await orm_add_key(session, int(product_id), key_value, None, description, expiry_date or None)
        await message.answer("Ключ добавлен!")
    except ValueError:
        await message.answer("Неверный формат! Пример: 1|ABC123|Описание|2025-12-31")
    await state.clear()

@admin_private_router.message(Command("edit_payment"))
async def edit_payment_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in message.bot.my_admins_list:
        return
    await message.answer("Введите новую инструкцию по оплате:")
    await state.set_state(AdminStates.editing_payment)

@admin_private_router.message(AdminStates.editing_payment)
async def process_edit_payment(message: types.Message, session: AsyncSession, state: FSMContext):
    await orm_add_banner_description(session, "payment", message.text)
    await message.answer("Инструкция по оплате обновлена!")
    await state.clear()

@admin_private_router.callback_query(F.data.startswith("order_success_"))
async def order_success_cmd(callback: types.CallbackQuery, session: AsyncSession):
    order_id = int(callback.data.split("_")[2])
    order = (await session.execute(select(Order).where(Order.id == order_id))).scalars().first()
    carts = await orm_get_user_carts(session, order.user_id)
    for cart in carts:
        keys = await orm_get_keys(session, cart.product_id)
        if keys:
            key = keys[0]
            await orm_update_key(session, key.id)
            await callback.bot.send_message(order.user_id, f"Ваш заказ #{order_id} оплачен!\nКлюч: {key.key_value or key.key_file}")
    order.status = "completed"
    await session.commit()
    await callback.message.edit_text(f"Заказ #{order_id} успешно оплачен!")

@admin_private_router.callback_query(F.data.startswith("order_reject_"))
async def order_reject_cmd(callback: types.CallbackQuery, session: AsyncSession):
    order_id = int(callback.data.split("_")[2])
    order = (await session.execute(select(Order).where(Order.id == order_id))).scalars().first()
    order.status = "rejected"
    await session.commit()
    await callback.bot.send_message(order.user_id, f"Оплата для заказа #{order_id} не подтверждена.")
    await callback.message.edit_text(f"Оплата для заказа #{order_id} отклонена.")