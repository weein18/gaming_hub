const TelegramBot = require("node-telegram-bot-api");
const { Pool } = require("pg");

const token = process.env.TELEGRAM_BOT_TOKEN;
const bot = token ? new TelegramBot(token, {polling: true}) : null;

const pool = new Pool({connectionString: process.env.DATABASE_URL});

async function sendMessage(chatID, text) {
    if (!bot || !chatID) return;
    try {
        await bot.sendMessage(chatID, text, {parse_mode: "HTML"});
    } catch (e) {
        console.log(`[BOT] Failed to send ${e.message}`);
    }
}


function mainMenu(isLinked) {
    if(isLinked) {
        return {
            inline_keyboard: [
                [{ text: "🎮 Upcoming matches", callback_data: "matches"}],
                [{ text: "📊 My stats", callback_data: "stats"}],
                [{ text: "🔗 Re-link Account", callback_data: "link_promt"}],
            ]
        };
    }
    return {
        inline_keyboard: [
            [{ text: "🎮 Upcoming matches", callback_data: "matches"}],
            [{ text: "🔗 Link My Account", callback_data: "link_promt"}],
        ]
    };
}
const backBtn = { inline_keyboard: [[{ text: "⬅️ Back", callback_data: "back_home"}]]};

if (bot) {
    bot.onText(/\/link (.+)/, async (msg, match) => {
        const chatId = String(msg.chat.id);
        const code = match[1].trim();
        const name = msg.from.first_name || "there";
        if (code) {
            const user = await pool.query(
                `SELECT * FROM "user" WHERE telegram_link_code = $1`, [code]
            );
            if (user.rows.length > 0) {
                const u = user.rows[0];
                await pool.query(
                    `UPDATE "user" SET telegram_chat_id=$1, telegram_id=$2, telegram_link_code=NULL WHERE id=$3`,
                    [chatId, msg.from.username || "", u.id]
                );
                return bot.sendMessage(chatId,
                    `✅ <b>Account linked!</b>\n\nWelcome, <b>${u.username}</b>!`,
                    { parse_mode: "HTML", reply_markup: mainMenu(true)}
                );
            }
        }
        const user = await pool.query(
            `SELECT * FROM "user" WHERE telegram_chat_id = $1`, [chatId]
        );
        const isLinked = user.rows.length > 0;
        const text = isLinked
            ? `👋 Welcome back, <b>${user.rows[0].username}</b>!\n\n🏅 ${user.rows[0].rank} · ⭐ ${user.rows[0].xp} XP`
            : `👋 Hey <b>${name}</b>!\n\nLink your EliteHub account to receive notifications.`;
        bot.sendMessage(chatId, text, {parse_mode: "HTML", reply_markup: mainMenu(isLinked)});
    });
    bot.on("callback_query", async(query) => {
        const chatId = String(query.from.id);
        const data = query.data;
        await bot.answerCallbackQuery(query.id);
        if (data==="matches") {
            const matches = await pool.query(
                `SELECT * FROM match WHERE status='Upcoming' ORDER BY date, time LIMIT 6`
            );
            if (!matches.rows.length) {
                return bot.editMessageText("No upcoming matches right now", {
                    chat_id: chatId, message_id: query.message.message_id
                });
            }
            let text = '🎮 <b>Upcoming Matches</b>\n\n';
            for(const m of matches.rows) {
                text += `⚔️ <b>${m.team1}</b> vs <b>${m.team2}</b>\n`;
                text += `   📅 ${m.date} · ${m.time} · ${m.match_type}\n`;
                text += `   🏆 ${m.tournament_name}\n\n`;
            }
            return bot.editMessageText(text, {
                chat_id: chatId, message_id: query.message.message_id,
                parse_mode: "HTML", reply_markup: backBtn
            });
        }
        if (data === "stats") {
            const user = await pool.query(
                `SELECT * FROM "user" WHERE telegram_chat_id=$1`, [chatId]
            );
            if(!user.rows.length) {
                return bot.editMessageText("❌ Account not linked.", {
                    chat_id: chatId, message_id: query.message.message_id,
                    parse_mode: "HTML", reply_markup: backBtn
                });
            }
            const u = user.rows[0];
            const total = await pool.query("SELECT COUNT(*) FROM prediction WHERE user_id=$1", [u.id]);
            const correct = await pool.query("SELECT COUNT(*) FROM prediction WHERE user_id=$1 AND is_correct=true", [u.id]);
            const losses = await pool.query("SELECT COUNT(*) FROM prediction WHERE user_id=$1 AND is_correct=false", [u.id]);
            const t = parseInt(total.rows[0].count);
            const c = parseInt(correct.rows[0].count);
            const l = parseInt(losses.rows[0].count);
            const acc = t > 0 ? Math.round(c / t * 100) : 0;
            const text = `📊 <b>${u.username}'s Stats</b>\n\n🏅 ${u.rank}\n⭐ ${u.xp} XP\n🎯 ${acc}%\n✅ ${c}  ❌ ${l}\n📈 Total: ${t}`;
            return bot.editMessageText(text, {
                chat_id: chatId, message_id: query.message.message_id,
                parse_mode: "HTML", reply_markup: backBtn
            });
        }
        if (data === "link_promt") {
            return bot.editMessageText(
                '🔗 <b>Link your account</b>\n\n1. Go to EliteHub → Settings\n2. Click Connect Telegram\n3. Send: <code>/link YOUR_CODE</code>',
                {chat_id: chatId, message_id: query.message.message_id, parse_mode: "HTML", reply_markup: backBtn}
            );
        }
        if (data === "back_home") {
            const user = await pool.query(`SELECT * FROM "user" WHERE telegram_chat_id=$1`, [chatId]);
            const isLinked = user.rows.length > 0;
            const name = query.from.first_name || "there";
            const text = isLinked
                ? `👋 Welcome back, <b>${user.rows[0].username}</b>!\n\nWhat would you like to do?`
                : `👋 Hey <b>${name}</b>!\n\nWhat would you like to do?`;
            return bot.editMessageText(text, {
                chat_id: chatId, message_id: query.message.message_id,
                parse_mode: "HTML", reply_markup: mainMenu(isLinked)
            });
        }
    });
    console.log("[BOT] Started polling...");
} else {
    console.log("[BOT] No token set, skipping");
}
module.exports = { sendMessage};