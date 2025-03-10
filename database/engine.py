from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.models import Base
from common.texts_for_db import banners_data, categories, products

engine = create_async_engine("sqlite+aiosqlite:///my_db.db", echo=True)
session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with session_maker() as session:
        from database.orm_query import orm_add_banner_description, orm_add_category, orm_add_product
        for banner in banners_data:
            await orm_add_banner_description(session, name=banner["name"], description=banner["description"], image=banner.get("image"))
        for category_name in categories:
            await orm_add_category(session, category_name)
        async with session.begin():
            for name, price in products.items():
                category = (await session.execute("SELECT id FROM categories LIMIT 1")).scalar()
                await orm_add_product(session, category_id=category, name=name, price=price)

async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)