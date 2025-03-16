from aiogram import F, types, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os

from database.orm_query import (
    orm_add_to_cart,
    orm_add_user,
    orm_get_product,
    orm_get_user_carts,
    orm_process_order_from_cart,
    orm_get_available_keys_count,
)
from filters.chat_types import ChatTypeFilter
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_callback_btns
from database.models import Cart, Key

user_private_router = Router()
user_private_router.message.filter(ChatTypeFilter(["private"]))

ADMIN_ID = int(os.getenv("ADMIN_ID"))


# FSM для оплаты
class OrderPayment(StatesGroup):
    waiting_for_payment_confirmation = State()  # Ожидание выбора "Оплатил" или "Отмена"
    waiting_for_screenshot = State()            # Ожидание скриншота оплаты

@user_private_router.message(CommandStart())
async def start_cmd(message: types.Message, session: AsyncSession):
    media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
    await message.answer_photo(media.media, caption=media.caption, reply_markup=reply_markup)

async def add_to_cart(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession):
    user = callback.from_user
    await orm_add_user(
        session,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=None,
    )
    await orm_add_to_cart(session, user_id=user.id, product_id=callback_data.product_id)
    await callback.answer("Товар добавлен в корзину.")

# Хендлер для обработки заказа из корзины
@user_private_router.callback_query(MenuCallBack.filter(F.menu_name == "order"))
async def process_order(callback: types.CallbackQuery, callback_data: MenuCallBack, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    carts = await orm_get_user_carts(session, user_id)
    if not carts:
        await callback.message.edit_media(
            media=types.InputMediaPhoto(media=callback.message.photo[-1].file_id, caption="Корзина пуста!"),
            reply_markup=None
        )
        await callback.answer()
        return

    # Проверка наличия всех товаров в корзине
    unavailable_items = []
    for cart in carts:
        available_keys = await orm_get_available_keys_count(session, cart.product_id)
        if available_keys < cart.quantity:
            unavailable_items.append(f"{cart.product.name} (нужно {cart.quantity}, доступно {available_keys})")

    if unavailable_items:
        # Если есть товары с недостаточным количеством ключей, показываем главное меню
        unavailable_list = "\n".join(unavailable_items)
        media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
        await callback.message.edit_media(
            media=types.InputMediaPhoto(
                media=media.media,
                caption=f"{media.caption}\n\n*Недостаточно товаров в наличии:*\n{unavailable_list}\nПожалуйста, обновите корзину.",
                parse_mode="Markdown"  # Перемещён сюда
            ),
            reply_markup=reply_markup  # Добавляем кнопки главного меню
        )
        await callback.answer()
        return

    # Если все товары доступны, продолжаем
    total_price = sum(cart.product.price * cart.quantity for cart in carts)
    product_list = "\n".join(f"{cart.product.name} ({cart.quantity} шт.)" for cart in carts)

    # Сохраняем данные в состоянии
    await state.update_data(user_id=user_id, cart_items=[cart.id for cart in carts])

    # Отправляем инструкцию по оплате
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=callback.message.photo[-1].file_id,
            caption=f"Ваша корзина:\n{product_list}\n"
                    f"Итого: {total_price} USDT.\n\n"
                    f"Инструкция по оплате:\n"
                    f"1. Переведите {total_price} USDT на счет: `TKw81JByTvE6GU4DGP12EohM3KeGY2ngk2`\n"
                    f"2. Отправляйте только USDT в сети Tron.\n"
                    f"3. После оплаты нажмите 'Оплатил' и отправьте скриншот.\n"
                    f"4. Ожидайте подтверждения от администратора.",
            parse_mode="Markdown"
        ),
        reply_markup=get_callback_btns(
            btns={
                "Оплатил": "paid",
                "Отмена": "cancel",
            },
            sizes=(2,)
        )
    )
    await state.set_state(OrderPayment.waiting_for_payment_confirmation)
    await callback.answer()

# Обработка выбора "Оплатил"
@user_private_router.callback_query(OrderPayment.waiting_for_payment_confirmation, F.data == "paid")
async def payment_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=callback.message.photo[-1].file_id,
            caption="Пожалуйста, отправьте скриншот оплаты."
        ),
        reply_markup=None
    )
    await state.set_state(OrderPayment.waiting_for_screenshot)
    await callback.answer()

# Обработка выбора "Отмена"
@user_private_router.callback_query(OrderPayment.waiting_for_payment_confirmation, F.data == "cancel")
async def payment_cancelled(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_media(
        media=types.InputMediaPhoto(
            media=callback.message.photo[-1].file_id,
            caption="Заказ отменён."
        ),
        reply_markup=None
    )
    await state.clear()
    await callback.answer()

# Обработка скриншота оплаты
@user_private_router.message(OrderPayment.waiting_for_screenshot, F.photo)
async def process_screenshot(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    user_id = data["user_id"]
    carts = await orm_get_user_carts(session, user_id)
    total_price = sum(cart.product.price * cart.quantity for cart in carts)
    product_list = "\n".join(f"{cart.product.name} ({cart.quantity} шт.)" for cart in carts)

    # Отправляем скриншот администратору
    await message.bot.send_photo(
        ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"Скриншот оплаты от пользователя {user_id}\n"
                f"Корзина:\n{product_list}\n"
                f"Итого: {total_price} руб.",
        reply_markup=get_callback_btns(
            btns={
                "Подтверждено": f"confirm_{user_id}",
                "Не подтверждено": f"reject_{user_id}",
            },
            sizes=(2,)
        )
    )
    await message.answer("Скриншот отправлен администратору. Ожидайте подтверждения.")
    await state.clear()

# Подтверждение оплаты администратором
@user_private_router.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery, session: AsyncSession):
    user_id = int(callback.data.split("_")[1])
    carts = await orm_get_user_carts(session, user_id)
    if not carts:
        await callback.message.edit_caption("Корзина пользователя пуста!", reply_markup=None)
        await callback.answer()
        return

    try:
        # Обрабатываем все товары в корзине и собираем ключи
        all_keys = []
        for cart in carts:
            keys = await orm_process_order_from_cart(session, user_id, cart.product_id)
            for key in keys:
                all_keys.append((cart.product, key))

        # Формируем сообщение с ключами и ссылками на инструкции
        response = (
            "Ваша оплата подтверждена!\n"
            "Инструкция по использованию ключей:\n"
            "1. Скопируйте ключ или скачайте файл.\n"
            "2. Используйте его в соответствующем приложении.\n\n"
            "Полезные ссылки на инструкции:\n"
            "1. [Скачать приложение для Android](https://play.google.com/store/apps/details?id=org.amnezia.vpn&hl=ru)\n"
            "2. [Скачать приложение для Android TV](https://play.google.com/store/search?q=amneziawg&c=apps&hl=ru)\n"
            "3. [Скачать приложение для iOS (инструкция)](https://docs.amnezia.org/ru/documentation/instructions/installing-amneziavpn-on-ios/)\n"
            "4. [Подключение через ключ в виде текста](https://docs.amnezia.org/ru/documentation/instructions/connect-via-text-key)\n"
            "5. [Подключение через файл конфигурации](https://docs.amnezia.org/ru/documentation/instructions/connect-via-config)\n"
            "6. [Подключение AmneziaVPN на Android TV](https://docs.amnezia.org/ru/documentation/instructions/android_tv_connect)\n\n"
        )
        for product, key in all_keys:
            response += f"Товар: {product.name}\n"
            if key.key_value:
                response += f"Ключ: `{key.key_value}`\n"
            if key.key_file:
                await callback.bot.send_document(user_id, key.key_file, caption=f"Товар: {product.name}")

        # Отправляем сообщение с Markdown-разметкой
        await callback.bot.send_message(user_id, response, parse_mode="Markdown")
        await callback.message.edit_caption("Оплата подтверждена, пользователю отправлены ключи.", reply_markup=None)
    except ValueError as e:
        await callback.bot.send_message(user_id, str(e))
        await callback.message.edit_caption(str(e), reply_markup=None)
    except Exception as e:
        await callback.bot.send_message(user_id, f"Ошибка: {str(e)}")
        await callback.message.edit_caption(f"Ошибка: {str(e)}", reply_markup=None)
    await callback.answer()

# Отклонение оплаты администратором
@user_private_router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.bot.send_message(user_id, "Ваша оплата не подтверждена администратором. Попробуйте снова.")
    await callback.message.edit_caption("Оплата отклонена.", reply_markup=None)
    await callback.answer()

# Отклонение оплаты администратором
@user_private_router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.bot.send_message(user_id, "Ваша оплата не подтверждена администратором. Попробуйте снова.")
    await callback.message.edit_caption("Оплата отклонена.", reply_markup=None)
    await callback.answer()

# Основной хендлер меню
@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession, state: FSMContext):
    if callback_data.menu_name == "add_to_cart":
        await add_to_cart(callback, callback_data, session)
        return
    elif callback_data.menu_name == "order":
        await process_order(callback, callback_data, state=state, session=session)
        return

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        category=callback_data.category,
        page=callback_data.page,
        product_id=callback_data.product_id,
        user_id=callback.from_user.id,
    )
    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()