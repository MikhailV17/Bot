import logging
from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from datetime import datetime

from database.orm_query import (
    orm_change_banner_image,
    orm_get_categories,
    orm_add_product,
    orm_delete_product,
    orm_get_info_pages,
    orm_get_product,
    orm_get_products,
    orm_update_product,
    orm_add_key,
    orm_delete_key,
    orm_update_key,
    orm_get_all_keys,
    orm_get_free_keys,
    orm_get_expired_keys,
)

from filters.chat_types import ChatTypeFilter, IsAdmin
from kbds.inline import get_callback_btns
from kbds.reply import get_keyboard
from database.models import Key

# Предполагаем, что ADMIN_ID загружается из конфигурации или .env
# Замените на ваш реальный ID администратора
ADMIN_ID = 700865418  # Укажите ваш ID администратора здесь или настройте через .env

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())

# Инлайн-клавиатура для администратора
ADMIN_INLINE_KB = get_callback_btns(
    btns={
        "Добавить товар": "add_product",
        "Ассортимент": "list_products",
        "Добавить/Изменить баннер": "change_banner",
        "Добавить ключ": "add_key",
        "Удалить ключ": "delete_key",
        "Изменить ключ": "edit_key",
        "Список ключей": "list_keys",
        "Отмена операции": "cancel_operation",
    },
    sizes=(2,)
)

@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await message.answer("Что хотите сделать?", reply_markup=ADMIN_INLINE_KB)

# Обработчики для кнопок ADMIN_INLINE_KB
@admin_router.callback_query(F.data == "add_product")
async def add_product_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите название товара")
    await state.set_state(AddProduct.name)
    await callback.answer()

@admin_router.callback_query(F.data == "list_products")
async def list_products_callback(callback: types.CallbackQuery, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f'category_{category.id}' for category in categories}
    await callback.message.edit_text("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await callback.answer()

@admin_router.callback_query(F.data == "change_banner")
async def change_banner_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await callback.message.edit_text(
        f"Отправьте фото баннера.\nВ описании укажите для какой страницы:\n{', '.join(pages_names)}"
    )
    await state.set_state(AddBanner.image)
    await callback.answer()

@admin_router.callback_query(F.data == "add_key")
async def add_key_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f"key_cat_{category.id}" for category in categories}
    await callback.message.edit_text(
        "Выберите категорию продукта для ключа",
        reply_markup=get_callback_btns(btns=btns)
    )
    await state.set_state(AddKey.product_id)
    await callback.answer()

@admin_router.callback_query(F.data == "delete_key")
async def delete_key_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    query = select(Key).where(Key.used == 0)
    result = await session.execute(query)
    keys = result.scalars().all()
    if not keys:
        await callback.message.edit_text("Нет доступных ключей для удаления.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        btns = {f"{key.name} (ID: {key.id})": f"del_key_{key.id}" for key in keys}
        await callback.message.edit_text(
            "Выберите ключ для удаления:",
            reply_markup=get_callback_btns(btns=btns)
        )
        await state.set_state(DeleteKey.key_selection)
    await callback.answer()

@admin_router.callback_query(F.data == "edit_key")
async def edit_key_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    query = select(Key).where(Key.used == 0)
    result = await session.execute(query)
    keys = result.scalars().all()
    if not keys:
        await callback.message.edit_text("Нет доступных ключей для изменения.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        btns = {f"{key.name} (ID: {key.id})": f"edit_key_{key.id}" for key in keys}
        await callback.message.edit_text(
            "Выберите ключ для изменения:",
            reply_markup=get_callback_btns(btns=btns)
        )
        await state.set_state(EditKey.key_selection)
    await callback.answer()

@admin_router.callback_query(F.data == "list_keys")
async def list_keys_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выберите категорию ключей для просмотра:",
        reply_markup=get_callback_btns(
            btns={
                "Все ключи": "view_all_keys",
                "Свободные ключи": "view_free_keys",
                "Просроченные ключи": "view_expired_keys",
                "Назад": "cancel",
            }
        )
    )
    await state.set_state(ViewKeys.key_list)
    await callback.answer()

@admin_router.callback_query(F.data == "cancel_operation")
async def cancel_operation_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Операция отменена!", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()

@admin_router.callback_query(F.data.startswith('category_'))
async def starring_at_product(callback: types.CallbackQuery, session: AsyncSession):
    category_id = callback.data.split('_')[-1]
    products = await orm_get_products(session, int(category_id))
    if not products:
        await callback.message.edit_text("В этой категории нет товаров.", reply_markup=ADMIN_INLINE_KB)
    else:
        for product in products:
            await callback.message.answer_photo(
                product.image,
                caption=f"<strong>{product.name}</strong>\n{product.description}\nСтоимость: {round(product.price, 2)}",
                reply_markup=get_callback_btns(
                    btns={
                        "Удалить": f"delete_{product.id}",
                        "Изменить": f"change_{product.id}",
                    },
                    sizes=(2,)
                ),
            )
        await callback.message.edit_text("ОК, вот список товаров ⏫", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()

@admin_router.callback_query(F.data.startswith("delete_"))
async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))
    await callback.message.edit_text("Товар удалён!", reply_markup=ADMIN_INLINE_KB)
    await callback.answer()

################# Микро FSM для загрузки/изменения баннеров ############################

class AddBanner(StatesGroup):
    image = State()

@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip() if message.caption else ""
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(f"Введите нормальное название страницы, например:\n{', '.join(pages_names)}")
        return
    await orm_change_banner_image(session, for_page, image_id)
    await message.answer("Баннер добавлен/изменён.", reply_markup=ADMIN_INLINE_KB)
    await state.clear()

@admin_router.message(AddBanner.image)
async def add_banner_invalid(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или используйте команду 'отмена'")

#########################################################################################
######################### FSM для добавления/изменения товаров админом ###################

class AddProduct(StatesGroup):
    name = State()
    description = State()
    category = State()
    price = State()
    image = State()

    product_for_change = None

    texts = {
        "AddProduct:name": "Введите название заново:",
        "AddProduct:description": "Введите описание заново:",
        "AddProduct:category": "Выберите категорию заново ⬆️",
        "AddProduct:price": "Введите стоимость заново:",
        "AddProduct:image": "Этот стейт последний, поэтому...",
    }

@admin_router.callback_query(StateFilter(None), F.data.startswith("change_"))
async def change_product_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    product_for_change = await orm_get_product(session, int(product_id))
    AddProduct.product_for_change = product_for_change
    await callback.message.edit_text("Введите название товара")
    await state.set_state(AddProduct.name)
    await callback.answer()

@admin_router.message(StateFilter("*"), Command("отмена"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    await state.clear()
    await message.answer("Действия отменены", reply_markup=ADMIN_INLINE_KB)

@admin_router.message(StateFilter("*"), Command("назад"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "назад")
async def back_step_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == AddProduct.name:
        await message.answer('Предыдущего шага нет, введите название товара или напишите "отмена"')
        return
    previous = None
    for step in AddProduct.__all_states__:
        if step.state == current_state:
            await state.set_state(previous)
            await message.answer(f"Ок, вы вернулись к прошлому шагу\n{AddProduct.texts[previous.state]}")
            return
        previous = step

@admin_router.message(AddProduct.name, F.text)
async def add_name(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        if len(message.text) < 5 or len(message.text) > 150:
            await message.answer("Название товара должно быть от 5 до 150 символов. Введите заново.")
            return
        await state.update_data(name=message.text)
    await message.answer("Введите описание товара")
    await state.set_state(AddProduct.description)

@admin_router.message(AddProduct.name)
async def add_name_invalid(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое название товара!")

@admin_router.message(AddProduct.description, F.text)
async def add_description(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(description=AddProduct.product_for_change.description)
    else:
        if len(message.text) < 5:
            await message.answer("Слишком короткое описание. Введите заново.")
            return
        await state.update_data(description=message.text)
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddProduct.category)

@admin_router.message(AddProduct.description)
async def add_description_invalid(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое описание товара!")

@admin_router.callback_query(AddProduct.category)
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if int(callback.data) in [category.id for category in await orm_get_categories(session)]:
        await state.update_data(category=callback.data)
        await callback.message.edit_text("Теперь введите цену товара.")
        await state.set_state(AddProduct.price)
    else:
        await callback.message.edit_text("Выберите категорию из кнопок.")
    await callback.answer()

@admin_router.message(AddProduct.category)
async def category_choice_invalid(message: types.Message, state: FSMContext):
    await message.answer("Выберите категорию из кнопок!")

@admin_router.message(AddProduct.price, F.text)
async def add_price(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(price=AddProduct.product_for_change.price)
    else:
        try:
            price = float(message.text)
            if price <= 0:
                await message.answer("Цена должна быть положительной. Введите заново.")
                return
            await state.update_data(price=price)
        except ValueError:
            await message.answer("Введите корректное значение цены (число).")
            return
    await message.answer("Загрузите изображение товара")
    await state.set_state(AddProduct.image)

@admin_router.message(AddProduct.price)
async def add_price_invalid(message: types.Message, state: FSMContext):
    await message.answer("Введите числовое значение цены!")

@admin_router.message(AddProduct.image, or_f(F.photo, F.text == "."))
async def add_image(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(image=AddProduct.product_for_change.image)
    elif message.photo:
        await state.update_data(image=message.photo[-1].file_id)
    else:
        await message.answer("Отправьте фото товара!")
        return
    data = await state.get_data()
    try:
        if AddProduct.product_for_change:
            await orm_update_product(session, AddProduct.product_for_change.id, data)
        else:
            await orm_add_product(session, data)
        await message.answer("Товар добавлен/изменён", reply_markup=ADMIN_INLINE_KB)
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    finally:
        await state.clear()
        AddProduct.product_for_change = None

@admin_router.message(AddProduct.image)
async def add_image_invalid(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото товара или используйте точку (.), если редактируете!")

######################### FSM для добавления ключей админом ###################

class AddKey(StatesGroup):
    product_id = State()
    name = State()
    key_type = State()
    key_value = State()
    key_file = State()
    validity_period = State()

    texts = {
        "AddKey:product_id": "Выберите продукт заново ⬆️",
        "AddKey:name": "Введите название ключа заново:",
        "AddKey:key_type": "Выберите тип ключа заново ⬆️",
        "AddKey:key_value": "Введите значение ключа заново:",
        "AddKey:key_file": "Загрузите файл ключа заново:",
        "AddKey:validity_period": "Введите срок действия ключа (в днях) заново:",
    }

@admin_router.callback_query(AddKey.product_id, F.data.startswith("key_cat_"))
async def select_category_for_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data.split("_")[-1])
    products = await orm_get_products(session, category_id)
    if not products:
        await callback.message.edit_text("В этой категории нет продуктов!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        btns = {product.name: f"key_prod_{product.id}" for product in products}
        await callback.message.edit_text("Выберите продукт", reply_markup=get_callback_btns(btns=btns))
    await callback.answer()

@admin_router.callback_query(AddKey.product_id, F.data.startswith("key_prod_"))
async def select_product_for_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    product_id = int(callback.data.split("_")[-1])
    product = await orm_get_product(session, product_id)
    if not product:
        await callback.message.edit_text("Продукт не найден!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        await state.update_data(product_id=product_id)
        await callback.message.edit_text("Введите название ключа")
        await state.set_state(AddKey.name)
    await callback.answer()

@admin_router.message(AddKey.product_id)
async def invalid_product_input(message: types.Message, state: FSMContext):
    await message.answer("Выберите продукт из кнопок!")

@admin_router.message(AddKey.name, F.text)
async def add_key_name(message: types.Message, state: FSMContext):
    if len(message.text) > 150:
        await message.answer("Название ключа не должно превышать 150 символов. Введите заново.")
        return
    await state.update_data(name=message.text)
    await message.answer(
        "Выберите тип ключа:",
        reply_markup=get_callback_btns(btns={"Текст": "key_text", "Файл": "key_file"})
    )
    await state.set_state(AddKey.key_type)

@admin_router.message(AddKey.name)
async def invalid_key_name(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое название ключа!")

@admin_router.callback_query(AddKey.key_type, F.data.in_(["key_text", "key_file"]))
async def select_key_type(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "key_text":
        await state.update_data(key_type="text")
        await callback.message.edit_text("Введите значение ключа")
        await state.set_state(AddKey.key_value)
    elif callback.data == "key_file":
        await state.update_data(key_type="file")
        await callback.message.edit_text("Загрузите файл ключа")
        await state.set_state(AddKey.key_file)
    await callback.answer()

@admin_router.message(AddKey.key_type)
async def invalid_key_type(message: types.Message, state: FSMContext):
    await message.answer("Выберите тип ключа из кнопок!")

@admin_router.message(AddKey.key_value, F.text)
async def add_key_value(message: types.Message, state: FSMContext, session: AsyncSession):
    if len(message.text) > 1500:
        await message.answer("Значение ключа не должно превышать 1500 символов. Введите заново.")
        return
    await state.update_data(key_value=message.text)
    await message.answer("Введите срок действия ключа в днях (или '-' для бессрочного)")
    await state.set_state(AddKey.validity_period)

@admin_router.message(AddKey.key_value)
async def invalid_key_value(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое значение ключа!")

@admin_router.message(AddKey.key_file, F.document)
async def add_key_file(message: types.Message, state: FSMContext, session: AsyncSession):
    file_id = message.document.file_id
    await state.update_data(key_file=file_id)
    await message.answer("Введите срок действия ключа в днях (или '-' для бессрочного)")
    await state.set_state(AddKey.validity_period)

@admin_router.message(AddKey.key_file)
async def invalid_key_file(message: types.Message, state: FSMContext):
    await message.answer("Загрузите файл ключа (документ)!")

@admin_router.message(AddKey.validity_period, F.text)
async def add_validity_period(message: types.Message, state: FSMContext, session: AsyncSession):
    validity_period = None
    if message.text != "-":
        try:
            validity_period = int(message.text)
            if validity_period <= 0:
                await message.answer("Срок действия должен быть положительным числом. Введите заново.")
                return
        except ValueError:
            await message.answer("Введите число дней или '-' для бессрочного ключа.")
            return

    data = await state.get_data()
    try:
        await orm_add_key(
            session,
            product_id=data["product_id"],
            name=data["name"],
            key_value=data.get("key_value"),
            key_file=data.get("key_file"),
            validity_period=validity_period
        )
        await message.answer("Ключ успешно добавлен!", reply_markup=ADMIN_INLINE_KB)
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ключа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    finally:
        await state.clear()

######################### FSM для удаления ключей админом ###################

class DeleteKey(StatesGroup):
    key_selection = State()

@admin_router.callback_query(DeleteKey.key_selection, F.data.startswith("del_key_"))
async def confirm_delete_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    key_id = int(callback.data.split("_")[-1])
    query = select(Key).where(Key.id == key_id)
    result = await session.execute(query)
    key = result.scalar()
    if not key:
        await callback.message.edit_text("Ключ не найден!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        try:
            await orm_delete_key(session, key_id)
            await session.commit()
            await callback.message.edit_text(f"Ключ '{key.name}' (ID: {key_id}) удалён!", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await callback.message.edit_text(f"Ошибка при удалении ключа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    await state.clear()
    await callback.answer()

@admin_router.message(DeleteKey.key_selection)
async def invalid_key_selection(message: types.Message, state: FSMContext):
    await message.answer("Выберите ключ из кнопок!")

######################### FSM для изменения ключей админом ###################

class EditKey(StatesGroup):
    key_selection = State()
    field_selection = State()
    new_value = State()

@admin_router.callback_query(EditKey.key_selection, F.data.startswith("edit_key_"))
async def select_key_to_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    key_id = int(callback.data.split("_")[-1])
    query = select(Key).where(Key.id == key_id)
    result = await session.execute(query)
    key = result.scalar()
    if not key:
        await callback.message.edit_text("Ключ не найден!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        await state.update_data(key_id=key_id)
        btns = {
            "Название": "edit_field_name",
            "Значение ключа": "edit_field_keyvalue",
            "Файл ключа": "edit_field_keyfile",
            "Срок действия": "edit_field_validityperiod",
        }
        await callback.message.edit_text(
            f"Выберите поле ключа '{key.name}' (ID: {key.id}) для изменения:",
            reply_markup=get_callback_btns(btns=btns)
        )
        await state.set_state(EditKey.field_selection)
    await callback.answer()

@admin_router.callback_query(EditKey.field_selection, F.data.startswith("edit_field_"))
async def select_field_to_edit(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[-1]
    field_mapping = {
        "name": "name",
        "keyvalue": "key_value",
        "keyfile": "key_file",
        "validityperiod": "validity_period"
    }
    mapped_field = field_mapping.get(field)
    if not mapped_field:
        await callback.message.edit_text("Некорректное поле!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        await state.update_data(field=mapped_field)
        if mapped_field == "name":
            await callback.message.edit_text("Введите новое название ключа (или '-' для отмены):")
        elif mapped_field == "key_value":
            await callback.message.edit_text("Введите новое значение ключа (или '-' для отмены):")
        elif mapped_field == "key_file":
            await callback.message.edit_text("Загрузите новый файл ключа (или отправьте '-' для отмены):")
        elif mapped_field == "validity_period":
            await callback.message.edit_text("Введите новый срок действия в днях (или '-' для бессрочного):")
        await state.set_state(EditKey.new_value)
    await callback.answer()

@admin_router.message(EditKey.field_selection)
async def invalid_field_selection(message: types.Message, state: FSMContext):
    await message.answer("Выберите поле из кнопок!")

@admin_router.message(EditKey.new_value, F.text)
async def update_key_value_text(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    field = data["field"]
    new_value = message.text

    if new_value == "-":
        try:
            await orm_update_key(session, key_id, {field: None})
            await session.commit()
            await message.answer(f"Поле '{field}' ключа с ID {key_id} очищено!", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await message.answer(f"Ошибка при очистке ключа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
        finally:
            await state.clear()
        return

    if field == "name":
        if not new_value or len(new_value) > 150:
            await message.answer("Название ключа должно быть от 1 до 150 символов. Введите заново.")
            return
        query = select(Key).where(Key.name == new_value, Key.id != key_id)
        result = await session.execute(query)
        if result.scalar():
            await message.answer("Ключ с таким названием уже существует! Введите другое название.")
            return
    elif field == "key_value":
        if len(new_value) > 1500:
            await message.answer("Значение ключа не должно превышать 1500 символов. Введите заново.")
            return
    elif field == "validity_period":
        try:
            validity_period = int(new_value)
            if validity_period <= 0:
                await message.answer("Срок действия должен быть положительным числом. Введите заново.")
                return
            new_value = validity_period
        except ValueError:
            await message.answer("Введите число дней!")
            return

    try:
        await orm_update_key(session, key_id, {field: new_value})
        await session.commit()
        await message.answer(f"Поле '{field}' ключа с ID {key_id} обновлено!", reply_markup=ADMIN_INLINE_KB)
    except Exception as e:
        await message.answer(f"Ошибка при обновлении ключа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    finally:
        await state.clear()

@admin_router.message(EditKey.new_value, F.document)
async def update_key_file(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    field = data["field"]

    if field != "key_file":
        await message.answer("Ожидается текстовое значение, а не файл! Введите заново.")
        return

    new_value = message.document.file_id
    try:
        await orm_update_key(session, key_id, {field: new_value})
        await session.commit()
        await message.answer(f"Поле '{field}' ключа с ID {key_id} обновлено!", reply_markup=ADMIN_INLINE_KB)
    except Exception as e:
        await message.answer(f"Ошибка при обновлении ключа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    finally:
        await state.clear()

@admin_router.message(EditKey.new_value)
async def invalid_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["field"]
    if field == "key_file":
        await message.answer("Загрузите файл или отправьте '-' для отмены!")
    elif field in ["name", "key_value", "validity_period"]:
        await message.answer(f"Введите значение для '{field}' или '-' для отмены!")

######################### FSM для просмотра ключей и отправки сообщений ###################

class ViewKeys(StatesGroup):
    key_list = State()
    key_action = State()

class SendMessage(StatesGroup):
    message_type = State()
    custom_message = State()

@admin_router.callback_query(F.data == "list_keys")
async def list_keys_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выберите категорию ключей для просмотра:",
        reply_markup=get_callback_btns(
            btns={
                "Все ключи": "view_all_keys",
                "Свободные ключи": "view_free_keys",
                "Просроченные ключи": "view_expired_keys",
                "Назад": "cancel",
            }
        )
    )
    await state.set_state(ViewKeys.key_list)
    await callback.answer()

@admin_router.callback_query(ViewKeys.key_list, F.data.in_(["view_all_keys", "view_free_keys", "view_expired_keys"]))
async def view_keys(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if callback.data == "view_all_keys":
        keys = await orm_get_all_keys(session)
        title = "Все ключи:"
    elif callback.data == "view_free_keys":
        keys = await orm_get_free_keys(session)
        title = "Свободные ключи:"
    elif callback.data == "view_expired_keys":
        keys = await orm_get_expired_keys(session)
        title = "Просроченные ключи:"

    if not keys:
        await callback.message.edit_text(f"{title}\nКлючи не найдены.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        response = f"{title}\n"
        btns = {}
        for key in keys:
            status = "Свободен" if not key.used else f"Куплен (ID: {key.user_id})"
            expiration = key.expiration_date.strftime('%Y-%m-%d %H:%M:%S UTC') if key.expiration_date else "Бессрочный"
            response += (
                f"ID: {key.id} | Товар: {key.product.name} | Название: {key.name}\n"
                f"Статус: {status} | Срок: {key.validity_period or 'Нет'} дней | Окончание: {expiration}\n\n"
            )
            btns[f"Ключ {key.id}"] = f"key_action_{key.id}"
        await callback.message.edit_text(response, reply_markup=get_callback_btns(btns=btns, sizes=(2,)))
        await state.set_state(ViewKeys.key_action)
    await callback.answer()

@admin_router.callback_query(ViewKeys.key_list, F.data == "cancel")
async def cancel_view_keys(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выберите действие:", reply_markup=ADMIN_INLINE_KB)
    await state.clear()
    await callback.answer()

@admin_router.callback_query(ViewKeys.key_action, F.data.startswith("key_action_"))
async def key_action(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    key_id = int(callback.data.split("_")[-1])
    query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
    result = await session.execute(query)
    key = result.scalar()
    if not key:
        await callback.message.edit_text("Ключ не найден!", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        await state.update_data(key_id=key_id)
        btns = {
            "Отправить уведомление": "send_expiration_notice",
            "Написать сообщение": "send_custom_message",
            "Назад": "back_to_list",
        }
        user_info = f"Куплен пользователем: {key.user_id}" if key.used else "Свободен"
        await callback.message.edit_text(
            f"Ключ ID: {key.id}\nТовар: {key.product.name}\nНазвание: {key.name}\n{user_info}\nВыберите действие:",
            reply_markup=get_callback_btns(btns=btns)
        )
        await state.set_state(SendMessage.message_type)
    await callback.answer()

@admin_router.callback_query(ViewKeys.key_action, F.data == "back_to_list")
async def back_to_key_list(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "Выберите категорию ключей для просмотра:",
        reply_markup=get_callback_btns(
            btns={
                "Все ключи": "view_all_keys",
                "Свободные ключи": "view_free_keys",
                "Просроченные ключи": "view_expired_keys",
                "Назад": "cancel",
            }
        )
    )
    await state.set_state(ViewKeys.key_list)
    await callback.answer()

@admin_router.callback_query(SendMessage.message_type, F.data == "send_expiration_notice")
async def send_expiration_notice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
    result = await session.execute(query)
    key = result.scalar()

    if not key.user_id:
        await callback.message.edit_text("Этот ключ не куплен, уведомление не отправлено.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        notice = (
            "Уважаемый пользователь!\n"
            f"Срок действия вашего ключа '{key.name}' для товара '{key.product.name}' истёк "
            f"{key.expiration_date.strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
            "Для продления обратитесь к администратору."
        )
        await callback.bot.send_message(key.user_id, notice)
        await callback.message.edit_text("Уведомление об окончании срока действия отправлено.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    await callback.answer()

@admin_router.callback_query(SendMessage.message_type, F.data == "send_custom_message")
async def start_custom_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите текст сообщения для пользователя (или '-' для отмены):")
    await state.set_state(SendMessage.custom_message)
    await callback.answer()

@admin_router.message(SendMessage.custom_message, F.text)
async def send_custom_message(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    if "key_id" in data:  # Первое сообщение от администратора по ключу
        key_id = data["key_id"]
        query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
        result = await session.execute(query)
        key = result.scalar()

        if not key.user_id:
            await message.answer("Этот ключ не куплен, сообщение не отправлено.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return

        if message.text == "-":
            await message.answer("Отправка сообщения отменена.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return

        try:
            await message.bot.send_message(
                key.user_id,
                f"Сообщение от администратора:\n{message.text}",
                reply_markup=get_callback_btns(
                    btns={
                        "Ответить": f"reply_to_admin_{key.user_id}",
                        "Отмена": "cancel_reply"
                    }
                )
            )
            await message.answer("Сообщение отправлено пользователю.", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await message.answer(f"Ошибка при отправке сообщения: {str(e)}", reply_markup=ADMIN_INLINE_KB)
        finally:
            await state.clear()
    elif "user_id" in data and "is_admin_reply" not in data:  # Ответ пользователя администратору
        user_id = data["user_id"]
        if message.text == "-":
            await message.answer("Отправка ответа отменена.")
            await state.clear()
            return
        try:
            await message.bot.send_message(
                ADMIN_ID,
                f"Ответ от пользователя {user_id}:\n{message.text}",
                reply_markup=get_callback_btns(
                    btns={
                        "Ответить": f"reply_to_user_{user_id}",
                        "Отмена": "cancel_admin_reply"
                    }
                )
            )
            await message.answer("Ваш ответ отправлен администратору.")
        except Exception as e:
            await message.answer(f"Не удалось отправить ответ администратору: {str(e)}")
            logging.error(f"Ошибка при отправке ответа администратору {ADMIN_ID}: {str(e)}")
        finally:
            await state.clear()
    elif "user_id" in data and "is_admin_reply" in data:  # Ответ администратора пользователю
        user_id = data["user_id"]
        if message.text == "-":
            await message.answer("Отправка ответа отменена.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return
        try:
            await message.bot.send_message(
                user_id,
                f"Ответ от администратора:\n{message.text}",
                reply_markup=get_callback_btns(
                    btns={
                        "Ответить": f"reply_to_admin_{user_id}",
                        "Отмена": "cancel_reply"
                    }
                )
            )
            await message.answer("Ответ отправлен пользователю.", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await message.answer(f"Ошибка при отправке ответа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
        finally:
            await state.clear()

# Обработка ответа пользователя через инлайн-кнопку
@admin_router.callback_query(F.data.startswith("reply_to_admin_"))
async def user_reply_to_admin(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(user_id=user_id)
    await callback.message.edit_text("Введите ваш ответ администратору (или '-' для отмены):")
    await state.set_state(SendMessage.custom_message)
    await callback.answer()

@admin_router.callback_query(F.data == "cancel_reply")
async def cancel_user_reply(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Диалог завершён.")
    await state.clear()
    await callback.answer()

# Обработка ответа администратора через инлайн-кнопку
@admin_router.callback_query(F.data.startswith("reply_to_user_"))
async def admin_reply_to_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(user_id=user_id, is_admin_reply=True)  # Добавляем флаг, что это ответ администратора
    await callback.message.edit_text("Введите текст ответа пользователю (или '-' для отмены):")
    await state.set_state(SendMessage.custom_message)
    await callback.answer()

@admin_router.callback_query(F.data == "cancel_admin_reply")
async def cancel_admin_reply(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Диалог завершён.", reply_markup=ADMIN_INLINE_KB)
    await state.clear()
    await callback.answer()


@admin_router.callback_query(ViewKeys.key_action, F.data == "back_to_list")
async def back_to_key_list(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "Выберите категорию ключей для просмотра:",
        reply_markup=get_callback_btns(
            btns={
                "Все ключи": "view_all_keys",
                "Свободные ключи": "view_free_keys",
                "Просроченные ключи": "view_expired_keys",
                "Назад": "cancel",
            }
        )
    )
    await state.set_state(ViewKeys.key_list)
    await callback.answer()

@admin_router.callback_query(SendMessage.message_type, F.data == "send_expiration_notice")
async def send_expiration_notice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
    result = await session.execute(query)
    key = result.scalar()

    if not key.user_id:
        await callback.message.edit_text("Этот ключ не куплен, уведомление не отправлено.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    else:
        notice = (
            "Уважаемый пользователь!\n"
            f"Срок действия вашего ключа '{key.name}' для товара '{key.product.name}' истёк "
            f"{key.expiration_date.strftime('%Y-%m-%d %H:%M:%S UTC')}.\n"
            "Для продления обратитесь к администратору."
        )
        await callback.bot.send_message(key.user_id, notice)
        await callback.message.edit_text("Уведомление об окончании срока действия отправлено.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
    await callback.answer()

@admin_router.callback_query(SendMessage.message_type, F.data == "send_custom_message")
async def start_custom_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите текст сообщения для пользователя (или '-' для отмены):")
    await state.set_state(SendMessage.custom_message)
    await callback.answer()

@admin_router.message(SendMessage.custom_message, F.text)
async def send_custom_message(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
    result = await session.execute(query)
    key = result.scalar()

    if not key.user_id:
        await message.answer("Этот ключ не куплен, сообщение не отправлено.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
        return

    if message.text == "-":
        await message.answer("Отправка сообщения отменена.", reply_markup=ADMIN_INLINE_KB)
        await state.clear()
        return

    try:
        await message.bot.send_message(
            key.user_id,
            f"Сообщение от администратора:\n{message.text}\n\n"
            f"Вы можете ответить на это сообщение, и администратор получит ваш ответ."
        )
        await message.answer("Сообщение отправлено пользователю.", reply_markup=ADMIN_INLINE_KB)
    except Exception as e:
        await message.answer(f"Ошибка при отправке сообщения: {str(e)}", reply_markup=ADMIN_INLINE_KB)
    finally:
        await state.clear()

# Обработка ответа пользователя
@admin_router.message(F.reply_to_message, ChatTypeFilter(["private"]))
async def handle_user_reply(message: types.Message):
    if message.from_user.id != message.bot.get_me().id:  # Проверяем, что это не бот отвечает
        try:
            await message.bot.send_message(
                ADMIN_ID,  # Используем реальный ID администратора
                f"Ответ от пользователя {message.from_user.id}:\n{message.text}",
                reply_markup=get_callback_btns(btns={"Ответить": f"reply_to_{message.from_user.id}"})
            )
            await message.answer("Ваш ответ отправлен администратору.")
        except Exception as e:
            await message.answer(f"Не удалось отправить ответ администратору: {str(e)}")
            logging.error(f"Ошибка при отправке ответа администратору {ADMIN_ID}: {str(e)}")

@admin_router.callback_query(F.data.startswith("reply_to_"))
async def admin_reply_to_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[-1])
    await state.update_data(user_id=user_id)
    await callback.message.edit_text("Введите текст ответа пользователю (или '-' для отмены):")
    await state.set_state(SendMessage.custom_message)
    await callback.answer()

@admin_router.message(SendMessage.custom_message, F.text)
async def send_admin_reply(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    if "user_id" in data:  # Это ответ пользователю
        user_id = data["user_id"]
        if message.text == "-":
            await message.answer("Отправка ответа отменена.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return
        try:
            await message.bot.send_message(
                user_id,
                f"Ответ от администратора:\n{message.text}\n\n"
                f"Вы можете ответить на это сообщение."
            )
            await message.answer("Ответ отправлен пользователю.", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await message.answer(f"Ошибка при отправке ответа: {str(e)}", reply_markup=ADMIN_INLINE_KB)
        finally:
            await state.clear()
    else:
        # Логика для отправки сообщения по ключу (оставлена без изменений)
        key_id = data["key_id"]
        query = select(Key).where(Key.id == key_id).options(joinedload(Key.product))
        result = await session.execute(query)
        key = result.scalar()

        if not key.user_id:
            await message.answer("Этот ключ не куплен, сообщение не отправлено.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return

        if message.text == "-":
            await message.answer("Отправка сообщения отменена.", reply_markup=ADMIN_INLINE_KB)
            await state.clear()
            return

        try:
            await message.bot.send_message(
                key.user_id,
                f"Сообщение от администратора:\n{message.text}\n\n"
                f"Вы можете ответить на это сообщение, и администратор получит ваш ответ."
            )
            await message.answer("Сообщение отправлено пользователю.", reply_markup=ADMIN_INLINE_KB)
        except Exception as e:
            await message.answer(f"Ошибка при отправке сообщения: {str(e)}", reply_markup=ADMIN_INLINE_KB)
        finally:
            await state.clear()