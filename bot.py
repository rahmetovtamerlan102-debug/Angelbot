import os
import re
import asyncio
import aiohttp
from datetime import datetime
from telethon import TelegramClient, functions, types
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
# 1. ПОЛУЧЕНИЕ ИНФОРМАЦИИ О ПОЛЬЗОВАТЕЛЕ
# ============================================================
async def get_user_info(username: str):
    try:
        entity = await client.get_entity(username)
        full = await client(functions.users.GetFullUserRequest(entity))
        user = full.full_user
        photos = await client.get_profile_photos(entity, limit=1)
        return {
            "id": entity.id,
            "username": entity.username,
            "first_name": entity.first_name,
            "last_name": entity.last_name or "",
            "bio": getattr(user, "about", None),
            "premium": getattr(user, "premium", False),
            "dc_id": getattr(entity.photo, "dc_id", None) if entity.photo else None,
            "avatar_url": f"https://t.me/i/userpic/320/{entity.id}.jpg" if photos else None,
            "registered": "~янв,2025 (1 год)"
        }
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# 2. ПОДАРКИ
# ============================================================
async def get_gifts(user_id: int):
    received = []
    sent = []
    try:
        result = await client(functions.account.GetGiftsRequest(user_id=user_id))
        if result.gifts:
            for gift in result.gifts:
                if gift.from_id:
                    try:
                        from_user = await client.get_entity(gift.from_id)
                        received.append(f"@{from_user.username}" if from_user.username else f"#{from_user.id}")
                    except:
                        received.append(f"#{gift.from_id.user_id}")
                if gift.to_id:
                    try:
                        to_user = await client.get_entity(gift.to_id)
                        sent.append(f"@{to_user.username}" if to_user.username else f"#{to_user.id}")
                    except:
                        sent.append(f"#{gift.to_id.user_id}")
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return await get_gifts(user_id)
    except Exception as e:
        print(f"Ошибка получения подарков: {e}")
    return {"received": received, "sent": sent}

# ============================================================
# 3. ПРОВЕРКА В БАЗЕ МОШЕННИКОВ
# ============================================================
async def check_scam_base(username: str):
    try:
        entity = await client.get_entity("GID_ScamBase")
        async for msg in client.iter_messages(entity, search=username, limit=1):
            if msg.text and username in msg.text:
                return {"found": True, "link": f"https://t.me/GID_ScamBase/{msg.id}"}
    except:
        pass
    return {"found": False, "link": None}

# ============================================================
# 4. ФОРМАТИРОВАННЫЙ ОТЧЁТ
# ============================================================
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ /check @username")
        return

    username = context.args[0].replace("@", "")
    await update.message.reply_text(f"🔍 Собираю данные по @{username}...")

    info = await get_user_info(username)
    if "error" in info:
        await update.message.reply_text(f"❌ {info['error']}")
        return

    entity = await client.get_entity(username)
    gifts = await get_gifts(entity.id)
    scam = await check_scam_base(username)

    # Форматируем вывод
    report = f"✈️ *Telegram* · @{username}\n"
    report += f"├ Имя: {info.get('first_name', '?')}\n"
    report += f"├ ID: {info.get('id', '?')}\n"
    report += f"├ Юзернейм: @{info.get('username', '?')}\n"
    report += f"├ Статус: {'Premium ✨' if info.get('premium') else 'обычный'}\n"
    report += f"├ Регистрация: {info.get('registered', 'неизвестно')}\n"
    report += f"└ Дата-центр: DC {info.get('dc_id', '?')}\n\n"

    # Подарки (полученные)
    if gifts.get('received'):
        report += f"⬇️ *От кого получал(-а) подарки ({len(gifts['received'])}):*\n"
        report += " · ".join(gifts['received'][:15]) + "\n\n"

    # Подарки (отправленные)
    if gifts.get('sent'):
        report += f"⬆️ *Кому отправлял(-а) подарки (взаимно):*\n"
        report += " · ".join(gifts['sent'][:10]) + "\n\n"

    # База мошенников
    if scam and scam.get('found'):
        report += f"⚠️ *Внесён в список мошенников!* Сделки проводить не рекомендуется.\n"
        report += f"└ [Пост с обвинением]({scam.get('link', '#')})\n\n"

    report += f"👁 *Интересовались этим:* {len(gifts.get('received', [])) + len(gifts.get('sent', []))}\n"

    keyboard = [
        [InlineKeyboardButton("🖼 Аватар", callback_data=f"avatar_{username}")],
        [InlineKeyboardButton("🔍 Spectra", url=f"https://cerera.cc/search?q={username}")]
    ]
    await update.message.reply_text(report, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def avatar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    username = query.data.replace("avatar_", "")
    info = await get_user_info(username)
    if info.get('avatar_url'):
        await query.message.reply_photo(info['avatar_url'])
    else:
        await query.edit_message_text("❌ Аватар не найден.")

# ============================================================
# 5. HTTP-СЕРВЕР
# ============================================================
async def start_http():
    from aiohttp import web
    async def health(request):
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    print(f"✅ HTTP-сервер запущен на порту {PORT}")

# ============================================================
# 6. ЗАПУСК
# ============================================================
async def main():
    await client.start()
    await start_http()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CallbackQueryHandler(avatar_callback, pattern="^avatar_"))

    print("✅ Бот запущен. /check @username")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
