from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(AsyncAttrs, DeclarativeBase):
    pass

class Banner(Base):
    __tablename__ = "banners"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    image = Column(String, nullable=True)
    description = Column(String)
    created = Column(DateTime, default=func.now())
    updated = Column(DateTime, default=func.now(), onupdate=func.now())

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    created = Column(DateTime, default=func.now())
    updated = Column(DateTime, default=func.now(), onupdate=func.now())
    products = relationship("Product", back_populates="category")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String)
    description = Column(String, nullable=True)
    price = Column(Float)
    image = Column(String, nullable=True)
    available_keys = Column(Integer, default=0)  # Количество доступных ключей
    created = Column(DateTime, default=func.now())
    updated = Column(DateTime, default=func.now(), onupdate=func.now())
    category = relationship("Category", back_populates="products")

class Key(Base):
    __tablename__ = "keys"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    key_value = Column(String, nullable=True)  # Текстовый ключ
    key_file = Column(String, nullable=True)  # Путь к файлу ключа
    description = Column(String, nullable=True)
    expiry_date = Column(DateTime, nullable=True)  # Срок действия
    used = Column(Integer, default=0)  # 0 - не использован, 1 - использован
    created = Column(DateTime, default=func.now())

class Cart(Base):
    __tablename__ = "cart"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    username = Column(String)
    total = Column(Float)
    status = Column(String, default="pending")  # pending, paid, completed, rejected
    created = Column(DateTime, default=func.now())
    key_type = Column(String, nullable=True)  # text или file
    key_expiry = Column(DateTime, nullable=True)  # Срок действия ключа
    additional_info = Column(String, nullable=True)  # Доп. информация

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    quantity = Column(Integer)
    price = Column(Float)