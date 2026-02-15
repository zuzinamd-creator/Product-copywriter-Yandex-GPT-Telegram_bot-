import requests
import json
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from langfuse import Langfuse

from src import TELEGRAM_TOKEN, IAM_TOKEN, MODEL_URI, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, ENDPOINT

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Langfuse
langfuse = Langfuse(
    public_key=LANGFUSE_PUBLIC_KEY,
    secret_key=LANGFUSE_SECRET_KEY,
    debug=True,
    sample_rate=1.0
)

# Заголовки для Yandex API
headers = {
    "Authorization": f"Bearer {IAM_TOKEN}",
    "Content-Type": "application/json",
}

# Функция вызова Yandex GPT
def call_yandex(payload):
    with langfuse.start_as_current_observation(as_type="span", name="yandex_call") as span:
        span.update(input={"payload": payload})
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        span.update(output={"response": result})
        return result

#Telegram Bot

# Словарь для хранения состояния каждого пользователя
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = {"stage": "waiting_for_name"}
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник, создающий продающие описания товаров. Для генерации описания отправь мне первым сообщением название товара."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in user_states:
        user_states[user_id] = {"stage": "waiting_for_name"}
        await update.message.reply_text("Пожалуйста, начнем сначала. Отправь название товара.")
        return

    stage = user_states[user_id].get("stage")

    if stage == "waiting_for_name":
        # Сохраняем название товара
        user_states[user_id]["name"] = user_text
        user_states[user_id]["stage"] = "waiting_for_info"
        await update.message.reply_text(
            "Отлично! Теперь отправь характеристики товара (описание, размеры, особенности и т.д.)."
        )
        return

    elif stage == "waiting_for_info":
        # Сохраняем характеристики и переходим к генерации описания
        user_states[user_id]["info"] = user_text
        await update.message.reply_text("⏳ Генерирую описание товара...")

        # ---------------- Payload для Yandex GPT ----------------
        system_prompt = """Роль модели: маркетолог и контент-редактор маркетплейсов (Ozon/Wildberries).
Задача: по заданному запросу пользователя разработать продающее описание товара.
Название товара: {product_name}
Характеристики товара: {product_info}
Требования к описанию:
- Название товара (четко выражает уникальность и полезность)
-Описание товара (5–7 предложений, подробно объясняющих функции, удобство использования и привлекательность товара для покупателя)
- Преимущества товара (не менее трех уникальных ценностей, направленных на удовлетворение нужд покупателей)
-Характеристики (таблица или список важных параметров)
-Ключевые слова для SEO (перечень поисковых запросов, которые используют потенциальные покупатели, чтобы найти этот товар)

Тон: позитивный, информативный, продающий, с упором на выгоду.
Максимальное количество символов: 1500.

Инструкция:
Выполни задачу в соответствии с подходом Chain-of-Verification:

Этап 1: Генерация базового ответа.

Этап 2: Верификация.
Чтобы проверить факты из базового ответа сгенерируй до 3 проверочных вопросов и ответь на каждый из них, сравнивая их с исходными данными о продукте. Вопросы должны касаться ключевых характеристик.
Примеры вопросов:
"Точно ли указанный объем емкости для воды 5 литров?"
"Упомянут ли метод естественного испарения в методах фильтрации?"

Этап 3: Создание финального ответа.
На основе результатов верификации отредактируй и улучши базовый ответ. 

Формат ответа:
1) Чеклист верификации 
2) Итог — структурированный вывод в формате:
**Название товара:** ...
**Описание (5–7 предложений):** ...
**Преимущества:**
- ...
- ...
- ...
**Характеристики:**
- параметр: значение
**SEO-ключевые слова:** ключ1, ключ2, ...

В ответе кратко покажи чеклист верификации и итог.
"""

        payload = {
            "modelUri": MODEL_URI,
            "completionOptions": {"stream": False, "temperature": 0.3, "maxTokens": 6000},
            "messages": [
                {"role": "system", "text": system_prompt.format(
                    product_name=user_states[user_id]["name"],
                    product_info=user_states[user_id]["info"]
                )},
                {"role": "user", "text": f"{user_states[user_id]['name']}: {user_states[user_id]['info']}"}
            ]
        }

        try:
            with langfuse.start_as_current_observation(as_type="span", name="yandex_bot_call") as span:
                span.update(input={"user_text": user_text})
                result = call_yandex(payload)
                span.update(output={"response": result})

            text = result["result"]["alternatives"][0]["message"]["text"] if result else "Нет ответа от модели."
            await update.message.reply_text(text)

        except Exception as e:
            logger.error(e)
            await update.message.reply_text("Ошибка при обработке запроса. Попробуйте позже.")

        # Сбрасываем состояние пользователя для нового запроса
        user_states[user_id]["stage"] = "waiting_for_name"
        return

    else:
        # Любой другой stage — сброс
        user_states[user_id]["stage"] = "waiting_for_name"
        await update.message.reply_text("Пожалуйста, отправь название товара, чтобы начать.")

# ---------------- Запуск бота ----------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()