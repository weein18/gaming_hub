import os
import asyncio
import threading
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

def get_token():
    return os.getenv("TELEGRAM_BOT_TOKEN")

# ── SEND FROM FLASK ──
def send_telegram_message(chat_id, text):
    token = get_token()
    if not chat_id or not token:
        return
    async def _send():
        bot = Bot(token=token)
        async with bot:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    try:
        asyncio.run(_send())
    except Exception as e:
        print(f"[BOT] Failed to send: {e}")

# ── MAIN MENU ──
def main_menu_keyboard(is_linked=False):
    if is_linked:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Upcoming Matches", callback_data="matches")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
            [InlineKeyboardButton("🔗 Re-link Account", callback_data="link_prompt")],
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Upcoming Matches", callback_data="matches")],
            [InlineKeyboardButton("🔗 Link My Account", callback_data="link_prompt")],
        ])

# ── /START ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import app, User
    chat_id = str(update.effective_chat.id)
    with app.app_context():
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        is_linked = user is not None
    name = update.effective_user.first_name or "there"
    if is_linked:
        text = (
            f"👋 Welcome back, <b>{user.username}</b>!\n\n"
            f"🏅 Rank: <b>{user.rank}</b> · ⭐ <b>{user.xp} XP</b>\n\n"
            "What would you like to do?"
        )
    else:
        text = (
            f"👋 Hey <b>{name}</b>, welcome to <b>EliteHub Bot</b>!\n\n"
            "Track CS2 matches, get notified about results and manage your predictions — all from Telegram.\n\n"
            "To get started, link your EliteHub account 👇"
        )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard(is_linked))

# ── CALLBACKS ──
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = str(query.from_user.id)
    if data == "matches":
        from app import app, Match
        with app.app_context():
            upcoming = Match.query.filter_by(status="Upcoming").order_by(Match.date, Match.time).limit(6).all()
            if not upcoming:
                await query.edit_message_text("No upcoming matches right now. Check back later! 🕐")
                return
            text = "🎮 <b>Upcoming Matches</b>\n\n"
            for m in upcoming:
                text += f"⚔️ <b>{m.team1}</b> vs <b>{m.team2}</b>\n"
                text += f"   📅 {m.date} · {m.time} · {m.match_type}\n"
                text += f"   🏆 {m.tournament_name}\n\n"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    elif data == "stats":
        from app import app, User, Prediction
        with app.app_context():
            user = User.query.filter_by(telegram_chat_id=chat_id).first()
            if not user:
                await query.edit_message_text(
                    "❌ Account not linked yet.\n\nGo to <b>EliteHub → Settings → Connect Telegram</b> to get your code.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Link Account", callback_data="link_prompt"), InlineKeyboardButton("⬅️ Back", callback_data="back_home")]])
                )
                return
            total = Prediction.query.filter_by(user_id=user.id).count()
            correct = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
            accuracy = int(correct / total * 100) if total > 0 else 0
            wins = correct
            losses = Prediction.query.filter_by(user_id=user.id, is_correct=False).count()
            text = (
                f"📊 <b>{user.username}'s Stats</b>\n\n"
                f"🏅 Rank: <b>{user.rank}</b>\n"
                f"⭐ XP: <b>{user.xp}</b>\n"
                f"🎯 Accuracy: <b>{accuracy}%</b>\n"
                f"✅ Wins: <b>{wins}</b>  ❌ Losses: <b>{losses}</b>\n"
                f"📈 Total Predictions: <b>{total}</b>"
            )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    elif data == "link_prompt":
        text = (
            "🔗 <b>Link your EliteHub account</b>\n\n"
            "1. Go to <b>EliteHub → Settings</b>\n"
            "2. Click <b>Connect Telegram</b>\n"
            "3. You'll get a code — send it here:\n\n"
            "<code>/link YOUR_CODE</code>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    elif data == "back_home":
        from app import app, User
        with app.app_context():
            user = User.query.filter_by(telegram_chat_id=chat_id).first()
            is_linked = user is not None
        name = query.from_user.first_name or "there"
        if is_linked:
            text = f"👋 Welcome back, <b>{user.username}</b>!\n\nWhat would you like to do?"
        else:
            text = f"👋 Hey <b>{name}</b>!\n\nWhat would you like to do?"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard(is_linked))

# ── /LINK CODE ──
async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import app, db, User
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/link YOUR_CODE</code>\n\nGet your code from EliteHub → Settings → Connect Telegram",
            parse_mode="HTML"
        )
        return
    code = context.args[0].strip()
    chat_id = str(update.effective_chat.id)
    tg_username = update.effective_user.username or ""
    with app.app_context():
        user = User.query.filter_by(telegram_link_code=code).first()
        if not user:
            await update.message.reply_text(
                "❌ Invalid or expired code.\n\nGenerate a new one in EliteHub Settings.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Main Menu", callback_data="back_home")]])
            )
            return
        user.telegram_chat_id = chat_id
        user.telegram_id = tg_username
        user.telegram_link_code = None
        db.session.commit()
        await update.message.reply_text(
            f"✅ <b>Successfully linked!</b>\n\n"
            f"Welcome, <b>{user.username}</b>! 🎉\n"
            f"You'll now receive match result notifications here.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(is_linked=True)
        )

# ── RUN ──
def run_bot():
    token = get_token()
    if not token:
        print("[BOT] No TELEGRAM_BOT_TOKEN set, skipping")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_app = Application.builder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("link", link_command))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    print("[BOT] Starting polling loop...")
    bot_app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
        stop_signals=None
    )

def start_bot_thread():
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()