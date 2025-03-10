from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, BigInteger, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    created: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Banner(Base):
    __tablename__ = 'banner'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(15), unique=True)
    image: Mapped[str] = mapped_column(String(150), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)


class Category(Base):
    __tablename__ = 'category'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)

    products: Mapped[list['Product']] = relationship(back_populates="category")  # Связь с продуктами


class Product(Base):
    __tablename__ = 'product'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)  # Описание может быть пустым
    price: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    image: Mapped[str] = mapped_column(String(150), nullable=True)  # Изображение необязательно
    available_keys: Mapped[int] = mapped_column(default=0)
    category_id: Mapped[int] = mapped_column(ForeignKey('category.id', ondelete='CASCADE'), nullable=False)

    category: Mapped['Category'] = relationship(back_populates="products")  # Связь с категорией
    keys: Mapped[list['Key']] = relationship(back_populates="product")  # Связь с ключами
    carts: Mapped[list['Cart']] = relationship(back_populates="product")  # Связь с корзиной


class Key(Base):
    __tablename__ = 'keys'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('product.id', ondelete='CASCADE'), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id', ondelete='SET NULL'), nullable=True)  # Новый внешний ключ
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    key_value: Mapped[str] = mapped_column(String(150), nullable=True)  # Текстовый ключ, необязательно
    key_file: Mapped[str] = mapped_column(String(150), nullable=True)  # Путь к файлу, необязательно
    expiration_date: Mapped[DateTime] = mapped_column(DateTime, nullable=True)  # Срок действия, необязательно
    used: Mapped[int] = mapped_column(default=0)  # 0 - не использован, 1 - использован

    product: Mapped['Product'] = relationship(back_populates="keys")  # Связь с продуктом
    user: Mapped['User'] = relationship(back_populates="keys")  # Уточняем обратную связь

class User(Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(150), nullable=True)
    last_name: Mapped[str] = mapped_column(String(150), nullable=True)
    phone: Mapped[str] = mapped_column(String(13), nullable=True)

    carts: Mapped[list['Cart']] = relationship(back_populates="user")  # Связь с корзиной
    keys: Mapped[list['Key']] = relationship(back_populates="user")  # Связь с ключами


class Cart(Base):
    __tablename__ = 'cart'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey('product.id', ondelete='CASCADE'), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)  # Количество не может быть NULL

    user: Mapped['User'] = relationship(back_populates="carts")  # Связь с пользователем
    product: Mapped['Product'] = relationship(back_populates="carts")  # Связь с продуктом