import os
import json
import pytz

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, JobQueue
)

# === КОНФИГ ===
TOKEN = "8224693908:AAEM6woNULlwsBQJpFktBMRrVEeCpv7JOHk"
ADMIN_ID = 514959058
DATA_FILE = "profiles.json"

NAME, AGE, GENDER, PHOTO = range(4)

profiles = {}
banned_users = set()
user_temp = {}

# ======== ЗАГРУЗКА / СОХРАНЕНИЕ =========
def load_data():
    global profiles, banned_users
    if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                profiles = data.get("profiles", {})
                banned_users = set(data.get("banned", []))
            except json.JSONDecodeError:
                print("⚠️ Ошибка при чтении JSON-файла. Созданы пустые данные.")
                profiles = {}
                banned_users = set()
    else:
        save_data()

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"profiles": profiles, "banned": list(banned_users)}, f, ensure_ascii=False, indent=2)

# ======== СТАРТ =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in banned_users:
        await update.message.reply_text("🚫 Вы заблокированы и не можете пользоваться ботом.")
        return

    if user_id in profiles:
        keyboard = [
            [InlineKeyboardButton("Посмотреть анкеты 💞", callback_data="browse")],
            [InlineKeyboardButton("Удалить анкету 🗑️", callback_data="delete")]
        ]
        await update.message.reply_text("С возвращением! Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        keyboard = [[InlineKeyboardButton("Создать анкету 👌", callback_data="create")]]
        await update.message.reply_text("Привет! 👋 Хочешь создать анкету?", reply_markup=InlineKeyboardMarkup(keyboard))

# ======== КНОПКИ =========
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = str(query.from_user.id)

    if data == "create":
        await query.message.reply_text("Как тебя зовут?")
        user_temp[user_id] = {}
        return NAME
    elif data == "browse":
        await query.edit_message_text(text="Загружаю анкеты...")
        await show_profiles(update, context)
        return ConversationHandler.END
    elif data == "delete":
        if user_id in profiles:
            del profiles[user_id]
            save_data()
            await query.edit_message_text("✅ Ваша анкета удалена.")
        else:
            await query.edit_message_text("❌ У вас нет анкеты.")
    elif data.startswith("like_"):
        target_id = data.split("_", 1)[1]
        await handle_like(update, context, user_id, target_id)
        await show_profiles(update, context)
    elif data.startswith("dislike_"):
        await query.edit_message_text("⏭️ Пропущено.")
        await show_profiles(update, context)
    elif data.startswith("msg_"):
        target_id = data.split("_", 1)[1]
        target_username = (await context.bot.get_chat(user_id)).username
        await context.bot.send_message(
            target_id,
            f"💌 Вас лайкнули! Пользователь @{target_username or user_id} хочет с вами пообщаться."
        )
        await query.message.reply_text("📨 Сообщение отправлено!")

    return ConversationHandler.END

# ======== АНКЕТА =========
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_temp[user_id]["name"] = update.message.text
    await update.message.reply_text("Сколько тебе лет?")
    return AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    age_text = update.message.text.strip()
    if not age_text.isdigit() or not (14 <= int(age_text) <= 99):
        await update.message.reply_text("Введите корректный возраст (14–99).")
        return AGE
    user_temp[user_id]["age"] = age_text
    keyboard = [
        [InlineKeyboardButton("Мужской ♂️", callback_data="male"),
         InlineKeyboardButton("Женский ♀️", callback_data="female")]
    ]
    await update.message.reply_text("Укажи свой пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GENDER

async def gender_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    gender = "Мужской" if query.data == "male" else "Женский"
    user_temp[user_id] = {"gender": gender, "photos": user_temp.get(user_id, {}).get("photos", [])}
    await query.edit_message_text("Отправь 1–3 своих фото 📸 (минимум одно).")
    return PHOTO

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in user_temp or "photos" not in user_temp[user_id]:
        await update.message.reply_text("Начни создание анкеты заново через /start.")
        return ConversationHandler.END

    photo_id = update.message.photo[-1].file_id
    user_temp[user_id]["photos"].append(photo_id)

    if len(user_temp[user_id]["photos"]) >= 3:
        await finish_profile(update, context)
        return ConversationHandler.END

    await update.message.reply_text(f"Принято! Отправь ещё фото ({len(user_temp[user_id]['photos'])}/3) или напиши 'Готово'.")
    return PHOTO

async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if len(user_temp[user_id].get("photos", [])) < 1:
        await update.message.reply_text("🚫 Нужно хотя бы одно фото.")
        return PHOTO
    profiles[user_id] = user_temp[user_id]
    save_data()
    await update.message.reply_text("✅ Анкета создана!")
    await show_profiles(update, context)
    return ConversationHandler.END

# ======== ПРОСМОТР АНКЕТ =========
async def show_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    me = profiles.get(user_id)
    if not me:
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text("Сначала создай анкету через /start.")
        return

    opposite_gender = "Женский" if me["gender"] == "Мужской" else "Мужской"
    candidates = [
        (uid, p)
        for uid, p in profiles.items()
        if p["gender"] == opposite_gender and uid != user_id and uid not in banned_users and p.get("photos")
    ]
    if not candidates:
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text("😕 Пока нет подходящих анкет.")
        return

    target_id, p = candidates[0]
    media = [InputMediaPhoto(x) for x in p["photos"]]
    await context.bot.send_media_group(user_id, media)
    text = f"**{p['name']}**, {p['age']} лет\nПол: {p['gender']}"
    keyboard = [
        [InlineKeyboardButton("❤️ Класс", callback_data=f"like_{target_id}"),
         InlineKeyboardButton("👎 Пропустить", callback_data=f"dislike_{target_id}")],
        [InlineKeyboardButton("💬 Сообщение", callback_data=f"msg_{target_id}")]
    ]
    await context.bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ======== ЛАЙКИ =========
async def handle_like(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, target_id):
    query = update.callback_query
    liker_username = (await context.bot.get_chat(user_id)).username
    await context.bot.send_message(
        target_id,
        f"❤️ Вас лайкнул @{liker_username or user_id}! Напишите /start, чтобы посмотреть."
    )
    try:
        await query.edit_message_caption(caption="👍 Лайк отправлен!", reply_markup=None)
    except:
        await query.edit_message_text("👍 Лайк отправлен!")

# ======== АДМИН =========
async def all_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = "📋 Все анкеты:\n"
    for uid, p in profiles.items():
        text += f"ID: {uid} | {p.get('name','N/A')} ({p.get('age','N/A')}), {p.get('gender','N/A')}\n"
    await update.message.reply_text(text or "Нет анкет.")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Используй: /ban <id>")
        return
    uid = args[0]
    banned_users.add(uid)
    if uid in profiles:
        del profiles[uid]
    save_data()
    await update.message.reply_text(f"🚫 Пользователь {uid} заблокирован.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Используй: /unban <id>")
        return
    uid = args[0]
    banned_users.discard(uid)
    save_data()
    await update.message.reply_text(f"✅ Пользователь {uid} разблокирован.")

# ======== MAIN =========
def main():
    load_data()

    bishkek_tz = pytz.timezone("Asia/Bishkek")

    # ✅ Исправлено: убрали set_timezone
    job_queue = JobQueue()
    job_queue.start()

    app = (
        Application.builder()
        .token(TOKEN)
        .job_queue(job_queue)
        .build()
    )

    # Диалог анкет
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button, pattern="^create$"), CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            GENDER: [CallbackQueryHandler(gender_choice, pattern="^(male|female)$")],
            PHOTO: [
                MessageHandler(filters.PHOTO, get_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex("^(Готово|готово)$"), finish_profile),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Отправь фото или напиши 'Готово'.")),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CommandHandler("all_profiles", all_profiles))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))

    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

