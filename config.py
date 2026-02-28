"""Конфигурация: загрузка переменных окружения и инициализация клиентов."""

import os

from dotenv import load_dotenv
from gigachat import GigaChat
from openai import OpenAI

load_dotenv()

# Токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")
OPENAI_TOKEN = os.getenv("OPENAI_TOKEN")

# Клиенты LLM
giga_client = GigaChat(credentials=GIGACHAT_TOKEN, verify_ssl_certs=False)
openai_client = OpenAI(
    api_key=OPENAI_TOKEN,
    base_url="https://api.vsegpt.ru/v1",
)
