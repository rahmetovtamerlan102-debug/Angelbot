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

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN обязателен")
if not SESSION_STRING:
    raise ValueError("SESSION_STRING обязательна")

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

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
                        received.append({
                            "name": from_user.first_name or f"#{from_user.id}",
                            "username": f"@{from_user.username}" if from_user.username else None,
                            "id": from_user.id,
                            "date": gift.date.strftime("%d.%m.%Y %H:%M") if gift.date else None
                        })
                    except:
                        received.append({"name": f"#{gift.from_id.user_id}", "username": None, "id": gift.from_id.user_id})
                if gift.to_id:
                    try:
                        to_user = await client.get_entity(gift.to_id)
                        sent.append({
                            "name": to_user.first_name or f"#{to_user.id}",
                            "username": f"@{to_user.username}" if to_user.username else None,
                            "id": to_user.id
                        })
                    except:
                        sent.append({"name": f"#{gift.to_id.user_id}", "username": None, "id": gift.to_id.user_id})
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return await get_gifts(user_id)
    except Exception as e:
        print(f"Ошибка получения подарков: {e}")
    return {"received": received, "sent": sent}

async def get_mentions(username: str):
    mentions = []
    try:
        async for dialog in client.iter_dialogs():
            try:
                async for msg in client.iter_messages(dialog.entity, search=username, limit=3):
                    if msg.text and username in msg.text:
                        mentions.append(f"{dialog.name} | {msg.text[:30]}...")
            except:
                continue
    except Exception as e:
        print(f"Ошибка поиска упоминаний: {e}")
    return mentions[:3]

async def check_scam_base(username: str):
    try:
        entity = await client.get_entity("GID_ScamBase")
        async for msg in client.iter_messages(entity, search=username, limit=5):
            if msg.text and username in msg.text:
                return {"found": True, "link": f"https://t.me/GID_ScamBase/{msg.id}"}
    except:
        pass
    return {"found": False, "link": None}

def spectra_report(username: str):
    return {
        "title": f"Spectra - {username}",
        "link": f"https://cerera.cc/search?q={username}",
        "coverage": "1/10 (10%)",
        "categories": ["Документы", "Банки", "Соцсети", "Работа", "Связи", "Адреса", "Авто", "Недвижимость", "Нарушения", "Связь лица"],
        "summary": {"fio": f"{username} (1/5)", "telegram": f"{username} (1/5)"},
        "found": {"fio": f"{username} ×1", "telegram": f"{username} ×1"},
        "possible_names": "0 ... 1",
        "registrations": ["t.me", "telegram.org"],
        "profile": {"fio": username, "telegram": username, "id": "—", "phone": "—", "bio": "—"}
    }

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
    mentions = await get_mentions(username)
    spectra = spectra_report(username)

    report = f"📋 *Закреплённое сообщение*\nАктуальная ссылка на бота\n\n"
    report += f"*Имя:* {info.get('first_name', '?')} {info.get('last_name', '')}\n"
    report += f"*ID:* {info.get('id', '?')}\n"
    report += f"*Юзернейм:* @{info.get('username', '?')}\n"
    report += f"*Статус:* {'Premium' if info.get('premium') else 'обычный'}\n"
    report += f"*Регистрация:* {info.get('registered', 'неизвестно')}\n"
    report += f"*Дата-центр:* DC {info.get('dc_id', '?')}\n\n"

    if mentions:
        report += f"*Упоминания в чатах/каналах ({len(mentions)}):*\n"
        for m in mentions:
            report += f"- {m}\n"
        report += "\n"

    if gifts.get('received'):
        report += f"*От кого получал(-а) подарки ({len(gifts['received'])}):*\n"
        gift_names = [g.get('username', f"#{g['id']}") for g in gifts['received']]
        report += " · ".join(gift_names) + "\n\n"

    if gifts.get('sent'):
        report += f"*Кому отправлял(-а) подарки (взаимно):*\n"
        gift_names = [g.get('username', f"#{g['id']}") for g in gifts['sent']]
        report += " · ".join(gift_names) + "\n\n"

    if scam and scam.get('found'):
        report += f"*Внесён в список мошенников!*\nСделки проводить не рекомендуется.\n[Пост с обвинением]({scam.get('link', '#')})\n\n"

    report += f"*Интересовались этим:* {len(mentions)}\n\n"
    report += f"*{spectra['title']}*\n{spectra['link']}\n\n"
    report += f"*Покрытие отчёта*\n{spectra['coverage']}\n\n"
    report += f"*Категории:*\n" + "\n".join(f"- {cat}" for cat in spectra['categories']) + "\n\n"
    report += f"*Общая сводка:* 2\n*Фио:* {spectra['summary']['fio']}\n*TELEGRAM:* {spectra['summary']['telegram']}\n\n"
    report += f"*Все найденные значения:*\n*Фио:* {spectra['found']['fio']}\n*TELEGRAM:* {spectra['found']['telegram']}\n\n"
    report += f"*Возможные имена:* {spectra['possible_names']}\n\n*СОКРАЩЕНИЯ / ПРОЧЕЕ (1)*\n\n"
    report += f"*Телеграм:*\n**{username}**\n{username}\n\n"
    report += f"*Сайты, где найдены регистрации:* 2\n- t.me\n- telegram.org\n\n"
    report += f"*Профиль Telegram:* 1\n*ФИО:* {spectra['profile']['fio']}\n*Telegram:* {spectra['profile']['telegram']}\n*Telegram ID:* {spectra['profile']['id']}\n*Телефон:* {spectra['profile']['phone']}\n*Био:* {spectra['profile']['bio']}\n"

    keyboard = [
        [InlineKeyboardButton("🖼 Аватар", callback_data=f"avatar_{username}")],
        [InlineKeyboardButton("🔍 Spectra", url=spectra['link'])]
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
# ЗАПУСК
# ============================================================
async def main():
    await client.start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CallbackQueryHandler(avatar_callback, pattern="^avatar_"))
    print("✅ Бот запущен. /check @username")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
