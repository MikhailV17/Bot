import logging
from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
)

from filters.chat_types import ChatTypeFilter, IsAdmin
from kbds.inline import get_callback_btns
from kbds.reply import get_keyboard
from database.models import Key

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())

ADMIN_KB = get_keyboard(
    "Добавить товар",
    "Ассортимент",
    "Добавить/Изменить баннер",
    "Добавить ключ",
    "Удалить ключ",
    "Изменить ключ",
    "Отмена операции",
    placeholder="Выберите действие",
    sizes=(2,),
)

@admin_router.message(F.text == "Отмена операции")
async def cancel_operation(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена!", reply_markup=ADMIN_KB)

@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await message.answer("Что хотите сделать?", reply_markup=ADMIN_KB)

@admin_router.message(F.text == 'Ассортимент')
async def admin_features(message: types.Message, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f'category_{category.id}' for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))

@admin_router.callback_query(F.data.startswith('category_'))
async def starring_at_product(callback: types.CallbackQuery, session: AsyncSession):
    category_id = callback.data.split('_')[-1]
    for product in await orm_get_products(session, int(category_id)):
        await callback.message.answer_photo(
            product.image,
            caption=f"<strong>{product.name}\
                    </strong>\n{product.description}\nСтоимость: {round(product.price, 2)}",
            reply_markup=get_callback_btns(
                btns={
                    "Удалить": f"delete_{product.id}",
                    "Изменить": f"change_{product.id}",
                },
                sizes=(2,)
            ),
        )
    await callback.answer()
    await callback.message.answer("ОК, вот список товаров ⏫")

@admin_router.callback_query(F.data.startswith("delete_"))
async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    product_id = callback.data.split("_")[-1]
    await orm_delete_product(session, int(product_id))
    await callback.answer("Товар удален")
    await callback.message.answer("Товар удален!")

################# Микро FSM для загрузки/изменения баннеров ############################

class AddBanner(StatesGroup):
    image = State()

@admin_router.message(StateFilter(None), F.text == 'Добавить/Изменить баннер')
async def add_image2(message: types.Message, state: FSMContext, session: AsyncSession):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await message.answer(f"Отправьте фото баннера.\nВ описании укажите для какой страницы:\
                         \n{', '.join(pages_names)}")
    await state.set_state(AddBanner.image)

@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(f"Введите нормальное название страницы, например:\
                         \n{', '.join(pages_names)}")
        return
    await orm_change_banner_image(session, for_page, image_id)
    await message.answer("Баннер добавлен/изменен.")
    await state.clear()

@admin_router.message(AddBanner.image)
async def add_banner2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или отмена")

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
    await callback.answer()
    await callback.message.answer("Введите название товара", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddProduct.name)

@admin_router.message(StateFilter(None), F.text == "Добавить товар")
async def add_product(message: types.Message, state: FSMContext):
    await message.answer("Введите название товара", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddProduct.name)

@admin_router.message(StateFilter("*"), Command("отмена"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return
    if AddProduct.product_for_change:
        AddProduct.product_for_change = None
    await state.clear()
    await message.answer("Действия отменены", reply_markup=ADMIN_KB)

@admin_router.message(StateFilter("*"), Command("назад"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "назад")
async def back_step_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state == AddProduct.name:
        await message.answer('Предыдущего шага нет, или введите название товара или напишите "отмена"')
        return
    previous = None
    for step in AddProduct.__all_states__:
        if step.state == current_state:
            await state.set_state(previous)
            await message.answer(f"Ок, вы вернулись к прошлому шагу \n {AddProduct.texts[previous.state]}")
            return
        previous = step

@admin_router.message(AddProduct.name, F.text)
async def add_name(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(name=AddProduct.product_for_change.name)
    else:
        if 4 >= len(message.text) >= 150:
            await message.answer("Название товара не должно превышать 150 символов\nили быть менее 5ти символов. \n Введите заново")
            return
        await state.update_data(name=message.text)
    await message.answer("Введите описание товара")
    await state.set_state(AddProduct.description)

@admin_router.message(AddProduct.name)
async def add_name2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите текст названия товара")

@admin_router.message(AddProduct.description, F.text)
async def add_description(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(description=AddProduct.product_for_change.description)
    else:
        if 4 >= len(message.text):
            await message.answer("Слишком короткое описание. \n Введите заново")
            return
        await state.update_data(description=message.text)
    categories = await orm_get_categories(session)
    btns = {category.name: str(category.id) for category in categories}
    await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddProduct.category)

@admin_router.message(AddProduct.description)
async def add_description2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите текст описания товара")

@admin_router.callback_query(AddProduct.category)
async def category_choice(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    if int(callback.data) in [category.id for category in await orm_get_categories(session)]:
        await callback.answer()
        await state.update_data(category=callback.data)
        await callback.message.answer('Теперь введите цену товара.')
        await state.set_state(AddProduct.price)
    else:
        await callback.message.answer('Выберите категорию из кнопок.')
        await callback.answer()

@admin_router.message(AddProduct.category)
async def category_choice2(message: types.Message, state: FSMContext):
    await message.answer("'Выберите категорию из кнопок.'")

@admin_router.message(AddProduct.price, F.text)
async def add_price(message: types.Message, state: FSMContext):
    if message.text == "." and AddProduct.product_for_change:
        await state.update_data(price=AddProduct.product_for_change.price)
    else:
        try:
            float(message.text)
        except ValueError:
            await message.answer("Введите корректное значение цены")
            return
        await state.update_data(price=message.text)
    await message.answer("Загрузите изображение товара")
    await state.set_state(AddProduct.image)

@admin_router.message(AddProduct.price)
async def add_price2(message: types.Message, state: FSMContext):
    await message.answer("Вы ввели не допустимые данные, введите стоимость товара")

@admin_router.message(AddProduct.image, or_f(F.photo, F.text == "."))
async def add_image(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text and message.text == "." and AddProduct.product_for_change:
        await state.update_data(image=AddProduct.product_for_change.image)
    elif message.photo:
        await state.update_data(image=message.photo[-1].file_id)
    else:
        await message.answer("Отправьте фото пищи")
        return
    data = await state.get_data()
    try:
        if AddProduct.product_for_change:
            await orm_update_product(session, AddProduct.product_for_change.id, data)
        else:
            await orm_add_product(session, data)
        await message.answer("Товар добавлен/изменен", reply_markup=ADMIN_KB)
        await state.clear()
    except Exception as e:
        await message.answer(f"Ошибка: \n{str(e)}\nОбратись к программеру, он опять денег хочет", reply_markup=ADMIN_KB)
        await state.clear()
    AddProduct.product_for_change = None

@admin_router.message(AddProduct.image)
async def add_image2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото пищи")

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

@admin_router.message(StateFilter(None), F.text == "Добавить ключ")
async def add_key_start(message: types.Message, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f"key_cat_{category.id}" for category in categories}
    await message.answer("Выберите категорию продукта для ключа", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddKey.product_id)

@admin_router.callback_query(AddKey.product_id, F.data.startswith("key_cat_"))
async def select_category_for_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    category_id = int(callback.data.split("_")[-1])
    products = await orm_get_products(session, category_id)
    if not products:
        await callback.message.answer("В этой категории нет продуктов!")
        await state.clear()
        await callback.answer()
        return
    btns = {product.name: f"key_prod_{product.id}" for product in products}
    await callback.message.answer("Выберите продукт", reply_markup=get_callback_btns(btns=btns))
    await callback.answer()

@admin_router.callback_query(AddKey.product_id, F.data.startswith("key_prod_"))
async def select_product_for_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    product_id = int(callback.data.split("_")[-1])
    product = await orm_get_product(session, product_id)
    if not product:
        await callback.message.answer("Продукт не найден!")
        await state.clear()
        await callback.answer()
        return
    await state.update_data(product_id=product_id)
    await callback.message.answer("Введите название ключа")
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
        await callback.message.answer("Введите значение ключа")
        await state.set_state(AddKey.key_value)
    elif callback.data == "key_file":
        await state.update_data(key_type="file")
        await callback.message.answer("Загрузите файл ключа")
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
        await message.answer("Ключ успешно добавлен!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ключа: {str(e)}", reply_markup=ADMIN_KB)
    finally:
        await state.clear()

######################### FSM для удаления ключей админом ###################

class DeleteKey(StatesGroup):
    key_selection = State()

@admin_router.message(StateFilter(None), F.text == "Удалить ключ")
async def delete_key_start(message: types.Message, state: FSMContext, session: AsyncSession):
    query = select(Key).where(Key.used == 0)
    result = await session.execute(query)
    keys = result.scalars().all()
    if not keys:
        await message.answer("Нет доступных ключей для удаления.", reply_markup=ADMIN_KB)
        return
    btns = {f"{key.name} (ID: {key.id})": f"del_key_{key.id}" for key in keys}
    await message.answer("Выберите ключ для удаления:", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(DeleteKey.key_selection)

@admin_router.callback_query(DeleteKey.key_selection, F.data.startswith("del_key_"))
async def confirm_delete_key(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    key_id = int(callback.data.split("_")[-1])
    query = select(Key).where(Key.id == key_id)
    result = await session.execute(query)
    key = result.scalar()
    if not key:
        await callback.message.answer("Ключ не найден!", reply_markup=ADMIN_KB)
        await state.clear()
        await callback.answer()
        return
    try:
        await orm_delete_key(session, key_id)
        await session.commit()
        await callback.message.answer(f"Ключ '{key.name}' (ID: {key_id}) удалён!", reply_markup=ADMIN_KB)
    except Exception as e:
        await callback.message.answer(f"Ошибка при удалении ключа: {str(e)}", reply_markup=ADMIN_KB)
    finally:
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

@admin_router.message(StateFilter(None), F.text == "Изменить ключ")
async def edit_key_start(message: types.Message, state: FSMContext, session: AsyncSession):
    query = select(Key).where(Key.used == 0)
    result = await session.execute(query)
    keys = result.scalars().all()
    if not keys:
        await message.answer("Нет доступных ключей для изменения.", reply_markup=ADMIN_KB)
        return
    btns = {f"{key.name} (ID: {key.id})": f"edit_key_{key.id}" for key in keys}
    await message.answer("Выберите ключ для изменения:", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(EditKey.key_selection)

@admin_router.callback_query(EditKey.key_selection, F.data.startswith("edit_key_"))
async def select_key_to_edit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    key_id = int(callback.data.split("_")[-1])
    query = select(Key).where(Key.id == key_id)
    result = await session.execute(query)
    key = result.scalar()
    if not key:
        await callback.message.answer("Ключ не найден!", reply_markup=ADMIN_KB)
        await state.clear()
        await callback.answer()
        return
    await state.update_data(key_id=key_id)
    btns = {
        "Название": "edit_field_name",
        "Значение ключа": "edit_field_keyvalue",
        "Файл ключа": "edit_field_keyfile",
        "Срок действия": "edit_field_validityperiod",
    }
    await callback.message.answer(
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
        await callback.message.answer("Некорректное поле!", reply_markup=ADMIN_KB)
        await state.clear()
        await callback.answer()
        return
    await state.update_data(field=mapped_field)
    if mapped_field == "name":
        await callback.message.answer("Введите новое название ключа (или '-' для отмены):")
    elif mapped_field == "key_value":
        await callback.message.answer("Введите новое значение ключа (или '-' для отмены):")
    elif mapped_field == "key_file":
        await callback.message.answer("Загрузите новый файл ключа (или отправьте '-' для отмены):")
    elif mapped_field == "validity_period":
        await callback.message.answer("Введите новый срок действия в днях (или '-' для бессрочного):")
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
            await message.answer(f"Поле '{field}' ключа с ID {key_id} очищено!", reply_markup=ADMIN_KB)
        except Exception as e:
            await message.answer(f"Ошибка при очистке ключа: {str(e)}", reply_markup=ADMIN_KB)
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
        await message.answer(f"Поле '{field}' ключа с ID {key_id} обновлено!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при обновлении ключа: {str(e)}", reply_markup=ADMIN_KB)
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
        await message.answer(f"Поле '{field}' ключа с ID {key_id} обновлено!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при обновлении ключа: {str(e)}", reply_markup=ADMIN_KB)
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