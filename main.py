"""Точка входа: регистрация хэндлеров и запуск бота."""

from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import TELEGRAM_TOKEN
from database import init_db
from game import start, stop, process_city_input
from handlers import handle_callback, handle_voice


def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            lambda u, c: process_city_input(u, c, u.message.text),
        )
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот запущен. Сменим нейронку?")
    app.run_polling()


if __name__ == "__main__":
    main()
