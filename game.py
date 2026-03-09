"""Основная логика игры в города."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from state import games
from llm import ask_llm
from database import log_request


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало новой игры: создаёт состояние и предлагает выбрать модель."""
    chat_id = update.effective_chat.id
    games[chat_id] = {
        "model": "GigaChat",
        "used": set(),
        "last_char": None,
        "last_bot_city": None,
    }

    keyboard = [
        [
            InlineKeyboardButton("🤖 GigaChat", callback_data="set_model_GigaChat"),
            InlineKeyboardButton("🧠 OpenAI (Router)", callback_data="set_model_OpenAI"),
        ]
    ]

    await update.message.reply_text(
        "🌆 **Игра в города началась!**\n\n"
        "Я буду твоим соперником. Выбери модель кнопкой ниже или просто напиши первый город.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def process_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_city: str):
    """Обрабатывает ход игрока: проверяет город и делает ответный ход."""
    chat_id = update.effective_chat.id
    user_city = user_city.strip().title()

    if chat_id not in games:
        await update.message.reply_text("Нажми /start, чтобы начать игру.")
        return

    game = games[chat_id]

    # Проверка на существование города
    check_prompt = f'Является ли "{user_city}" реально существующим названием города? Ответь ТОЛЬКО "да" или "нет".'
    is_real = await ask_llm(game, check_prompt)
    if "да" not in is_real.lower():
        log_request(req=user_city, resp=f"Город «{user_city}»? Звучит как выдумка. Назови настоящий!", llm=game["model"])
        await update.message.reply_text(f"Город «{user_city}»? Звучит как выдумка. Назови настоящий!")
        return

    # Проверка правил
    if user_city.lower() in game["used"]:
        log_request(req=user_city, resp="Этот город уже был!", llm=game["model"])
        await update.message.reply_text("Этот город уже был!")
        return
    if game["last_char"] and user_city[0].lower() != game["last_char"]:
        log_request(req=user_city, resp=f"Нужен город на букву {game['last_char'].upper()}!", llm=game["model"])
        await update.message.reply_text(f"Нужен город на букву **{game['last_char'].upper()}**!")
        return

    # Ход игрока принят
    game["used"].add(user_city.lower())
    for c in reversed(user_city.lower()):
        if c not in "ьъы":
            game["last_char"] = c
            break

    # Ход бота
    bot_prompt = (
        f"Играем в города. Назови реальный город на букву '{game['last_char']}'. "
        f"Уже были: {list(game['used'])[-15:]}. Ответь ТОЛЬКО названием."
    )

    bot_city = await ask_llm(game, bot_prompt)
    bot_city = bot_city.replace(".", "").strip().title()

    if bot_city.lower() in game["used"] or len(bot_city) > 40:
        await update.message.reply_text(
            f"Я не смог найти город на '{game['last_char'].upper()}'. Ты победил! 🏆"
        )
        del games[chat_id]
        return

    game["used"].add(bot_city.lower())
    game["last_bot_city"] = bot_city
    log_request(req=user_city, resp=bot_city, llm=game["model"])
    for c in reversed(bot_city.lower()):
        if c not in "ьъы":
            game["last_char"] = c
            break

    keyboard = [[InlineKeyboardButton(f"ℹ️ О городе {bot_city}", callback_data=f"info_{bot_city}")]]
    await update.message.reply_text(
        f"🤖 ({game['model']}): **{bot_city}**\nТвой ход на букву **{game['last_char'].upper()}**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение игры."""
    chat_id = update.effective_chat.id
    if chat_id in games:
        del games[chat_id]
    await update.message.reply_text("Игра окончена. Будет скучно — заходи!")
