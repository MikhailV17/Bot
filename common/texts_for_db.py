from aiogram.utils.formatting import Bold, as_list, as_marked_section


categories = ['Ключи', 'Акции']

description_for_info_pages = {
    "main": "Добро пожаловать! Здесь вы можете посмотреть каталог предоставляемых услуг и выбрать что-то подходящее.",
    "about": "Сервис ремонта Youtube.com.\nРежим работы - круглосуточно.",
    "payment": as_marked_section(
        Bold("Варианты оплаты:"),
        "Крипловалютой USDT",
        "Tether (USDT в сети Tron)",
        "Адрес кошелька:",
        "TKw81JByTvE6GU4DGP12EohM3KeGY2ngk2",
        marker="✅ ",
    ).as_html(),
    "shipping": as_list(
        as_marked_section(
            Bold("Варианты доставки/заказа:"),
            "Письмом на почту",
            "Самовынос (Через Бота)",
            "Сообщением через Telegram",
            marker="✅ ",
        ),
        as_marked_section(Bold("Нельзя:"), "WatsApp", "СМС", marker="❌ "),
        sep="\n----------------------\n",
    ).as_html(),
    'catalog': 'Категории:',
    'cart': 'В корзине ничего нет!'
}
