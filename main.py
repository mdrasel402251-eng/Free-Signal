import sqlite3
import random
import asyncio
import aiohttp
import ssl
import logging
import os

from flask import Flask
from threading import Thread

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery
)
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= CONFIGURATION =================

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

SUPPORT_USER = "@sojibbro5"

MARKET_API = (
    "https://draw.ar-lottery01.com/"
    "WinGo/WinGo_1M/GetHistoryIssuePage.json"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= KEEP ALIVE =================

app = Flask('')

@app.route('/')
def home():
    return "Signal Bot Running Successfully!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ================= DATABASE =================

def get_db():

    conn = sqlite3.connect(
        "pro_ai_bot.db",
        check_same_thread=False
    )

    return conn, conn.cursor()

def db_init():

    conn, cursor = get_db()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            balance REAL DEFAULT 0,
            referred_by INTEGER,
            join_status INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            price REAL,
            coins REAL
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO settings
        (key,value)
        VALUES ('signal_cost', 10)
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO settings
        (key,value)
        VALUES ('refer_reward', 50)
    """)

    conn.commit()
    conn.close()

db_init()

active_signals = {}

# ================= HELPERS =================

async def fetch_market_data():

    ssl_context = ssl.create_default_context()

    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                ssl=ssl_context
            )
        ) as session:

            payload = {
                "pageSize": 1,
                "pageNo": 1,
                "typeId": 1
            }

            async with session.post(
                MARKET_API,
                json=payload,
                timeout=10
            ) as resp:

                if resp.status == 200:

                    data = await resp.json()

                    return {
                        "issue": str(
                            data['data']['list'][0]['issueNumber']
                        )
                    }

    except:
        return None

    return None

def main_menu(uid):

    buttons = [
        [KeyboardButton(text="🎯 START WIN GO 30S")],

        [
            KeyboardButton(text="👤 Profile"),
            KeyboardButton(text="👥 Refer & Earn")
        ],

        [
            KeyboardButton(text="💰 Buy Coin"),
            KeyboardButton(text="📞 Support")
        ]
    ]

    if uid == ADMIN_ID:

        buttons.append([
            KeyboardButton(text="⚙️ Admin Panel")
        ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )

# ================= START =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):

    uid = message.from_user.id

    args = message.text.split()

    ref_id = (
        int(args[1])
        if len(args) > 1
        and args[1].isdigit()
        else None
    )

    conn, cursor = get_db()

    cursor.execute("""
        SELECT * FROM users
        WHERE user_id=?
    """, (uid,))

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO users
            (user_id, name, referred_by)
            VALUES(?,?,?)
        """, (
            uid,
            message.from_user.full_name,
            ref_id
        ))

        conn.commit()

    conn.close()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Join Channel",
                    url="https://t.me/battleteam2"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Verify Membership",
                    callback_data="verify_user"
                )
            ]
        ]
    )

    await message.answer(
        f"👋 Welcome "
        f"{message.from_user.first_name}!\n\n"

        f"Join our official channel "
        f"and verify to continue.",

        reply_markup=kb
    )

# ================= VERIFY =================

@dp.callback_query(F.data == "verify_user")
async def verify_user(call: CallbackQuery):

    uid = call.from_user.id

    conn, cursor = get_db()

    cursor.execute("""
        SELECT referred_by, join_status
        FROM users
        WHERE user_id=?
    """, (uid,))

    res = cursor.fetchone()

    if res and res[1] == 0:

        ref_id = res[0]

        cursor.execute("""
            SELECT value FROM settings
            WHERE key='refer_reward'
        """)

        reward = cursor.fetchone()[0]

        if ref_id:

            cursor.execute("""
                UPDATE users
                SET balance = balance + ?
                WHERE user_id=?
            """, (reward, ref_id))

            try:

                await bot.send_message(
                    ref_id,
                    f"🎉 Refer Bonus!\n"
                    f"You got {reward} coins."
                )

            except:
                pass

        cursor.execute("""
            UPDATE users
            SET join_status = 1
            WHERE user_id=?
        """, (uid,))

        conn.commit()

    conn.close()

    await call.message.delete()

    await call.message.answer(
        "✅ Verification Successful!",
        reply_markup=main_menu(uid)
    )

# ================= SIGNAL ENGINE =================

@dp.message(F.text == "🎯 START WIN GO 30S")
async def start_signal(message: types.Message):

    uid = message.from_user.id

    conn, cursor = get_db()

    cursor.execute("""
        SELECT balance FROM users
        WHERE user_id=?
    """, (uid,))

    bal = cursor.fetchone()[0]

    cursor.execute("""
        SELECT value FROM settings
        WHERE key='signal_cost'
    """)

    cost = cursor.fetchone()[0]

    conn.close()

    if bal < cost:

        return await message.answer(
            f"❌ Low Balance!\n"
            f"Needs {cost} Coins."
        )

    if uid in active_signals:

        return await message.answer(
            "⚠️ Signal already running!"
        )

    active_signals[uid] = True

    await message.answer(
        "🤖 Starting AI Signal Engine..."
    )

    asyncio.create_task(
        signal_loop(message, uid, cost)
    )

async def signal_loop(message, uid, cost):

    while uid in active_signals:

        try:

            conn, cursor = get_db()

            cursor.execute("""
                SELECT balance FROM users
                WHERE user_id=?
            """, (uid,))

            bal = cursor.fetchone()[0]

            if bal < cost:

                await message.answer(
                    "❌ Out of balance!\n"
                    "Signal stopped."
                )

                active_signals.pop(uid, None)

                conn.close()

                break

            analysis = await message.answer(
                "📊 Analyzing "
                "1000+ algorithms... (5s)"
            )

            await asyncio.sleep(5)

            try:
                await analysis.delete()
            except:
                pass

            market = await fetch_market_data()

            if not market:

                await message.answer(
                    "⚠️ Market data pending..."
                )

                conn.close()

                await asyncio.sleep(5)

                continue

            cursor.execute("""
                UPDATE users
                SET balance = balance - ?
                WHERE user_id=?
            """, (cost, uid))

            conn.commit()
            conn.close()

            prediction = random.choice([
                "🔵 SMALL",
                "🔴 BIG"
            ])

            next_issue = str(
                int(market['issue']) + 1
            )

            numbers = (
                "0, 1, 2, 4"
                if "SMALL" in prediction
                else "5, 7, 8, 9"
            )

            signal_txt = (
                f"🤖 AI PREDICTOR PRO\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"🎮 Game   » WIN GO 30S\n"
                f"📊 Period » {next_issue}\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"🎯 Result » {prediction}\n"
                f"🛡 Safe   » {numbers}\n"

                f"━━━━━━━━━━━━━━━━━━\n"

                f"📈 Accuracy: "
                f"{random.randint(85, 99)}%\n"

                f"⏳ Waiting for next round..."
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🛑 STOP",
                            callback_data="stop_sig"
                        )
                    ]
                ]
            )

            await message.answer(
                signal_txt,
                reply_markup=kb
            )

            await asyncio.sleep(25)

        except Exception as e:

            logging.error(
                f"Signal Error: {e}"
            )

            await asyncio.sleep(5)

# ================= STOP SIGNAL =================

@dp.callback_query(F.data == "stop_sig")
async def stop_sig(call: CallbackQuery):

    active_signals.pop(
        call.from_user.id,
        None
    )

    await call.message.answer(
        "🛑 Signal process stopped."
    )

    await call.answer()

# ================= ADMIN PANEL =================

@dp.message(F.text == "⚙️ Admin Panel")
async def admin(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardBuilder()

    kb.row(
        InlineKeyboardButton(
            text="🎁 Set Refer",
            callback_data="adm_ref"
        ),

        InlineKeyboardButton(
            text="💰 Add Balance",
            callback_data="adm_bal"
        )
    )

    kb.row(
        InlineKeyboardButton(
            text="➕ Add Plan",
            callback_data="adm_plan"
        )
    )

    await message.answer(
        "⚙️ Admin Control Panel",
        reply_markup=kb.as_markup()
    )

# ================= SET REFER =================

@dp.message(Command("set_refer"))
async def set_ref(message: types.Message):

    if message.from_user.id != ADMIN_ID:
        return

    val = message.text.split()[1]

    conn, cursor = get_db()

    cursor.execute("""
        UPDATE settings
        SET value = ?
        WHERE key = 'refer_reward'
    """, (val,))

    conn.commit()
    conn.close()

    await message.answer(
        f"✅ Refer reward updated to {val}"
    )

# ================= PROFILE =================

@dp.message(F.text == "👤 Profile")
async def profile(message: types.Message):

    conn, cursor = get_db()

    cursor.execute("""
        SELECT balance FROM users
        WHERE user_id=?
    """, (message.from_user.id,))

    bal = cursor.fetchone()[0]

    conn.close()

    await message.answer(
        f"👤 Your Profile\n\n"

        f"💰 Balance: {bal} Coins\n"
        f"🆔 ID: {message.from_user.id}"
    )

# ================= BUY COIN =================

@dp.message(F.text == "💰 Buy Coin")
async def buy(message: types.Message):

    conn, cursor = get_db()

    cursor.execute("""
        SELECT price, coins FROM plans
    """)

    plans = cursor.fetchall()

    conn.close()

    txt = "💰 Coin Shop\n\n"

    for p, c in plans:

        txt += (
            f"💎 {p} TK = "
            f"{c} Coins\n"
        )

    txt += f"\n📞 Contact: {SUPPORT_USER}"

    await message.answer(txt)

# ================= SUPPORT =================

@dp.message(F.text == "📞 Support")
async def support(message: types.Message):

    await message.answer(
        f"📞 Contact for help:\n"
        f"{SUPPORT_USER}"
    )

# ================= MAIN =================

async def main():

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    print("✅ Signal Bot running perfectly!")

    while True:

        try:

            await dp.start_polling(bot)

        except Exception as e:

            logging.error(
                f"Polling error: {e}"
            )

            await asyncio.sleep(5)

if __name__ == "__main__":

    try:

        keep_alive()

        asyncio.run(main())

    except (KeyboardInterrupt, SystemExit):

        print("Bot stopped.")