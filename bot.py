import os
import re
import json
import asyncio
import aiohttp
from datetime import datetime
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === КОНФИГ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN обязателен")
if not SESSION_STRING:
    raise ValueError("SESSION_STRING обязательна")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# ============================================================
# 1. ПОЛУЧЕНИЕ ИНФОРМАЦИИ
# ============================================================
async def get_user_info(username: str):
    try:
        if re.match(r'^\d+$', username):
            entity = await client.get_entity(int(username))
        else:
            entity = await client.get_entity(username)

        full = await client(functions.users.GetFullUserRequest(entity))
        user = full.full_user
        photos = await client.get_profile_photos(entity, limit=1)

        registered = None
        try:
            if hasattr(user, 'date'):
                registered = user.date.strftime("%d.%m.%Y")
            else:
                registered = "неизвестно"
        except:
            registered = "неизвестно"

        last_seen = None
        if entity.status and hasattr(entity.status, 'was_online'):
            last_seen = entity.status.was_online.strftime("%d.%m.%Y %H:%M")

        return {
            "id": entity.id,
            "username": entity.username,
            "first_name": entity.first_name,
            "last_name": entity.last_name or "",
            "bio": getattr(user, "about", None),
            "premium": getattr(user, "premium", False),
            "verified": getattr(entity, 'verified', False),
            "restricted": getattr(entity, 'restricted', False),
            "lang_code": getattr(entity, 'lang_code', None),
            "dc_id": getattr(entity.photo, "dc_id", None) if entity.photo else None,
            "avatar_url": f"https://t.me/i/userpic/320/{entity.id}.jpg" if photos else None,
            "registered": registered,
            "status": "онлайн" if entity.status and hasattr(entity.status, 'was_online') else "не в сети",
            "last_seen": last_seen,
            "photos_count": photos.total if photos else 0
        }
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# 2. ПРОВЕРКА В БАЗЕ МОШЕННИКОВ
# ============================================================
async def check_scam_base(username: str):
    results = []
    try:
        entity = await client.get_entity("GID_ScamBase")
        async for msg in client.iter_messages(entity, search=username, limit=5):
            if msg.text and username in msg.text:
                results.append({
                    "source": "GID_ScamBase",
                    "link": f"https://t.me/GID_ScamBase/{msg.id}",
                    "text": msg.text[:200]
                })
    except:
        pass
    return results

# ============================================================
# 3. HTTP-СЕРВЕР
# ============================================================
async def start_http():
    from aiohttp import web
    async def index(request):
        return web.FileResponse('index.html')
    app_web = web.Application()
    app_web.router.add_get('/', index)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=PORT)
    await site.start()
    print(f"✅ Mini App доступен на порту {PORT}")
    await asyncio.Event().wait()

# ============================================================
# 4. КОМАНДЫ БОТА
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost")
    url = f"https://{hostname}" if hostname != "localhost" else f"http://localhost:{PORT}"
    keyboard = [
        [InlineKeyboardButton("🔍 Открыть Spectra", web_app=WebAppInfo(url=url))]
    ]
    await update.message.reply_text(
        "Нажми кнопку, чтобы открыть интерфейс поиска:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = json.loads(update.message.web_app_data.data)
        username = data.get("username", "").strip()
        if not username:
            await update.message.reply_text("❌ Введите username")
            return

        username = username.replace("@", "")
        await update.message.reply_text(f"🔍 Собираю данные по @{username}...")

        info = await get_user_info(username)
        if "error" in info:
            await update.message.reply_text(f"❌ {info['error']}")
            return

        scam_results = await check_scam_base(username)

        if info.get('avatar_url'):
            await update.message.reply_photo(info['avatar_url'], caption=f"Аватар @{username}")

        report = f"✈️ *Telegram* · @{username}\n"
        report += f"├ Имя: {info.get('first_name', '?')}\n"
        report += f"├ ID: {info.get('id', '?')}\n"
        report += f"├ Юзернейм: @{info.get('username', '?')}\n"
        report += f"├ Статус: {'Premium ✨' if info.get('premium') else 'обычный'}\n"
        report += f"├ Верифицирован: {'✅ Да' if info.get('verified') else '❌ Нет'}\n"
        report += f"├ Ограничен: {'⚠️ Да' if info.get('restricted') else '✅ Нет'}\n"
        if info.get('lang_code'):
            report += f"├ Язык: {info.get('lang_code')}\n"
        report += f"├ Регистрация: {info.get('registered', 'неизвестно')}\n"
        if info.get('bio'):
            report += f"├ Био: {info['bio']}\n"
        report += f"├ Статус онлайн: {info.get('status', 'неизвестно')}\n"
        if info.get('last_seen'):
            report += f"├ Последняя активность: {info['last_seen']}\n"
        report += f"├ Дата-центр: DC {info.get('dc_id', '?')}\n"
        report += f"├ Фото в профиле: {info.get('photos_count', 0)}\n"
        report += f"└ Ссылка: https://t.me/{username}\n\n"

        if scam_results:
            report += f"⚠️ *Найден в базе мошенников!*\n"
            for scam in scam_results:
                report += f"├ Источник: {scam['source']}\n"
                report += f"├ [Ссылка на пост]({scam['link']})\n"
                report += f"└ {scam['text'][:100]}...\n\n"
        else:
            report += f"✅ *Не найден в базе мошенников*\n\n"

        await update.message.reply_text(report, parse_mode="Markdown")

    except json.JSONDecodeError:
        await update.message.reply_text("❌ Ошибка обработки данных")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ============================================================
# 5. ЗАПУСК (исправленный)
# ============================================================
def main():
    # Запускаем HTTP-сервер в отдельном потоке
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(start_http())

    # Запускаем бота синхронно
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data))

    print("✅ Бот запущен. /start")
    app.run_polling()

if __name__ == "__main__":
    main()
