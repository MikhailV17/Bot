from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Banner, Category, Product, Cart, Order, OrderItem, Key

async def orm_add_banner_description(session: AsyncSession, name: str, description: str, image: str = None):
    banner = Banner(name=name, description=description, image=image)
    session.add(banner)
    await session.commit()

async def orm_add_category(session: AsyncSession, name: str):
    stmt = select(Category).where(Category.name == name)
    result = await session.execute(stmt)
    if result.scalars().first():
        return False
    session.add(Category(name=name))
    await session.commit()
    return True

async def orm_add_product(session: AsyncSession, category_id: int, name: str, price: float, available_keys: int = 0):
    product = Product(category_id=category_id, name=name, price=price, available_keys=available_keys)
    session.add(product)
    await session.commit()

async def orm_get_categories(session: AsyncSession):
    query = select(Category)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_get_products(session: AsyncSession, category_id: int):
    query = select(Product).where(Product.category_id == category_id)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_get_banner(session: AsyncSession, name: str):
    query = select(Banner).where(Banner.name == name)
    result = await session.execute(query)
    return result.scalars().first()

async def orm_add_to_cart(session: AsyncSession, user_id: int, product_id: int):
    query = select(Cart).where(Cart.user_id == user_id, Cart.product_id == product_id)
    result = await session.execute(query)
    cart = result.scalars().first()
    if cart:
        cart.quantity += 1
    else:
        session.add(Cart(user_id=user_id, product_id=product_id, quantity=1))
    await session.commit()

async def orm_get_user_carts(session: AsyncSession, user_id: int):
    query = select(Cart).where(Cart.user_id == user_id)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_clear_cart(session: AsyncSession, user_id: int):
    await session.execute("DELETE FROM cart WHERE user_id = :user_id", {"user_id": user_id})
    await session.commit()

async def orm_create_order(session: AsyncSession, user_id: int, username: str, total: float, items: list):
    order = Order(user_id=user_id, username=username, total=total)
    session.add(order)
    await session.flush()
    for item in items:
        session.add(OrderItem(order_id=order.id, product_id=item.product_id, quantity=item.quantity, price=item.product.price))
        await session.execute(update(Product).where(Product.id == item.product_id).values(available_keys=Product.available_keys - item.quantity))
    await session.commit()
    return order

async def orm_add_key(session: AsyncSession, product_id: int, key_value: str = None, key_file: str = None, description: str = None, expiry_date=None):
    key = Key(product_id=product_id, key_value=key_value, key_file=key_file, description=description, expiry_date=expiry_date)
    session.add(key)
    await session.execute(update(Product).where(Product.id == product_id).values(available_keys=Product.available_keys + 1))
    await session.commit()

async def orm_get_keys(session: AsyncSession, product_id: int):
    query = select(Key).where(Key.product_id == product_id, Key.used == 0)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_update_key(session: AsyncSession, key_id: int, used: int = 1):
    await session.execute(update(Key).where(Key.id == key_id).values(used=used))
    await session.commit()