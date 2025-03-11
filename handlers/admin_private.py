import logging
from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select  # Добавляем импорт select
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
    orm_delete_key,  # Добавляем новые функции
    orm_update_key,  # Добавляем новые функции
)

from filters.chat_types import ChatTypeFilter, IsAdmin

from kbds.inline import get_callback_btns
from kbds.reply import get_keyboard
from database.models import Key  # Добавляем импорт модели Key

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())


ADMIN_KB = get_keyboard(
    "Добавить товар",
    "Ассортимент",
    "Добавить/Изменить баннер",
    "Добавить ключ",
    "Удалить ключ",  # Новая кнопка
    "Изменить ключ",  # Новая кнопка
    placeholder="Выберите действие",
    sizes=(2,),
)


@admin_router.message(Command("admin"))
async def admin_features(message: types.Message):
    await message.answer("Что хотите сделать?", reply_markup=ADMIN_KB)


@admin_router.message(F.text == 'Ассортимент')
async def admin_features(message: types.Message, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name : f'category_{category.id}' for category in categories}
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

# Отправляем перечень информационных страниц бота и становимся в состояние отправки photo
@admin_router.message(StateFilter(None), F.text == 'Добавить/Изменить баннер')
async def add_image2(message: types.Message, state: FSMContext, session: AsyncSession):
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    await message.answer(f"Отправьте фото баннера.\nВ описании укажите для какой страницы:\
                         \n{', '.join(pages_names)}")
    await state.set_state(AddBanner.image)

# Добавляем/изменяем изображение в таблице (там уже есть записанные страницы по именам:
# main, catalog, cart(для пустой корзины), about, payment, shipping
@admin_router.message(AddBanner.image, F.photo)
async def add_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    image_id = message.photo[-1].file_id
    for_page = message.caption.strip()
    pages_names = [page.name for page in await orm_get_info_pages(session)]
    if for_page not in pages_names:
        await message.answer(f"Введите нормальное название страницы, например:\
                         \n{', '.join(pages_names)}")
        return
    await orm_change_banner_image(session, for_page, image_id,)
    await message.answer("Баннер добавлен/изменен.")
    await state.clear()

# ловим некоррекный ввод
@admin_router.message(AddBanner.image)
async def add_banner2(message: types.Message, state: FSMContext):
    await message.answer("Отправьте фото баннера или отмена")

#########################################################################################



######################### FSM для дабавления Ключей админом ###################

class AddKey(StatesGroup):
    product_id = State()    # Выбор продукта для ключа
    name = State()          # Название ключа
    key_type = State()      # Тип ключа (текст или файл)
    key_value = State()     # Значение ключа (если текст)
    key_file = State()      # Файл ключа (если файл)

    texts = {
        "AddKey:product_id": "Выберите продукт заново ⬆️",
        "AddKey:name": "Введите название ключа заново:",
        "AddKey:key_type": "Выберите тип ключа заново ⬆️",
        "AddKey:key_value": "Введите значение ключа заново:",
        "AddKey:key_file": "Загрузите файл ключа заново:",
    }

# Запуск FSM для добавления ключа
@admin_router.message(StateFilter(None), F.text == "Добавить ключ")
async def add_key_start(message: types.Message, state: FSMContext, session: AsyncSession):
    categories = await orm_get_categories(session)
    btns = {category.name: f"key_cat_{category.id}" for category in categories}
    await message.answer("Выберите категорию продукта для ключа", reply_markup=get_callback_btns(btns=btns))
    await state.set_state(AddKey.product_id)

# Выбор категории и отображение продуктов
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

# Выбор продукта
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

# Некорректный ввод на шаге выбора продукта
@admin_router.message(AddKey.product_id)
async def invalid_product_input(message: types.Message, state: FSMContext):
    await message.answer("Выберите продукт из кнопок!")

# Ввод названия ключа
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

# Некорректный ввод названия
@admin_router.message(AddKey.name)
async def invalid_key_name(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое название ключа!")

# Выбор типа ключа
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

# Некорректный ввод на шаге выбора типа ключа
@admin_router.message(AddKey.key_type)
async def invalid_key_type(message: types.Message, state: FSMContext):
    await message.answer("Выберите тип ключа из кнопок!")

# Ввод текстового значения ключа и сохранение
@admin_router.message(AddKey.key_value, F.text)
async def add_key_value(message: types.Message, state: FSMContext, session: AsyncSession):
    if len(message.text) > 150:
        await message.answer("Значение ключа не должно превышать 150 символов. Введите заново.")
        return
    data = await state.get_data()
    try:
        await orm_add_key(
            session,
            product_id=data["product_id"],
            name=data["name"],
            key_value=message.text,
            key_file=None
        )
        await message.answer("Ключ успешно добавлен!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ключа: {str(e)}", reply_markup=ADMIN_KB)
    finally:
        await state.clear()

# Некорректный ввод текстового значения
@admin_router.message(AddKey.key_value)
async def invalid_key_value(message: types.Message, state: FSMContext):
    await message.answer("Введите текстовое значение ключа!")

# Загрузка файла ключа и сохранение
@admin_router.message(AddKey.key_file, F.document)
async def add_key_file(message: types.Message, state: FSMContext, session: AsyncSession):
    file_id = message.document.file_id
    data = await state.get_data()
    try:
        await orm_add_key(
            session,
            product_id=data["product_id"],
            name=data["name"],
            key_value=None,
            key_file=file_id
        )
        await message.answer("Ключ в виде файла успешно добавлен!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при добавлении ключа: {str(e)}", reply_markup=ADMIN_KB)
    finally:
        await state.clear()

# Некорректный ввод файла
@admin_router.message(AddKey.key_file)
async def invalid_key_file(message: types.Message, state: FSMContext):
    await message.answer("Загрузите файл ключа (документ)!")

######################### FSM для удаления ключей админом ###################

class DeleteKey(StatesGroup):
    key_selection = State()  # Выбор ключа для удаления

# Запуск FSM для удаления ключа
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

# Выбор ключа для удаления
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

# Некорректный ввод на шаге выбора ключа
@admin_router.message(DeleteKey.key_selection)
async def invalid_key_selection(message: types.Message, state: FSMContext):
    await message.answer("Выберите ключ из кнопок!")



######################### FSM для изменения ключей админом ###################

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
    }
    await callback.message.answer(
        f"Выберите поле ключа '{key.name}' (ID: {key_id}) для изменения:",
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
        "keyfile": "key_file"
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
    await state.set_state(EditKey.new_value)
    await callback.answer()

@admin_router.message(EditKey.field_selection)
async def invalid_field_selection(message: types.Message, state: FSMContext):
    await message.answer("Выберите поле из кнопок!")

# Обработка текстовых значений (name, key_value, и очистка/отмена)
@admin_router.message(EditKey.new_value, F.text)
async def update_key_value_text(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    field = data["field"]
    new_value = message.text

    await message.answer(f"Обработка текста: key_id={key_id}, field={field}, value={new_value}")  # Отладка

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
    elif field == "key_value":
        if len(new_value) > 150:
            await message.answer("Значение ключа не должно превышать 150 символов. Введите заново.")
            return

    try:
        await orm_update_key(session, key_id, {field: new_value})
        await session.commit()
        await message.answer(f"Поле '{field}' ключа с ID {key_id} обновлено!", reply_markup=ADMIN_KB)
    except Exception as e:
        await message.answer(f"Ошибка при обновлении ключа: {str(e)}", reply_markup=ADMIN_KB)
    finally:
        await state.clear()

# Обработка загрузки файла (key_file)
@admin_router.message(EditKey.new_value, F.document)
async def update_key_file(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key_id = data["key_id"]
    field = data["field"]

    await message.answer(f"Обработка файла: key_id={key_id}, field={field}")  # Отладка

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

# Обработка некорректного ввода
@admin_router.message(EditKey.new_value)
async def invalid_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["field"]
    if field == "key_file":
        await message.answer("Загрузите файл или отправьте '-' для отмены!")
    elif field in ["name", "key_value"]:
        await message.answer(f"Введите значение для '{field}' или '-' для отмены!")