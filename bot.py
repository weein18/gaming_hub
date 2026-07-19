import os
import asyncio
import threading
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── HELPER ──
async def send_message_async(chat_id, text):
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

def send_telegram_message(chat_id, text):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    try:
        asyncio.run(send_message_async(chat_id, text))
    except Exception as e:
        print(f"[BOT] Failed to send message: {e}")

# ── COMMANDS ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to <b>EliteHub Bot</b>!\n\n"
        "To link your account, go to <b>EliteHub → Settings</b> and click <b>Connect Telegram</b>.\n"
        "You'll get a code — send it here with /link YOUR_CODE\n\n"
        "Commands:\n"
        "/matches — today's upcoming matches\n"
        "/stats — your prediction stats\n"
        "/link CODE — link your EliteHub account",
        parse_mode="HTML"
    )
async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import app, db, User
    if not context.args:
        await update.message.reply_text("Usage: /link YOUR_CODE")
        return
    code = context.args[0].strip()
    chat_id = str(update.effective_chat.id)
    tg_username = update.effective_user.username or ""
    with app.app_context():
        user = User.query.filter_by(telegram_link_code=code).first()
        if not user:
            await update.message.reply_text("❌ Invalid or expired code. Generate a new one in Settings.")
            return
        user.telegram_chat_id = chat_id
        user.telegram_id = tg_username
        user.telegram_link_code = None
        db.session.commit()
        await update.message.reply_text(
            f"✅ Successfully linked to <b>{user.username}</b>!\n"
            "You'll now receive match notifications here.",
            parse_mode="HTML"
        )
async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import app, Match
    with app.app_context():
        upcoming = Match.query.filter_by(status="Upcoming").order_by(Match.date, Match.time).limit(5).all()
        if not upcoming:
            await update.message.reply_text("No upcoming matches right now.")
            return
        text = "🎮 <b>Upcoming Matches</b>\n\n"
        for m in upcoming:
            text += f"⚔️ <b>{m.team1}</b> vs <b>{m.team2}</b>\n"
            text += f"   📅 {m.date} · {m.time} · {m.match_type}\n"
            text += f"   🏆 {m.tournament_name}\n\n"
        await update.message.reply_text(text, parse_mode="HTML")
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import app, db, User, Prediction
    chat_id = str(update.effective_chat.id)
    with app.app_context():
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if not user:
            await update.message.reply_text("❌ Account not linked. Use /link YOUR_CODE first.")
            return
        total = Prediction.query.filter_by(user_id=user.id).count()
        correct = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
        accuracy = int(correct / total * 100) if total > 0 else 0
        await update.message.reply_text(
            f"📊 <b>Your Stats — {user.username}</b>\n\n"
            f"🏅 Rank: <b>{user.rank}</b>\n"
            f"⭐ XP: <b>{user.xp}</b>\n"
            f"🎯 Accuracy: <b>{accuracy}%</b>\n"
            f"✅ Correct: <b>{correct}</b> / {total} predictions",
            parse_mode="HTML"
        )
# ── START BOT ──
# def run_bot():
#     if not TELEGRAM_TOKEN:
#         print("[BOT] No TELEGRAM_BOT_TOKEN set, skipping")
#         return
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
#     app_bot.add_handler(CommandHandler("start", start))
#     app_bot.add_handler(CommandHandler("link", link_command))
#     app_bot.add_handler(CommandHandler("matches", matches_command))
#     app_bot.add_handler(CommandHandler("stats", stats_command))
#     print("[BOT] Starting...")
#     app_bot.run_polling(allowed_updates=Update.ALL_TYPES)

def run_bot():
    if not TELEGRAM_TOKEN:
        print("[BOT] No TELEGRAM_BOT_TOKEN set, skipping")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("link", link_command))
    app_bot.add_handler(CommandHandler("matches", matches_command))
    app_bot.add_handler(CommandHandler("stats", stats_command))
    print("[BOT] Starting polling loop...")
    app_bot.run_polling(
        allowed_updates=Update.ALL_TYPES,
        close_loop=False,
        stop_signals=None
    )

def start_bot_thread():
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()