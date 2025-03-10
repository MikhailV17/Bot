from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

def get_user_main_btns():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Каталог", callback_data="catalog")],
        [InlineKeyboardButton(text="Корзина", callback_data="cart")],
    ])

def get_user_category_btns(categories):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=cat.name, callback_data=f"category_{cat.id}")] for cat in categories])

def get_user_products_btns(products):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{prod.name} ({prod.price} руб.) [{prod.available_keys} ключей]", callback_data=f"product_{prod.id}")] for prod in products])

def get_cart_btns(has_items=False):
    buttons = []
    if has_items:
        buttons.append([InlineKeyboardButton(text="Заказать", callback_data="order")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_order_btns(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Успешная оплата", callback_data=f"order_success_{order_id}")],
        [InlineKeyboardButton(text="Оплата не поступила", callback_data=f"order_reject_{order_id}")],
    ])