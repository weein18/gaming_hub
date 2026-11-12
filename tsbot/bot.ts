import TelegramBot from "node-telegram-bot-api";
import { Pool } from "pg";

interface UserRow {
    id: number;
    username: string;
    rank: string;
    xp: number;
    telegram_chat_id: string | null;
    telegram_id: string | null;
    telegram_link_code: string | null;
}

interface MatchRow {
    team1: string;
    team2: string;
    date: string;
    time: string;
    match_type: string;
    tournament_name: string;
    status: string;
}

interface NotificationRow {
    id: number;
    chat_id: string;
    message: string;
}

const token = process.env.TELEGRAM_BOT_TOKEN;
const databaseUrl = process.env.DATABASE_URL;

if (!token) throw new Error("TELEGRAM_BOT_TOKEN is not configured");
if (!databaseUrl) throw new Error("DATABASE_URL is not configured");

const bot = new TelegramBot(token, { polling: true });
const pool = new Pool({ connectionString: databaseUrl });
const backButton = { inline_keyboard: [[{ text: "⬅️ Back", callback_data: "back_home" }]] };
let isDispatchingNotifications = false;

function escapeHtml(value: unknown): string {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function mainMenu(isLinked: Boolean) {
    const buttons: TelegramBot.InlineKeyboardButton[][] = [[{ text: "🎮 Upcoming Matches", callback_data: "matches" }]];
    if (isLinked) {
        buttons.push([{ text: "📊 My Stats", callback_data: "stats" }]);
        buttons.push([{ text: "🔗 Re-link Account", callback_data: "link_prompt" }]);
    } else {
        buttons.push([{ text: "🔗 Link My Account", callback_data: "link_prompt" }]);
    }
    return { inline_keyboard: buttons };
}

async function getLinkedUser(chatId: number | string): Promise<UserRow | null> {
    const result = await pool.query<UserRow>(
        'SELECT * FROM "user" WHERE telegram_chat_id = $1',
        [String(chatId)],
    );
    return result.rows[0] ?? null;
}

async function sendHome(chatId: number, firstName: string): Promise<void> {
    const user = await getLinkedUser(chatId);
    const text = user
        ? `👋 Welcome back, <b>${escapeHtml(user.username)}</b>!\n\n🏅 ${escapeHtml(user.rank)} · ⭐ ${user.xp} XP`
        : `👋 Hey <b>${escapeHtml(firstName || "there")}</b>!\n\nLink your EliteHub account to receive notifications.`;

    await bot.sendMessage(chatId, text, {
        parse_mode: "HTML",
        reply_markup: mainMenu(Boolean(user)),
    });
}

async function linkAccount(chatId: number, username: string | undefined, code: string): Promise<boolean> {
    const result = await pool.query<UserRow>(
        'SELECT * FROM "user" WHERE telegram_link_code = $1',
        [code],
    );
    const user = result.rows[0];
    if (!user) return false;

    await pool.query(
        'UPDATE "user" SET telegram_chat_id = $1, telegram_id = $2, telegram_link_code = NULL WHERE id = $3',
        [String(chatId), username || "", user.id],
    );
    await bot.sendMessage(
        chatId,
        `✅ <b>Account linked!</b>\n\nWelcome, <b>${escapeHtml(user.username)}</b>!`,
        { parse_mode: "HTML", reply_markup: mainMenu(true) },
    );
    return true;
}

bot.onText(/^\/start(?:\s+(.+))?$/, async (msg: TelegramBot.Message, match: RegExpExecArray | null) => {
    try {
        const code = match?.[1]?.trim();
        const username = msg.from?.username;
        const firstName = msg.from?.first_name || "";
        if (code && username && await linkAccount(msg.chat.id, username, code)) return;
        await sendHome(msg.chat.id, firstName);
    } catch (error) {
        console.error("[BOT] /start failed:", error);
    }
});

bot.onText(/^\/link\s+(.+)$/, async (msg: TelegramBot.Message, match: RegExpExecArray | null) => {
    try {
        if(!match?.[1]) return;
        const username = msg.from?.username;
        const linked = await linkAccount(msg.chat.id, username, match[1].trim());
        if (!linked) {
            await bot.sendMessage(
                msg.chat.id,
                "❌ <b>Invalid or expired code.</b>\n\nGenerate a new code in EliteHub Settings.",
                { parse_mode: "HTML" },
            );
        }
    } catch (error) {
        console.error("[BOT] /link failed:", error);
    }
});

bot.on("callback_query", async (query: TelegramBot.CallbackQuery) => {
    if(!query.message) return;
    const chatId = query.message?.chat.id;
    const messageId = query.message?.message_id;
    if (!chatId || !messageId) return;

    try {
        await bot.answerCallbackQuery(query.id);

        if (query.data === "matches") {
            const matches = await pool.query<MatchRow>(
                'SELECT * FROM "match" WHERE status = $1 ORDER BY date, time LIMIT 6',
                ["Upcoming"],
            );
            if (!matches.rows.length) {
                await bot.editMessageText("No upcoming matches right now. Check back later! 🕐", {
                    chat_id: chatId,
                    message_id: messageId,
                    reply_markup: backButton,
                });
                return;
            }

            let text = "🎮 <b>Upcoming Matches</b>\n\n";
            for (const match of matches.rows) {
                text += `⚔️ <b>${escapeHtml(match.team1)}</b> vs <b>${escapeHtml(match.team2)}</b>\n`;
                text += `   📅 ${escapeHtml(match.date)} · ${escapeHtml(match.time)} · ${escapeHtml(match.match_type)}\n`;
                text += `   🏆 ${escapeHtml(match.tournament_name)}\n\n`;
            }
            await bot.editMessageText(text, {
                chat_id: chatId,
                message_id: messageId,
                parse_mode: "HTML",
                reply_markup: backButton,
            });
            return;
        }

        if (query.data === "stats") {
            const user = await getLinkedUser(chatId);
            if (!user) {
                await bot.editMessageText("❌ <b>Account not linked.</b>", {
                    chat_id: chatId,
                    message_id: messageId,
                    parse_mode: "HTML",
                    reply_markup: backButton,
                });
                return;
            }

            const [total, correct, losses] = await Promise.all([
                pool.query<{ count: string }>("SELECT COUNT(*) FROM prediction WHERE user_id = $1", [user.id]),
                pool.query<{ count: string }>("SELECT COUNT(*) FROM prediction WHERE user_id = $1 AND is_correct = true", [user.id]),
                pool.query<{ count: string }>("SELECT COUNT(*) FROM prediction WHERE user_id = $1 AND is_correct = false", [user.id]),
            ]);
            const totalCount = Number(total.rows[0].count);
            const correctCount = Number(correct.rows[0].count);
            const lossCount = Number(losses.rows[0].count);
            const accuracy = totalCount ? Math.round((correctCount / totalCount) * 100) : 0;

            await bot.editMessageText(
                `📊 <b>${escapeHtml(user.username)}'s Stats</b>\n\n` +
                `🏅 ${escapeHtml(user.rank)}\n⭐ ${user.xp} XP\n🎯 ${accuracy}%\n` +
                `✅ ${correctCount}  ❌ ${lossCount}\n📈 Total: ${totalCount}`,
                {
                    chat_id: chatId,
                    message_id: messageId,
                    parse_mode: "HTML",
                    reply_markup: backButton,
                },
            );
            return;
        }

        if (query.data === "link_prompt") {
            await bot.editMessageText(
                "🔗 <b>Link your EliteHub account</b>\n\n" +
                "1. Go to <b>EliteHub → Settings</b>\n" +
                "2. Click <b>Connect Telegram</b>\n" +
                "3. Send: <code>/link YOUR_CODE</code>",
                {
                    chat_id: chatId,
                    message_id: messageId,
                    parse_mode: "HTML",
                    reply_markup: backButton,
                },
            );
            return;
        }

        if (query.data === "back_home") {
            const user = await getLinkedUser(chatId);
            const firstName = query.from.first_name || "there";
            const text = user
                ? `👋 Welcome back, <b>${escapeHtml(user.username)}</b>!\n\nWhat would you like to do?`
                : `👋 Hey <b>${escapeHtml(query.from.first_name || "there")}</b>!\n\nWhat would you like to do?`;
            await bot.editMessageText(text, {
                chat_id: chatId,
                message_id: messageId,
                parse_mode: "HTML",
                reply_markup: mainMenu(Boolean(user)),
            });
        }
    } catch (error) {
        console.error("[BOT] Callback failed:", error);
    }
});

async function claimNotifications(): Promise<NotificationRow[]> {
    const client = await pool.connect();
    try {
        await client.query("BEGIN");
        const result = await client.query(`
            SELECT id, chat_id, message
            FROM telegram_notification
            WHERE sent_at IS NULL
              AND attempts < 5
              AND (claimed_at IS NULL OR claimed_at < NOW() - INTERVAL '5 minutes')
            ORDER BY id
            LIMIT 20
            FOR UPDATE SKIP LOCKED
        `);
        if (result.rows.length) {
            await client.query(
                "UPDATE telegram_notification SET claimed_at = NOW(), attempts = attempts + 1 WHERE id = ANY($1::int[])",
                [result.rows.map((notification) => notification.id)],
            );
        }
        await client.query("COMMIT");
        return result.rows;
    } catch (error) {
        await client.query("ROLLBACK");
        throw error;
    } finally {
        client.release();
    }
}

async function dispatchNotifications() {
    if (isDispatchingNotifications) return;
    isDispatchingNotifications = true;
    try {
        const notifications = await claimNotifications();
        for (const notification of notifications) {
            try {
                await bot.sendMessage(notification.chat_id, notification.message, { parse_mode: "HTML" });
                await pool.query(
                    "UPDATE telegram_notification SET sent_at = NOW(), claimed_at = NULL, last_error = NULL WHERE id = $1",
                    [notification.id],
                );
            } catch (error: any) {
                const errorMessage = String(error?.message || error).slice(0, 2000);
                await pool.query(
                    "UPDATE telegram_notification SET claimed_at = NULL, last_error = $1 WHERE id = $2",
                    [String(error.message).slice(0, 2000), notification.id],
                );
                console.error(`[BOT] Notification ${notification.id} failed:`, error?.message);
            }
        }
    } finally {
        isDispatchingNotifications = false;
    }
}

bot.on("polling_error", (error) => console.error("[BOT] Polling error:", error.message));
process.on("unhandledRejection", (error) => console.error("[BOT] Unhandled rejection:", error));

async function shutdown(): Promise<void> {
    console.log("[BOT] Shutting down...");
    await bot.stopPolling();
    await pool.end();
    process.exit(0);
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);

dispatchNotifications().catch((error) => console.error("[BOT] Initial notification dispatch failed:", error));
setInterval(() => {
    dispatchNotifications().catch((error) => console.error("[BOT] Notification dispatch failed:", error));
}, 15_000);

console.log("[BOT] JavaScript bot started polling");
