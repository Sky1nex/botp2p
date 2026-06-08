from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import datetime
import random
from io import BytesIO
import os
import string
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials


# ================== CONFIG ==================

BOT_TOKEN = "8345450647:AAHUOm7Y-OlE2cxfM1QwnIPCxoWAk1dgvH4"

ADMIN_ID = 8280201278

SPREADSHEET_ID = "14KiSr0lxmn09O-95HxTGbpTK2JTiL4B3-qbMJsa4alo"
SHEET_NAME = "Report"

LOBBY_IMAGE = "lobby.png"
STORY_IMAGE = "story.png"
SPRED_IMAGE = "spred.png"

# ================== GOOGLE SHEETS ==================

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

CREDS = ServiceAccountCredentials.from_json_keyfile_name("moroz.json", SCOPE)
GS_CLIENT = gspread.authorize(CREDS)
SHEET = GS_CLIENT.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
ACCESS_SHEET = GS_CLIENT.open_by_key(SPREADSHEET_ID).worksheet("NickName")
def load_user_names():
    data = ACCESS_SHEET.get_all_values()
    result = {}
    for row in data[1:]: 
        if len(row) >= 2:
            nickname, tg_id = row[0], row[1]
            if tg_id.isdigit():
                result[int(tg_id)] = nickname
    return result



HEADERS = [
    "NickName",
    "Дата",
    "Вход ( Сумма )",
    "Выход ( Сумма )",
    "Профит ₽",
    "Профит %",
    "Профит $",
    "Сделка №",
]

if SHEET.row_values(1) != HEADERS:
    SHEET.clear()
    SHEET.append_row(HEADERS)

# ================== STATES ==================

ASK_ENTRY_SUM = "ask_entry_sum"
ASK_EXIT_SUM = "ask_exit_sum"
ASK_ENTRY_RATE = "ask_entry_rate"

COMPARE_ENTRY = "compare_entry"
COMPARE_EXIT = "compare_exit"

CALC_SUM = "calc_sum"
CALC_BUY = "calc_buy"
CALC_SELL = "calc_sell"

user_state = {}
last_bot_message = {}
user_ids = {}

async def gs_get_records():
    return await asyncio.to_thread(SHEET.get_all_records)

async def gs_append_row(row):
    return await asyncio.to_thread(SHEET.append_row, row)

# ================== HELPERS ==================

def get_user_name(uid: int) -> str:
    try:
        rows = ACCESS_SHEET.get_all_values()[1:]  # без заголовка
        for row in rows:
            if len(row) >= 2 and row[1] == str(uid):
                return row[0]  # NickName из таблицы
    except Exception as e:
        print("GET USER NAME ERROR:", e)

    return "Unknown"


def get_random_id():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=5))


def check_access(user_id):
    return user_id in ALLOWED_IDS


def today_date():
    return datetime.date.today()


def generate_deal_id():
    existing = set(SHEET.col_values(8)[1:])
    while True:
        rid = str(random.randint(10000, 99999))
        if rid not in existing:
            return rid

async def get_today_profit(user_id):
    nickname = get_user_name(user_id)

    if nickname == "Unknown":
        return 0.0

    today = today_date()
    rows = await gs_get_records()
    total = 0.0

    for r in rows:
        if r["NickName"] != nickname:
            continue

        dt = datetime.datetime.strptime(r["Дата"], "%Y-%m-%d %H:%M:%S")
        if dt.date() == today:
            total += float(r["Профит ₽"])

    return round(total, 2)

def get_user_names():
    data = ACCESS_SHEET.get_all_values()
    result = {}
    for row in data[1:]:
        if len(row) >= 2 and row[1].isdigit():
            result[int(row[1])] = row[0]
    return result


def get_rank(user_id):
    nickname = get_user_name(user_id)
    if nickname == "Unknown":
        return "Деревянный"

    rows = SHEET.get_all_records()
    count = sum(1 for r in rows if r["NickName"] == nickname)

    if count >= 350:
        return "💎 Алмазный"
    if count >= 200:
        return "🥇 Золотой"
    if count >= 100:
        return "🥈 Серебряный"
    if count >= 50:
        return "🥉 Бронзовый"
    return "Деревянный"



def make_main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📤 Отчёт", callback_data="send_report"),
                InlineKeyboardButton("📁 История", callback_data="history"),
            ],
            [
                InlineKeyboardButton("🔗 Спред %", callback_data="compare"),
                InlineKeyboardButton("🧮 Калькулятор", callback_data="calc"),
            ],
        ]
    )


def small_cancel_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
    )


def main_menu_kb():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]]
    )


async def send_bot_message(context, chat_id, user_id, text, reply_markup=None, always_new=False, image_path=None):
    text = f"<b>{text}</b>"
    prev = last_bot_message.get(user_id)

    if not always_new and prev:
        try:
            await context.bot.edit_message_text(
                chat_id=prev[0],
                message_id=prev[1],
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return  # ← ВАЖНО
        except Exception:
            pass

    if image_path and os.path.exists(image_path):
        sent = await context.bot.send_photo(
            chat_id=chat_id,
            photo=open(image_path, "rb"),
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    else:
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    last_bot_message[user_id] = (sent.chat.id, sent.message_id)

# ================== COMMANDS ==================

async def reg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔️ Нет доступа")

    args = context.args

    if len(args) < 2:
        return await update.message.reply_text(
            "❌ Использование:\n/reg telegram_id nickname"
        )

    tg_id = args[0]
    nickname = " ".join(args[1:])

    if not tg_id.isdigit():
        return await update.message.reply_text("❌ ID должен быть числом")

    # Проверяем есть ли уже такой ID
    existing_ids = ACCESS_SHEET.col_values(2)
    if tg_id in existing_ids:
        return await update.message.reply_text("⚠️ Такой ID уже зарегистрирован")

    try:
        ACCESS_SHEET.append_row([nickname, tg_id])
        await update.message.reply_text(
            f"✅ Пользователь добавлен:\n👤 {nickname}\n🆔 {tg_id}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(["Выпал: 🦅 Орёл", "Выпала: 🪙 Решка"]))


async def try_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🎯 Выпало: {random.randint(0,100)}")


async def zov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    text = " ".join(context.args)
    if not text:
        return await update.message.reply_text("❌ Текст обязателен")

    users = ACCESS_SHEET.col_values(2)

    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 <b>{text}</b>",
                parse_mode="HTML"
            )
        except:
            pass


def has_access(user_id: int) -> bool:
    try:
        ids = ACCESS_SHEET.col_values(2)  # колонка с telegram_id
        return str(user_id) in ids
    except Exception as e:
        print("ACCESS CHECK ERROR:", e)
        return False

def get_nickname(uid: int):
    rows = ACCESS_SHEET.get_all_values()[1:]
    for row in rows:
        if len(row) >= 2 and row[1] == str(uid):
            return row[0]
    return "Unknown"

# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    if not has_access(uid):
        return await update.message.reply_text(
            "⛔️ Доступ к боту запрещён\n\n"
            "Если считаешь, что это ошибка — обратись к админу."
        )

    if uid not in user_ids:
        user_ids[uid] = get_random_id()

    name = get_user_name(uid)
    rank = get_rank(uid)
    profit = await get_today_profit(uid)

    text = (
        f"⌜ Главное меню\n"
        f"👤 {name} \n"
        f"🏆 Ранг: {rank}\n\n"
        f"★ Профит за сутки: {profit} ₽"
    )





    if uid not in user_ids:
        user_ids[uid] = get_random_id()

    name = get_nickname(uid)
    rank = get_rank(uid)
    profit = await get_today_profit(uid)

    text = (
        f"• Главное меню\n\n"
        f"👤 {name} \n"
        f"🏆 Ранг: {rank}\n\n"
        f"★ Профит за сутки: {profit}₽ "
    )

    await send_bot_message(
        context,
        update.effective_chat.id,
        uid,
        text,
        make_main_keyboard(),
        True,
        LOBBY_IMAGE,
    )

def get_history_txt(uid: int, days: int):
    user_names = get_user_names()  # <-- здесь получаем свежие данные
    rows = SHEET.get_all_values()[1:]  # без шапки
    now = datetime.datetime.now()
    result = []

    for row in rows:
        try:
            username, date_str, entry, exit_, profit_rub, profit_pct, profit_usdt, deal_id = row
            row_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        if user_names.get(uid) != username:  # <-- используем свежие данные
            continue

        if (now - row_date).days <= days:
            result.append(
                f"📝 Сделка #{deal_id}\n"
                f"Дата: {date_str}\n"
                f"Вход: {entry} ₽\n"
                f"Выход: {exit_} ₽\n"
                f"Профит: {profit_rub} ₽ | {profit_usdt} USDT | {profit_pct}%\n"
                f"{'-'*25}\n"
            )

    if not result:
        return None

    filename = f"history_{uid}_{days}d.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.writelines(result)

    return filename


# ================== HANDLERS ==================
def make_history_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📅 За день", callback_data="hist_day")],
            [InlineKeyboardButton("🗓 За неделю", callback_data="hist_week")],
            [InlineKeyboardButton("📆 За месяц", callback_data="hist_month")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")],
        ]
    )


async def error_handler(update, context):
    print("ERROR:", context.error)


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        return
    uid = query.from_user.id

    if query.data == "send_report":
        user_state[uid] = {"stage": ASK_ENTRY_SUM}
        return await send_bot_message(
            context,
            query.message.chat.id,
            uid,
            "Введите сумму входа:",
            small_cancel_kb(),
            True,
        )


    if query.data == "history":
        
        return await send_bot_message(
            context,
            query.message.chat.id,
            uid,
            "Выберите период:",
            make_history_keyboard(),
            True,
            STORY_IMAGE,
        )

    if query.data.startswith("hist_"):
        periods = {
            "hist_day": 1,
            "hist_week": 7,
            "hist_month": 30
        }

        days = periods.get(query.data)
        file_path = get_history_txt(uid, days)

        if not file_path:
            return await send_bot_message(
                context,
                query.message.chat.id,
                uid,
                "❌ За выбранный период отчётов нет",
                main_menu_kb(),
                True
            )

        await context.bot.send_document(
            chat_id=query.message.chat.id,
            document=open(file_path, "rb"),
            caption="📂 История сделок выгружена."
        )

        os.remove(file_path)
        return



    if query.data == "compare":
        user_state[uid] = {"stage": COMPARE_ENTRY}
        return await send_bot_message(
            context,
            query.message.chat.id,
            uid,
            "Введите курс входа:",
            small_cancel_kb(),
            True,
        )

    if query.data == "calc":
        user_state[uid] = {"stage": CALC_SUM}
        return await send_bot_message(
            context,
            query.message.chat.id,
            uid,
            "💰 На сколько ₽ покупаешь USDT?",
            small_cancel_kb(),
            True,
        )

    if query.data == "menu":
        return await start(update, context)



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in user_state:
        return

    chat_id = update.effective_chat.id
    text = update.message.text.strip().replace(",", ".")

    state = user_state[uid]



        # ---------- КАЛЬКУЛЯТОР КРУГА ----------
    if state["stage"] == CALC_SUM:
        try:
            state["rub_start"] = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите сумму ₽ числом",
                small_cancel_kb(), True
            )

        state["stage"] = CALC_BUY
        return await send_bot_message(
            context, chat_id, uid,
            "📉 По какому курсу покупаешь USDT?",
            small_cancel_kb(), True
        )

    if state["stage"] == CALC_BUY:
        try:
            state["buy_rate"] = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите курс покупки числом",
                small_cancel_kb(), True
            )

        state["stage"] = CALC_SELL
        return await send_bot_message(
            context, chat_id, uid,
            "📈 По какому курсу продаёшь USDT?",
            small_cancel_kb(), True
        )

    if state["stage"] == CALC_SELL:
        try:
            sell_rate = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите курс продажи числом",
                small_cancel_kb(), True
            )

        rub_start = state["rub_start"]
        buy_rate = state["buy_rate"]

        usdt = round(rub_start / buy_rate, 4)
        rub_end = round(usdt * sell_rate, 2)

        profit_rub = round(rub_end - rub_start, 2)
        profit_usdt = round(profit_rub / sell_rate, 4)
        profit_percent = round((profit_rub / rub_start) * 100, 2)

        user_state.pop(uid, None)

        return await send_bot_message(
            context,
            chat_id,
            uid,
            f"🔁 <b>Результат круга</b>\n\n"
            f"🟢 <b>Начало</b>\n"
            f"• ₽ {rub_start}\n"
            f"• USDT {usdt}\n\n"
            f"🔵 <b>Итог</b>\n"
            f"• ₽ {rub_end}\n"
            f"• USDT {round(rub_end / sell_rate, 4)}\n\n"
            f"💰 <b>Профит</b>\n"
            f"├ ₽ {profit_rub}\n"
            f"├ USDT {profit_usdt}\n"
            f"└ % {profit_percent}%",
            main_menu_kb(),
            True
        )


    # ---------- СПРЕД ----------
    if state["stage"] == COMPARE_ENTRY:
        try:
            state["entry"] = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите курс входа ЧИСЛОМ",
                small_cancel_kb(), True
            )

        state["stage"] = COMPARE_EXIT
        return await send_bot_message(
            context, chat_id, uid,
            "Введите курс выхода:",
            small_cancel_kb(), True
        )

    if state["stage"] == COMPARE_EXIT:
        try:
            exit_rate = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите курс выхода ЧИСЛОМ",
                small_cancel_kb(), True
            )

        entry = state["entry"]
        percent = round(((exit_rate - entry) / entry) * 100, 2)
        user_state.pop(uid, None)

        return await send_bot_message(
            context, chat_id, uid,
            f"📊 <b>Спред</b>\n\n"
            f"⌜Вход: {entry}\n"
            f"⌞Выход: {exit_rate}\n\n"
            f"☺︎ Разница: <b>{percent}%</b>",
            main_menu_kb(),
            True,
            SPRED_IMAGE
        )

    # ---------- ОТЧЁТ ----------
    if state["stage"] == ASK_ENTRY_SUM:
        try:
            state["entry_sum"] = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите сумму входа цифрами",
                small_cancel_kb(), True
            )

        state["stage"] = ASK_EXIT_SUM
        return await send_bot_message(
            context, chat_id, uid,
            "Введите сумму выхода:",
            small_cancel_kb(), True
        )

    if state["stage"] == ASK_EXIT_SUM:
        try:
            state["exit_sum"] = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите сумму выхода цифрами",
                small_cancel_kb(), True
            )

        state["stage"] = ASK_ENTRY_RATE
        return await send_bot_message(
            context, chat_id, uid,
            "Введите курс входа:",
            small_cancel_kb(), True
        )

    if state["stage"] == ASK_ENTRY_RATE:
        try:
            entry_rate = float(text)
        except ValueError:
            return await send_bot_message(
                context, chat_id, uid,
                "❌ Введите курс цифрами",
                small_cancel_kb(), True
            )

        entry_sum = state["entry_sum"]
        exit_sum = state["exit_sum"]

        usd_entry = round(entry_sum / entry_rate, 2)
        usd_exit = round(exit_sum / entry_rate, 2)

        profit_rub = round(exit_sum - entry_sum, 2)
        profit_usd = round(usd_exit - usd_entry, 2)
        profit_percent = round((profit_rub / entry_sum) * 100, 2)

        deal_id = generate_deal_id()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        await gs_append_row([
            get_user_name(uid),
            now,
            entry_sum,
            exit_sum,
            profit_rub,
            profit_percent,
            profit_usd,
            deal_id,
        ])
        user_state.pop(uid, None)

        result = (
            f"📝 <b>Отчёт №{deal_id} • {get_user_name(uid)}</b>\n\n"
            f"Начало: {entry_sum} ₽ • {usd_entry} USDT\n"
            f"Итог: {exit_sum} ₽ • {usd_exit} USDT\n\n"
            f"💰 <b>Профит</b>\n"
            f"├ RUB {profit_rub}\n"
            f"├ USDT {profit_usd}\n"
            f"└ % {profit_percent}%"
        )

        return await send_bot_message(
            context, chat_id, uid,
            result,
            main_menu_kb(),
            True
        )


def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(10)
        .read_timeout(10)
        .write_timeout(10)
        .build()
    )
    app.add_handler(CommandHandler("reg", reg))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roll", roll))
    app.add_handler(CommandHandler("try", try_cmd))
    app.add_handler(CommandHandler("zov", zov))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("goat p2p...")
    #print("loading...")
    #print("vse good")
    #print("ili net? ")
    #print("eshe raz")
    #print("zapusk...")
    #print("loading...")
    #print("ne, vse ril zaebok")
    #print("zdarova zaebal!") 
    app.run_polling()

if __name__ == "__main__":
    
    main()
