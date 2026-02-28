"""Обёртка для работы с LLM (GigaChat / OpenAI-совместимый роутер)."""

from config import giga_client, openai_client


async def ask_llm(game_state: dict, prompt: str) -> str:
    """Отправляет запрос в ту модель, которая выбрана в текущей игре."""
    model_type = game_state.get("model", "GigaChat")

    try:
        if model_type == "GigaChat":
            response = giga_client.chat(prompt)
            return response.choices[0].message.content.strip()
        else:
            response = openai_client.chat.completions.create(
                model="google/gemini-flash-1.5",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка LLM ({model_type}): {e}")
        return "Ошибка"
