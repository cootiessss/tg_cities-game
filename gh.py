import asyncio
import nest_asyncio
import speech_recognition as sr
import tempfile
import os
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from gigachat import GigaChat
from openai import OpenAI
from pydub import AudioSegment

# Разрешаем работу event loop в интерактивных средах
nest_asyncio.apply()
load_dotenv()

# Токены для доступа к API Telegram и GigaChat (загружаются из .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")
OPENAI_TOKEN= os.getenv("GIGACHAT_TOKEN")


# Инициализация клиентов
giga_client = GigaChat(credentials=GIGACHAT_TOKEN, verify_ssl_certs=False)
openai_client = OpenAI(
    api_key=OPENAI_TOKEN, # Твой ключ (sk-or-vv... или ключ от vsegpt)
    base_url="https://api.vsegpt.ru/v1",
)

# Словарь для хранения состояния игр
games = {}

# --- УНИВЕРСАЛЬНЫЙ МОЗГ (LLM WRAPPER) ---
async def ask_llm(game_state, prompt: str) -> str:
    """Отправляет запрос в ту модель, которая выбрана в текущей игре."""
    model_type = game_state.get('model', 'GigaChat')

    try:
        if model_type == 'GigaChat':
            response = giga_client.chat(prompt)
            return response.choices[0].message.content.strip()
        else:
            response = openai_client.chat.completions.create(
                model="google/gemini-flash-1.5",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка LLM ({model_type}): {e}")
        return "Ошибка"

# --- ОБРАБОТКА ГОЛОСА ---
async def convert_voice_to_text(voice_file) -> str:
    recognizer = sr.Recognizer()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_audio:
            await voice_file.download_to_drive(temp_audio.name)
            audio = AudioSegment.from_ogg(temp_audio.name)

            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)

            with sr.AudioFile(wav_io) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            return recognizer.recognize_google(audio_data, language='ru-RU')
    except Exception as e:
        print(f"Ошибка распознавания: {e}")
        return None
    finally:
        if 'temp_audio' in locals():
            os.unlink(temp_audio.name)

# --- ЛОГИКА ИГРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    games[chat_id] = {
        'model': 'GigaChat',
        'used': set(),
        'last_char': None,
        'last_bot_city': None
    }

    keyboard = [[
        InlineKeyboardButton("🤖 GigaChat", callback_data="set_model_GigaChat"),
        InlineKeyboardButton("🧠 OpenAI (Router)", callback_data="set_model_OpenAI")
    ]]

    await update.message.reply_text(
        "🌆 **Игра в города началась!**\n\nЯ буду твоим соперником. Выбери модель кнопкой ниже или просто напиши первый город.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def process_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_city: str):
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
        await update.message.reply_text(f"Город «{user_city}»? Звучит как выдумка. Назови настоящий!")
        return

    # Проверка правил
    if user_city.lower() in game['used']:
        await update.message.reply_text("Этот город уже был!")
        return
    if game['last_char'] and user_city[0].lower() != game['last_char']:
        await update.message.reply_text(f"Нужен город на букву **{game['last_char'].upper()}**!")
        return

    # Ход игрока принят
    game['used'].add(user_city.lower())
    for c in reversed(user_city.lower()):
        if c not in 'ьъы':
            game['last_char'] = c
            break

    # Ход бота
    bot_prompt = (f"Играем в города. Назови реальный город на букву '{game['last_char']}'. "
                  f"Уже были: {list(game['used'])[-15:]}. Ответь ТОЛЬКО названием.")

    bot_city = await ask_llm(game, bot_prompt)
    bot_city = bot_city.replace(".", "").strip().title()

    if bot_city.lower() in game['used'] or len(bot_city) > 40:
        await update.message.reply_text(f"Я не смог найти город на '{game['last_char'].upper()}'. Ты победил! 🏆")
        del games[chat_id]
        return

    game['used'].add(bot_city.lower())
    game['last_bot_city'] = bot_city
    for c in reversed(bot_city.lower()):
        if c not in 'ьъы':
            game['last_char'] = c
            break

    keyboard = [[InlineKeyboardButton(f"ℹ️ О городе {bot_city}", callback_data=f"info_{bot_city}")]]
    await update.message.reply_text(
        f"🤖 ({game['model']}): **{bot_city}**\nТвой ход на букву **{game['last_char'].upper()}**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- ОБРАБОТЧИКИ ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data.startswith("set_model_"):
        model = query.data.replace("set_model_", "")
        if chat_id in games:
            games[chat_id]['model'] = model
            await query.edit_message_text(f"✅ Готово! Теперь за игру отвечает **{model}**.")

    elif query.data.startswith("info_"):
        city = query.data[5:]
        if chat_id in games:
            prompt = f"Расскажи кратко о городе {city}, и саркастично удивись тому, что пользователь не знает такого места. Укажи страну и 1 факт. До 200 символов."
            info = await ask_llm(games[chat_id], prompt)
            await query.message.reply_text(f"🏙 **{city}**\n\n{info}", parse_mode="Markdown")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proc_msg = await update.message.reply_text("🎤 Слушаю внимательно...")
    voice_file = await update.message.voice.get_file()
    text = await convert_voice_to_text(voice_file)
    await proc_msg.delete()
    if text:
        await update.message.reply_text(f"🗣 Ты сказал: *{text}*", parse_mode="Markdown")
        await process_city_input(update, context, text)
    else:
        await update.message.reply_text("Не разобрал. Повтори громче?")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games: del games[chat_id]
    await update.message.reply_text("Игра окончена. Будет скучно — заходи!")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: process_city_input(u, c, u.message.text)))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот запущен. Сменим нейронку?")
    app.run_polling()

if __name__ == "__main__":
    main()