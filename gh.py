from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from gigachat import GigaChat
import asyncio
import nest_asyncio
import speech_recognition as sr
import tempfile
import os
from pydub import AudioSegment
import io

# Применяем nest_asyncio для работы в средах типа Jupyter/Colab, где уже есть запущенный event loop
# Это позволяет избежать ошибки "RuntimeError: This event loop is already running"
nest_asyncio.apply()

from dotenv import load_dotenv

load_dotenv()

# Токены для доступа к API Telegram и GigaChat (загружаются из .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")

if not TELEGRAM_TOKEN or not GIGACHAT_TOKEN:
    raise ValueError("Необходимо задать TELEGRAM_TOKEN и GIGACHAT_TOKEN в файле .env")

# Словарь для хранения состояния активных игр
# Ключ: ID чата (int), Значение: словарь с данными игры
games = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем уникальный идентификатор чата
    chat_id = update.effective_chat.id

    # Создаем новую игру для этого чата
    games[chat_id] = {
        'giga': GigaChat(credentials=GIGACHAT_TOKEN, verify_ssl_certs=False),  # Клиент GigaChat для проверки городов
        'used': set(),  # Множество уже использованных названий городов (в нижнем регистре)
        'last_char': None,  # Последняя буква, на которую должен начинаться следующий город
        'last_bot_city': None  # Последний город, названный ботом
    }

    # Отправляем приветственное сообщение
    await update.message.reply_text("Игра в города! Назови первый город:")

async def is_real_city(city: str, giga_client) -> bool:
    prompt = f"""Является ли "{city}" реально существующим названием города?
Ответь ТОЛЬКО "да" или "нет" без пояснений."""

    try:
        # Отправляем запрос к GigaChat
        response = giga_client.chat(prompt)
        # Извлекаем ответ из первого выбора
        answer = response.choices[0].message.content.strip().lower()
        # Возвращаем True если в ответе есть "да"
        return "да" in answer
    except Exception as e:
        # В случае ошибки API считаем город валидным, чтобы не прерывать игру
        print(f"Ошибка при проверке города: {e}")
        return True

async def get_city_info(city: str, giga_client) -> str:
    """
    Получает информацию о городе от GigaChat
    """
    prompt = f"""Расскажи кратко о городе {city}, и усомнись в умственных способностях пользователя, саркастично удивись тому, что пользователь не знает такого города.
Укажи:
- Страну и регион
- Население (примерно)
- 1-2 интересных факта
- Чем известен город

Ответ должен быть кратким, но информативным, не более 200 символов."""

    try:
        response = giga_client.chat(prompt)
        info = response.choices[0].message.content.strip()
        return info
    except Exception as e:
        print(f"Ошибка при получении информации о городе: {e}")
        return "Не удалось получить информацию о городе."

async def convert_voice_to_text(voice_file) -> str:
    """
    Конвертирует голосовое сообщение в текст с помощью speech_recognition
    """
    recognizer = sr.Recognizer()

    try:
        # Создаем временный файл для обработки аудио
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_audio:
            # Скачиваем голосовое сообщение во временный файл
            await voice_file.download_to_drive(temp_audio.name)

            # Конвертируем OGG в WAV с помощью pydub
            audio = AudioSegment.from_ogg(temp_audio.name)

            # Создаем временный WAV файл в памяти
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)

            # Используем распознавание с WAV файлом из памяти
            with sr.AudioFile(wav_io) as source:
                # Учитываем фоновый шум для лучшего распознавания
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            # Распознаем речь с помощью Google Speech Recognition
            text = recognizer.recognize_google(audio_data, language='ru-RU')
            return text

    except sr.UnknownValueError:
        return None  # Не удалось распознать речь
    except sr.RequestError as e:
        print(f"Ошибка сервиса распознавания речи: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при обработке аудио: {e}")
        return None
    finally:
        # Удаляем временный файл
        if 'temp_audio' in locals():
            try:
                os.unlink(temp_audio.name)
            except:
                pass

async def process_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_city: str):
    """
    Обрабатывает введенный город (текстовый или преобразованный из голоса)
    """
    # Получаем ID чата и введенный город
    chat_id = update.effective_chat.id
    user_city = user_city.strip().title()

    # Проверяем, активна ли игра в этом чате
    if chat_id not in games:
        await update.message.reply_text("Введите /start чтобы начать")
        return

    # Получаем данные текущей игры
    game = games[chat_id]

    # Обработка команд остановки игры
    if user_city.lower() in ['/stop', '/стоп']:
        del games[chat_id]
        await update.message.reply_text("Игра завершена!")
        return

    # Проверка: является ли введенное слово реальным городом
    if not await is_real_city(user_city, game['giga']):
        await update.message.reply_text("Это не реальный город! Назови существующий город.")
        return

    # Проверка: не был ли этот город уже использован в игре
    if user_city.lower() in game['used']:
        await update.message.reply_text("Этот город уже был!")
        return

    # Проверка: начинается ли город на правильную букву (если это не первый ход)
    if game['last_char'] and user_city[0].lower() != game['last_char']:
        await update.message.reply_text(f"Нужен город на букву '{game['last_char'].upper()}'!")
        return

    # Ход игрока признан валидным - добавляем город в использованные
    game['used'].add(user_city.lower())

    # Определяем последнюю букву для следующего хода
    # Пропускаем буквы 'ь', 'ъ', 'ы' так как по правилам игры они не используются
    for c in reversed(user_city.lower()):
        if c not in 'ьъы':
            game['last_char'] = c
            break

    # Ход бота (GigaChat)
    # Собираем список уже использованных городов на нужную букву для подсказки AI
    cities_on_letter = [city for city in game['used'] if city[0] == game['last_char']]

    # Формируем промпт для GigaChat с правилами игры
    prompt = f"""Играем в города. Назови реальный город на букву '{game['last_char']}'.
    Уже использованы города на эту букву: {cities_on_letter[-10:]}.
    Ответь ТОЛЬКО названием города без пояснений."""
    print(prompt)  # Логируем промпт для отладки

    try:
        # Отправляем запрос к GigaChat для получения хода бота
        response = game['giga'].chat(prompt)
        bot_city = response.choices[0].message.content.strip()

        # Очищаем ответ от возможных лишних символов и форматирования
        bot_city = bot_city.split('\n')[0].split('.')[0].strip()

        # Проверяем, не был ли город бота уже использован
        if bot_city.lower() in game['used']:
            await update.message.reply_text(f"Ты выиграл! Я сдаюсь на букву '{game['last_char'].upper()}'")
            del games[chat_id]  # Завершаем игру
            return

        # Добавляем город бота в использованные
        game['used'].add(bot_city.lower())

        # Сохраняем последний город бота для возможности получения информации
        game['last_bot_city'] = bot_city

        # Определяем последнюю букву города бота для следующего хода игрока
        for c in reversed(bot_city.lower()):
            if c not in 'ьъы':
                game['last_char'] = c
                break

        # Создаем клавиатуру с кнопкой для получения информации о городе
        keyboard = [
            [InlineKeyboardButton(f"ℹ️ Узнать о городе {bot_city}", callback_data=f"info_{bot_city}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем ответ бота и информацию о следующей букве с кнопкой
        await update.message.reply_text(
            f"{bot_city}\nТвой ход на букву '{game['last_char'].upper()}'",
            reply_markup=reply_markup
        )

    except Exception as e:
        # Обработка ошибок при запросе к GigaChat
        print(f"Ошибка GigaChat: {e}")
        await update.message.reply_text("Ошибка при запросе к GigaChat. Попробуйте еще раз.")

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик нажатий на inline-кнопки
    """
    query = update.callback_query
    await query.answer()

    # Извлекаем данные из callback_data
    callback_data = query.data

    if callback_data.startswith('info_'):
        city_name = callback_data[5:]  # Извлекаем название города после 'info_'
        chat_id = query.message.chat_id

        if chat_id in games:
            game = games[chat_id]

            # Отправляем сообщение о загрузке информации
            await query.edit_message_text(text=f"🔄 Загружаю информацию о {city_name}...")

            # Получаем информацию о городе
            city_info = await get_city_info(city_name, game['giga'])

            # Отправляем информацию о городе
            await query.edit_message_text(
                text=f"🏙️ **{city_name}**\n\n{city_info}\n\nТвой ход на букву '{game['last_char'].upper()}'"
            )
        else:
            await query.edit_message_text(text="Игра не активна. Введите /start чтобы начать.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик текстовых сообщений
    """
    user_city = update.message.text
    await process_city_input(update, context, user_city)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик голосовых сообщений
    """
    voice_message = update.message.voice

    # Отправляем сообщение о том, что обрабатываем голосовое сообщение
    processing_message = await update.message.reply_text("🔊 Обрабатываю голосовое сообщение...")

    try:
        # Получаем файл голосового сообщения
        voice_file = await voice_message.get_file()

        # Конвертируем голос в текст
        recognized_text = await convert_voice_to_text(voice_file)

        if recognized_text:
            # Удаляем сообщение о обработке
            await processing_message.delete()

            # Отправляем распознанный текст для подтверждения
            await update.message.reply_text(f"🎤 Распознано: {recognized_text}")

            # Обрабатываем распознанный город
            await process_city_input(update, context, recognized_text)
        else:
            await processing_message.edit_text("❌ Не удалось распознать речь. Попробуйте сказать четче или напишите город текстом.")

    except Exception as e:
        print(f"Ошибка при обработке голосового сообщения: {e}")
        await processing_message.edit_text("❌ Ошибка при обработке голосового сообщения. Попробуйте еще раз или напишите город текстом.")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /info - показывает информацию о последнем городе бота
    """
    chat_id = update.effective_chat.id

    if chat_id in games:
        game = games[chat_id]

        if game['last_bot_city']:
            # Получаем информацию о последнем городе бота
            city_info = await get_city_info(game['last_bot_city'], game['giga'])
            await update.message.reply_text(f"🏙️ **{game['last_bot_city']}**\n\n{city_info}")
        else:
            await update.message.reply_text("Бот еще не назвал ни одного города.")
    else:
        await update.message.reply_text("Игра не активна. Введите /start чтобы начать.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /stop - принудительно завершает игру
    """
    chat_id = update.effective_chat.id
    if chat_id in games:
        del games[chat_id]  # Удаляем игру из активных
    await update.message.reply_text("Игра завершена!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /status - показывает текущее состояние игры
    """
    chat_id = update.effective_chat.id
    if chat_id in games:
        game = games[chat_id]
        # Формируем информационное сообщение о статусе игры
        status_text = f"Статус игры:\n"
        status_text += f"Использовано городов: {len(game['used'])}\n"
        if game['last_char']:
            status_text += f"Следующая буква: '{game['last_char'].upper()}'\n"
        if game['last_bot_city']:
            status_text += f"Последний город бота: {game['last_bot_city']}\n"
        if game['used']:
            # Показываем последние 3 использованных города
            status_text += f"Последние города: {', '.join(list(game['used'])[-3:])}"
        await update.message.reply_text(status_text)
    else:
        await update.message.reply_text("Игра не активна. Введите /start чтобы начать")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("info", info_command))

    # Регистрируем обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Регистрируем обработчик голосовых сообщений
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Регистрируем обработчик нажатий на inline-кнопки
    app.add_handler(CallbackQueryHandler(handle_button_click))

    # Запускаем бота в режиме polling (постоянный опрос серверов Telegram)
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()