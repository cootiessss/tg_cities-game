"""Обработчики Telegram: кнопки и голосовые сообщения."""

from telegram import Update
from telegram.ext import ContextTypes

from state import games
from llm import ask_llm
from voice import convert_voice_to_text
from game import process_city_input


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на инлайн-кнопки (выбор модели, инфо о городе)."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data.startswith("set_model_"):
        model = query.data.replace("set_model_", "")
        if chat_id in games:
            games[chat_id]["model"] = model
            await query.edit_message_text(f"✅ Готово! Теперь за игру отвечает **{model}**.")

    elif query.data.startswith("info_"):
        city = query.data[5:]
        if chat_id in games:
            prompt = (
                f"Расскажи кратко о городе {city}, и саркастично удивись тому, "
                f"что пользователь не знает такого места. Укажи страну и 1 факт. До 200 символов."
            )
            info = await ask_llm(games[chat_id], prompt)
            await query.message.reply_text(f"🏙 **{city}**\n\n{info}", parse_mode="Markdown")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосового сообщения: распознавание → ход в игре."""
    proc_msg = await update.message.reply_text("🎤 Слушаю внимательно...")
    voice_file = await update.message.voice.get_file()
    text = await convert_voice_to_text(voice_file)
    await proc_msg.delete()

    if text:
        await update.message.reply_text(f"🗣 Ты сказал: *{text}*", parse_mode="Markdown")
        await process_city_input(update, context, text)
    else:
        await update.message.reply_text("Не разобрал. Повтори громче?")
