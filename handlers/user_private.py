from aiogram import Router, F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import orm_get_categories, orm_get_products, orm_get_banner, orm_add_to_cart, orm_get_user_carts, orm_create_order, orm_clear_cart, orm_get_keys
from keyboards.inline import get_user_main_btns, get_user_category_btns, get_user_products_btns, get_cart_btns

user_private_router = Router()

class OrderStates(StatesGroup):
    waiting_for_payment_proof = State()

@user_private_router.message(commands=["start"])
async def start_cmd(message: types.Message, session: AsyncSession):
    banner = await orm_get_banner(session, "main")
    await message.answer(banner.description, reply_markup=get_user_main_btns())

@user_private_router.callback_query(F.data == "catalog")
async def catalog_cmd(callback: types.CallbackQuery, session: AsyncSession):
    categories = await orm_get_categories(session)
    await callback.message.edit_text("Выберите категорию:", reply_markup=get_user_category_btns(categories))

@user_private_router.callback_query(F.data.startswith("category_"))
async def category_cmd(callback: types.CallbackQuery, session: AsyncSession):
    category_id = int(callback.data.split("_")[1])
    products = await orm_get_products(session, category_id)
    await callback.message.edit_text("Выберите продукт:", reply_markup=get_user_products_btns(products))

@user_private_router.callback_query(F.data.startswith("product_"))
async def product_cmd(callback: types.CallbackQuery, session: AsyncSession):
    product_id = int(callback.data.split("_")[1])
    await orm_add_to_cart(session, callback.from_user.id, product_id)
    await callback.answer("Товар добавлен в корзину!")

@user_private_router.callback_query(F.data == "cart")
async def cart_cmd(callback: types.CallbackQuery, session: AsyncSession):
    carts = await orm_get_user_carts(session, callback.from_user.id)
    if not carts:
        banner = await orm_get_banner(session, "cart")
        await callback.message.edit_text(banner.description, reply_markup=get_cart_btns())
    else:
        total = sum(cart.product.price * cart.quantity for cart in carts)
        text = "Ваша корзина:\n" + "\n".join(f"{cart.product.name} - {cart.quantity} шт. ({cart.product.price} руб.)" for cart in carts) + f"\nИтого: {total} руб."
        await callback.message.edit_text(text, reply_markup=get_cart_btns(has_items=True))

@user_private_router.callback_query(F.data == "order")
async def order_cmd(callback: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    carts = await orm_get_user_carts(session, callback.from_user.id)
    if not carts:
        await callback.answer("Корзина пуста!")
        return
    for cart in carts:
        if cart.product.available_keys < cart.quantity:
            await callback.answer(f"Недостаточно ключей для {cart.product.name}!")
            return
    total = sum(cart.product.price * cart.quantity for cart in carts)
    order = await orm_create_order(session, callback.from_user.id, callback.from_user.username, total, carts)
    await orm_clear_cart(session, callback.from_user.id)
    payment_banner = await orm_get_banner(session, "payment")
    await callback.message.edit_text(f"Заказ #{order.id} оформлен!\nСумма: {total} руб.\n\n{payment_banner.description}\n\nОтправьте скриншот чека об оплате.", reply_markup=None)
    await state.set_state(OrderStates.waiting_for_payment_proof)
    await state.update_data(order_id=order.id)
    for admin_id in callback.bot.my_admins_list:
        await callback.bot.send_message(admin_id, f"Новый заказ #{order.id} от @{callback.from_user.username}\nСумма: {total} руб.\nОжидает оплаты.")

@user_private_router.message(OrderStates.waiting_for_payment_proof, F.photo)
async def payment_proof_cmd(message: types.Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    order_id = data["order_id"]
    for admin_id in message.bot.my_admins_list:
        await message.bot.send_photo(admin_id, message.photo[-1].file_id, caption=f"Скриншот чека для заказа #{order_id} от @{message.from_user.username}", reply_markup=get_admin_order_btns(order_id))
    await message.answer("Скриншот отправлен администратору. Ожидайте подтверждения.")
    await state.clear()