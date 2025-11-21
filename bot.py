import logging
import sqlite3
import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
import requests
import json

# Настройки бота
BOT_TOKEN = "8592468598:AAE3e2Idp8q2HYnQU3XdmJLYUxwda-Vx46g"
ADMIN_CHAT_ID = 7973988177

# Настройки Platega (СБП)
PLATEGA_MERCHANT_ID = "c06562b7-3636-435e-bb04-f0e69f1c2aed"
PLATEGA_API_KEY = "vh3dcCTGSim9sy4MhCaHYyb8Vn3iByiikS0P5LN5u6aaWsEE7PjZHChiIow9EtZ2eBUG1p1FayF8s6j66EdWMnwZWYKh5ttTt"
PLATEGA_BASE_URL = "https://platega.com/api/v2"

# Настройки Crypto Bot
CRYPTO_BOT_TOKEN = "490665:AAEwanehVerJ8FvFsTf81CWtyY9wSFW86aF"
CRYPTO_BOT_URL = "https://pay.crypt.bot/api"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица товаров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            type TEXT NOT NULL,
            category_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance REAL DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица платежей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            payment_system TEXT,
            status TEXT DEFAULT 'pending',
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем стандартные категории
    cursor.execute('''
        INSERT OR IGNORE INTO categories (name) VALUES 
        ('👥 Приватные группы'),
        ('🔌 Плагины'),
        ('🎨 Другое')
    ''')
    
    conn.commit()
    conn.close()

# Функции для работы с пользователями
def get_user(user_id: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_balance(user_id: int, amount: float):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

# Функции для работы с категориями
def add_category(name: str):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_categories():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()
    return categories

def get_category(category_id: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories WHERE id = ?', (category_id,))
    category = cursor.fetchone()
    conn.close()
    return category

def delete_category(category_id: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    # Сначала обновляем товары этой категории на NULL
    cursor.execute('UPDATE products SET category_id = NULL WHERE category_id = ?', (category_id,))
    cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()

# Функции для работы с товарами
def add_product(name: str, description: str, price: float, product_type: str, category_id: int = None):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO products (name, description, price, type, category_id) VALUES (?, ?, ?, ?, ?)',
        (name, description, price, product_type, category_id)
    )
    conn.commit()
    conn.close()

def get_products(category_id: int = None):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    if category_id:
        cursor.execute('''
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.category_id = ?
            ORDER BY p.created_at DESC
        ''', (category_id,))
    else:
        cursor.execute('''
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            ORDER BY p.created_at DESC
        ''')
    
    products = cursor.fetchall()
    conn.close()
    return products

def get_product(product_id: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.*, c.name as category_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        WHERE p.id = ?
    ''', (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def delete_product(product_id: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str, last_name: str):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
        (user_id, username, first_name, last_name)
    )
    conn.commit()
    conn.close()

def get_user_stats():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM payments WHERE status = "completed"')
    total_payments = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(amount) FROM payments WHERE status = "completed"')
    total_revenue = cursor.fetchone()[0] or 0
    
    conn.close()
    return total_users, total_payments, total_revenue

# Функции для получения курса USDT
def get_usdt_rate() -> float:
    """Получаем актуальный курс USDT к RUB"""
    try:
        # Пробуем получить курс с Binance
        response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=USDTRUB')
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
        
        # Если Binance не работает, пробуем другие источники
        response = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub')
        if response.status_code == 200:
            data = response.json()
            return data['tether']['rub']
        
        # Запасной курс
        return 90.0
    except Exception as e:
        logger.error(f"Error getting USDT rate: {e}")
        return 90.0  # Запасной курс

# Функции для работы с платежными системами
def create_platega_payment(amount: float, description: str) -> Optional[Dict]:
    """Создание платежа через Platega (СБП)"""
    try:
        # Platega API может требовать другой формат запроса
        headers = {
            'Authorization': f'Bearer {PLATEGA_API_KEY}',
            'Content-Type': 'application/json',
            'X-Merchant-ID': PLATEGA_MERCHANT_ID
        }
        
        data = {
            'amount': amount,
            'currency': 'RUB',
            'description': description,
            'merchant_id': PLATEGA_MERCHANT_ID
        }
        
        # Пробуем разные эндпоинты Platega API
        endpoints = [
            f'{PLATEGA_BASE_URL}/payment',
            f'{PLATEGA_BASE_URL}/create',
            f'{PLATEGA_BASE_URL}/invoice'
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=data,
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    # Адаптируемся к разным форматам ответа
                    if 'payment_url' in result:
                        return result
                    elif 'url' in result:
                        return {'payment_url': result['url'], 'payment_id': result.get('id', 'unknown')}
                    elif 'invoice_url' in result:
                        return {'payment_url': result['invoice_url'], 'payment_id': result.get('invoice_id', 'unknown')}
            except Exception as e:
                logger.error(f"Platega endpoint {endpoint} failed: {e}")
                continue
        
        logger.error("All Platega endpoints failed")
        return None
            
    except Exception as e:
        logger.error(f"Platega payment creation error: {e}")
        return None

def create_crypto_payment(amount_rub: float, description: str) -> Optional[Dict]:
    """Создание платежа через Crypto Bot с конвертацией RUB в USDT"""
    try:
        # Получаем актуальный курс
        usdt_rate = get_usdt_rate()
        amount_usdt = amount_rub / usdt_rate
        
        headers = {
            'Crypto-Pay-API-Token': CRYPTO_BOT_TOKEN,
            'Content-Type': 'application/json'
        }
        
        data = {
            'amount': round(amount_usdt, 6),  # Округляем до 6 знаков для USDT
            'asset': 'USDT',
            'description': description,
            'expires_in': 3600  # Срок жизни инвойса 1 час
        }
        
        response = requests.post(
            f'{CRYPTO_BOT_URL}/createInvoice',
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok') and 'result' in result:
                # Добавляем информацию о курсе
                result['exchange_rate'] = usdt_rate
                result['amount_rub'] = amount_rub
                return result
        else:
            logger.error(f"Crypto Bot error {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Crypto Bot payment creation error: {e}")
        return None

# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = [
        [InlineKeyboardButton("🛍️ Магазин", callback_data="shop_categories")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    
    if user.id == ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Добро пожаловать, {user.first_name}!\n\n"
        "Я бот для покупки приватных групп и плагинов.\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Помощь по боту**\n\n"
        "• Для просмотра товаров нажмите '🛍️ Магазин'\n"
        "• Выберите категорию и товар\n"
        "• Выберите способ оплаты\n"
        "• После оплаты вы получите доступ к товару\n\n"
        "Если возникли проблемы - свяжитесь с администратором."
    )

# Обработчики callback'ов
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "shop_categories":
        await show_categories(query, context)
    elif data == "profile":
        await show_profile(query, context)
    elif data == "help":
        await help_callback(query, context)
    elif data == "admin_panel":
        await admin_panel(query, context)
    elif data == "admin_stats":
        await admin_stats(query, context)
    elif data == "admin_broadcast":
        await admin_broadcast(query, context)
    elif data == "admin_add_product":
        await admin_add_product(query, context)
    elif data == "admin_manage_categories":
        await admin_manage_categories(query, context)
    elif data == "topup_balance":
        await topup_balance(query, context)
    elif data.startswith("topup_"):
        amount = float(data.split("_")[1])
        await choose_topup_method(query, context, amount)
    elif data.startswith("topup_pay_"):
        parts = data.split("_")
        amount = float(parts[2])
        payment_method = parts[3]
        await process_topup_payment(query, context, amount, payment_method)
    elif data.startswith("category_"):
        category_id = int(data.split("_")[1])
        await show_products_in_category(query, context, category_id)
    elif data.startswith("product_"):
        product_id = int(data.split("_")[1])
        await show_product(query, context, product_id)
    elif data.startswith("buy_"):
        product_id = int(data.split("_")[1])
        await choose_payment_method(query, context, product_id)
    elif data.startswith("pay_"):
        parts = data.split("_")
        product_id = int(parts[1])
        payment_method = parts[2]
        await process_payment(query, context, product_id, payment_method)
    elif data.startswith("admin_delete_category_"):
        category_id = int(data.split("_")[3])
        await admin_delete_category(query, context, category_id)
    elif data.startswith("admin_add_category"):
        await admin_add_category(query, context)
    elif data == "back_to_shop":
        await show_categories(query, context)
    elif data == "back_to_admin":
        await admin_panel(query, context)
    elif data == "back_to_profile":
        await show_profile(query, context)

# Показать профиль
async def show_profile(query, context):
    user = get_user(query.from_user.id)
    if not user:
        await query.answer("Пользователь не найден!")
        return
    
    user_id, username, first_name, last_name, balance, registered_at = user
    
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_balance")],
        [InlineKeyboardButton("🛍️ В магазин", callback_data="shop_categories")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="start")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👤 **Ваш профиль**\n\n"
        f"💼 Баланс: {balance:.2f} руб.\n"
        f"👤 Имя: {first_name} {last_name or ''}\n"
        f"📅 Регистрация: {registered_at[:10]}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Пополнение баланса
async def topup_balance(query, context):
    keyboard = [
        [InlineKeyboardButton("100 руб.", callback_data="topup_100")],
        [InlineKeyboardButton("500 руб.", callback_data="topup_500")],
        [InlineKeyboardButton("1000 руб.", callback_data="topup_1000")],
        [InlineKeyboardButton("5000 руб.", callback_data="topup_5000")],
        [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💳 **Пополнение баланса**\n\n"
        "Выберите сумму для пополнения:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def choose_topup_method(query, context, amount: float):
    total_amount = amount + (amount * 0.05)  # Комиссия 5%
    
    keyboard = [
        [InlineKeyboardButton("🇷🇺 СБП", callback_data=f"topup_pay_{amount}_sbp")],
        [InlineKeyboardButton("₿ Crypto Bot", callback_data=f"topup_pay_{amount}_crypto")],
        [InlineKeyboardButton("🔙 Назад", callback_data="topup_balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"💳 **Пополнение на {amount} руб.**\n\n"
        f"💰 Сумма: {amount} руб.\n"
        f"💸 Комиссия (5%): {amount * 0.05:.2f} руб.\n"
        f"💵 Итого к оплате: {total_amount:.2f} руб.\n\n"
        f"Выберите способ оплаты:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def process_topup_payment(query, context, amount: float, payment_method: str):
    total_amount = amount + (amount * 0.05)
    
    if payment_method == "sbp":
        payment_data = create_platega_payment(total_amount, f"Пополнение баланса на {amount} руб.")
        if payment_data and 'payment_url' in payment_data:
            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_data['payment_url'])],
                [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_topup_{payment_data['payment_id']}")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"topup_{amount}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"**Оплата через СБП**\n\n"
                f"Сумма пополнения: {amount} руб.\n"
                f"Итого к оплате: {total_amount:.2f} руб.\n\n"
                f"1. Нажмите 'Перейти к оплате'\n"
                f"2. Совершите платеж\n"
                f"3. Вернитесь и нажмите 'Я оплатил'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при создании платежа. Попробуйте позже."
            )
    
    elif payment_method == "crypto":
        payment_data = create_crypto_payment(total_amount, f"Пополнение баланса на {amount} руб.")
        if payment_data and 'result' in payment_data and 'pay_url' in payment_data['result']:
            usdt_rate = payment_data.get('exchange_rate', get_usdt_rate())
            amount_usdt = total_amount / usdt_rate
            
            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_data['result']['pay_url'])],
                [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_topup_crypto_{payment_data['result']['invoice_id']}")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"topup_{amount}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"**Оплата через Crypto Bot**\n\n"
                f"Сумма пополнения: {amount} руб.\n"
                f"Итого к оплате: {total_amount:.2f} руб. ({amount_usdt:.6f} USDT)\n"
                f"📊 Курс: 1 USDT = {usdt_rate:.2f} RUB\n\n"
                f"1. Нажмите 'Перейти к оплате'\n"
                f"2. Совершите платеж\n"
                f"3. Вернитесь и нажмите 'Я оплатил'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при создании платежа. Попробуйте позже."
            )

# Показать категории
async def show_categories(query, context):
    categories = get_categories()
    
    if not categories:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📂 Категории товаров пусты.",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for category in categories:
        cat_id, name, created_at = category
        keyboard.append([
            InlineKeyboardButton(f"{name}", callback_data=f"category_{cat_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📂 **Категории товаров**\n\nВыберите категорию:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Показать товары в категории
async def show_products_in_category(query, context, category_id):
    category = get_category(category_id)
    if not category:
        await query.answer("Категория не найдена!")
        return
    
    cat_id, cat_name, created_at = category
    products = get_products(category_id)
    
    if not products:
        keyboard = [
            [InlineKeyboardButton("🔙 Назад к категориям", callback_data="shop_categories")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📦 В категории '{cat_name}' пока нет товаров.",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for product in products:
        product_id, name, description, price, product_type, cat_id, created_at, category_name = product
        keyboard.append([
            InlineKeyboardButton(
                f"{name} - {price} руб.", 
                callback_data=f"product_{product_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад к категориям", callback_data="shop_categories")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📦 **Товары в категории: {cat_name}**\n\nВыберите товар:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_product(query, context, product_id):
    product = get_product(product_id)
    if not product:
        await query.answer("Товар не найден!")
        return
    
    product_id, name, description, price, product_type, category_id, created_at, category_name = product
    
    keyboard = [
        [InlineKeyboardButton("💳 Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton("🔙 Назад к товарам", callback_data=f"category_{category_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    category_text = f"📂 Категория: {category_name}\n" if category_name else ""
    
    await query.edit_message_text(
        f"**{name}**\n\n"
        f"{category_text}"
        f"📝 Описание: {description}\n"
        f"💰 Цена: {price} руб.\n"
        f"📦 Тип: {product_type}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def choose_payment_method(query, context, product_id):
    product = get_product(product_id)
    if not product:
        await query.answer("Товар не найден!")
        return
    
    product_id, name, description, price, product_type, category_id, created_at, category_name = product
    total_amount = price + (price * 0.05)  # С комиссией 5%
    
    keyboard = [
        [InlineKeyboardButton("🇷🇺 СБП", callback_data=f"pay_{product_id}_sbp")],
        [InlineKeyboardButton("₿ Crypto Bot", callback_data=f"pay_{product_id}_crypto")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"product_{product_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"**Оплата: {name}**\n\n"
        f"💰 Цена товара: {price} руб.\n"
        f"💸 Комиссия (5%): {price * 0.05:.2f} руб.\n"
        f"💵 Итого к оплате: {total_amount:.2f} руб.\n\n"
        f"Выберите способ оплаты:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def process_payment(query, context, product_id, payment_method):
    product = get_product(product_id)
    if not product:
        await query.answer("Товар не найден!")
        return
    
    product_id, name, description, price, product_type, category_id, created_at, category_name = product
    total_amount = price + (price * 0.05)
    
    if payment_method == "sbp":
        payment_data = create_platega_payment(total_amount, f"Покупка: {name}")
        if payment_data and 'payment_url' in payment_data:
            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_data['payment_url'])],
                [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_payment_{payment_data['payment_id']}")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"buy_{product_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"**Оплата через СБП**\n\n"
                f"Товар: {name}\n"
                f"Сумма: {total_amount:.2f} руб.\n\n"
                f"1. Нажмите 'Перейти к оплате'\n"
                f"2. Совершите платеж\n"
                f"3. Вернитесь и нажмите 'Я оплатил'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при создании платежа. Попробуйте позже."
            )
    
    elif payment_method == "crypto":
        payment_data = create_crypto_payment(total_amount, f"Покупка: {name}")
        if payment_data and 'result' in payment_data and 'pay_url' in payment_data['result']:
            usdt_rate = payment_data.get('exchange_rate', get_usdt_rate())
            amount_usdt = total_amount / usdt_rate
            
            keyboard = [
                [InlineKeyboardButton("💳 Перейти к оплате", url=payment_data['result']['pay_url'])],
                [InlineKeyboardButton("✅ Я оплатил", callback_data=f"check_crypto_{payment_data['result']['invoice_id']}")],
                [InlineKeyboardButton("🔙 Назад", callback_data=f"buy_{product_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"**Оплата через Crypto Bot**\n\n"
                f"Товар: {name}\n"
                f"Сумма: {total_amount:.2f} руб. ({amount_usdt:.6f} USDT)\n"
                f"📊 Курс: 1 USDT = {usdt_rate:.2f} RUB\n\n"
                f"1. Нажмите 'Перейти к оплате'\n"
                f"2. Совершите платеж\n"
                f"3. Вернитесь и нажмите 'Я оплатил'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при создании платежа. Попробуйте позже."
            )

# Админ панель (остается без изменений)
async def admin_panel(query, context):
    if query.from_user.id != ADMIN_CHAT_ID:
        await query.answer("У вас нет доступа!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")],
        [InlineKeyboardButton("📂 Управление категориями", callback_data="admin_manage_categories")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👑 **Админ панель**\n\nВыберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Остальные функции админ панели остаются без изменений...
# [Здесь должен быть код админ панели из предыдущего сообщения]

async def help_callback(query, context):
    await query.edit_message_text(
        "🤖 **Помощь по боту**\n\n"
        "• Для просмотра товаров нажмите '🛍️ Магазин'\n"
        "• Выберите категорию и товар\n"
        "• Выберите способ оплаты\n"
        "• После оплаты вы получите доступ к товару\n\n"
        "Если возникли проблемы - свяжитесь с администратором."
    )

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(shop_categories|profile|help|admin_panel|admin_stats|admin_broadcast|admin_add_product|admin_manage_categories|admin_add_category|topup_balance|back_to_shop|back_to_admin|back_to_profile)"))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(topup_|topup_pay_|category_|product_|buy_|pay_|check_|admin_delete_category_).*"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
