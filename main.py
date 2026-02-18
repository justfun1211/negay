import asyncio
import logging
import re
import sys
from os import getenv

# Библиотеки для Telegram бота (aiogram 3.x)
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode # Исправленный импорт

# Библиотеки для запросов и парсинга
import aiohttp
from bs4 import BeautifulSoup

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================

# ВСТАВЬ СЮДА СВОЙ ТОКЕН!
API_TOKEN = tpl_token_placeholder = "8129474637:AAFiEIxXMVpQt_xC_LNjcY2Vd944Ev4SlWU" 

# Курсы валют (ручная настройка - примерные значения)
USD_TO_RUB = 93.5  # 1 доллар в рублях
USD_TO_KZT = 455.0 # 1 доллар в тенге
EUR_TO_RUB = 101.0 # 1 евро в рублях
EUR_TO_KZT = 495.0 # 1 евро в тенге

# Ссылка на Steam (США регион, чтобы цены были в долларах для удобства конвертации)
STEAM_URL = "https://store.steampowered.com/search/?filter=topsellers&os=win&cc=us" 
# Используем страницу поиска топ-продаж, она стабильнее парсится

# Логирование (чтобы видеть ошибки в консоли)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# ==========================================
# ЛОГИКА КОНВЕРТАЦИИ ВАЛЮТ
# ==========================================

def get_price_numbers(price_str):
    """
    Пытается извлечь цену из строки.
    Возвращает число (float) или None.
    """
    if not price_str or "free" in price_str.lower():
        return 0.0
        
    # Ищем цену вида $19.99 или $1,999.00
    try:
        # Сначала убираем запятые (разделители тысяч)
        clean_str = price_str.replace(',', '')
        # Убираем все кроме цифр и точки
        clean_str = re.sub(r'[^\d\.]', '', clean_str)
        return float(clean_str)
    except ValueError:
        return None

def convert_price_data(price_str):
    """
    Принимает строку цены.
    Возвращает словарь с форматированными ценами.
    """
    if not price_str:
        return None

    price_str = price_str.strip()
    
    if "free" in price_str.lower() or "play for free" in price_str.lower():
         return {
            "original": "Free to Play",
            "rub": 0,
            "kzt": 0,
            "is_free": True
        }

    original_val = get_price_numbers(price_str)
    
    # Если парсер вернул 0.0, но это не Free - значит что-то пошло не так или цена реально 0
    if original_val is None:
        return None

    # По умолчанию считаем, что цена в долларах
    
    rub_price = int(original_val * USD_TO_RUB)
    kzt_price = int(original_val * USD_TO_KZT)

    return {
        "original": f"${original_val:,.2f}",
        "rub": rub_price,
        "kzt": kzt_price,
        "is_free": False
    }

# ==========================================
# ПАРСИНГ STEAM
# ==========================================

async def get_steam_games():
    """
    Парсит страницу поиска Steam (Топ продаж).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "birthtime=568022401; lastagecheckage=1-January-1988" # Обход проверки возраста
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(STEAM_URL, headers=headers) as response:
                if response.status != 200:
                    logging.error(f"Ошибка Steam: {response.status}")
                    return []
                html = await response.text()
        except Exception as e:
            logging.error(f"Ошибка сети: {e}")
            return []

    soup = BeautifulSoup(html, "html.parser")
    games = []
    
    # Ищем строки результатов поиска
    # Увеличиваем лимит игр
    items = soup.find_all("a", class_="search_result_row", limit=15)

    for item in items:
        try:
            # 1. Название
            title_span = item.find("span", class_="title")
            title = title_span.get_text(strip=True) if title_span else "Без названия"

            # Фильтр: убираем Steam Deck (оборудование)
            if "Steam Deck" in title:
                continue

            # 2. Ссылка
            game_url = item.get("href", "")

            # 3. Картинка (берем из атрибута src или srcset у img)
            img_tag = item.find("img")
            img_url = img_tag.get("src") if img_tag else None
            
            # Лайфхак: получаем картинку лучшего качества
            if img_url:
                app_id_match = re.search(r'/apps/(\d+)/', img_url)
                if app_id_match:
                    app_id = app_id_match.group(1)
                    img_url = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"

            # 4. Цена
            # Исправленный селектор: .discount_final_price содержит конечную цену (например "$45.49" или "Free")
            price_div = item.select_one(".discount_final_price")
            if not price_div:
                 # Fallback на случай другой верстки
                 price_div = item.select_one(".search_price")

            price_str = ""
            if price_div:
                # Получаем текст (например "$45.49" или "Free")
                full_text = price_div.get_text(strip=True)
                
                if "Free" in full_text:
                    price_str = "Free"
                else:
                    # Чистим цену от лишних символов, если они есть
                    # Но обычно в discount_final_price уже лежит готовая цена
                    parts = re.findall(r'\$[\d\.,]+', full_text)
                    if parts:
                        price_str = parts[-1] 
                    else:
                        price_str = full_text
            else:
                logging.warning(f"Цена не найдена для {title}")

            # Данные о цене
            price_data = convert_price_data(price_str)
            
            # Если не удалось спарсить цену, всё равно добавим игру, но пометим как не удалось
            
            games.append({
                "title": title,
                "url": game_url,
                "img": img_url,
                "price_data": price_data
            })

        except Exception as e:
            logging.error(f"Ошибка элемента: {e}")
            continue

    return games

# ==========================================
# TELEGRAM BOT
# ==========================================

# Создаем бота (экземпляр будет создан в main, чтобы проверить токен)
dp = Dispatcher()

# Клавиатура
kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔥 Показать новинки")]],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я ищу топ продаж в Steam.\nЖми кнопку!", 
        reply_markup=kb
    )

@dp.message(F.text == "🔥 Показать новинки")
@dp.message(Command("hot"))
async def cmd_hot(message: types.Message):
    # Отправляем "печатает..."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    games = await get_steam_games()

    if not games:
        await message.answer("😔 Ничего не нашел или Steam не отвечает.")
        return

    for game in games:
        # Формируем описание цены
        price_text = "Неизвестно"
        if game['price_data']:
            pd = game['price_data']
            if pd['is_free']:
                price_text = "🆓 Бесплатно"
            else:
                price_text = (
                    f"💲 <b>{pd['original']}</b>\n"
                    f"🇷🇺 ~{pd['rub']} ₽\n"
                    f"🇰🇿 ~{pd['kzt']} ₸"
                )
        
        caption = (
            f"🎮 <b>{game['title']}</b>\n\n"
            f"{price_text}\n\n"
            f"🔗 <a href='{game['url']}'>Открыть в Steam</a>"
        )

        try:
            if game['img']:
                await message.answer_photo(game['img'], caption=caption)
            else:
                await message.answer(caption, disable_web_page_preview=False)
        except Exception as e:
            logging.error(f"Ошибка отправки: {e}")
            # Если сломалось фото, шлем текст
            await message.answer(caption)
            
        await asyncio.sleep(0.5)

async def main():
    # Проверка токена
    if API_TOKEN == "ТВОЙ_ТОКЕН_ЗДЕСЬ":
        print("\n!!! ОШИБКА !!!")
        print("Открой файл main.py и вставь токен бота в 23-ю строку!")
        print("API_TOKEN = \"...\"\n")
        return

    # Создаем объект бота внутри main
    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    print("Бот запускается...")
    # Удаляем вебхуки, если были, и начинаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
             # Исправление для Windows (ProactorEventLoop)
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен.")
