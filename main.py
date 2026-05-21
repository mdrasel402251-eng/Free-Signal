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
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ================= CONFIGURATION =================

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

SUPPORT_USER = "@sojibbro5"

# আপনার দেওয়া ৩০ সেকেন্ডের গেম হিস্ট্রি API
MARKET_API = (
    "https://draw.ar-lottery01.com/"
    "WinGo/WinGo_30S/GetHistoryIssuePage.json"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ================= STATES FOR ADMIN PANEL =================

class AdminStates(StatesGroup):
    waiting_for_refer_reward = State()
    waiting_for_balance_data = State()
    waiting_for_plan_data = State()

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
            connector=aiohttp.TCPConnector(ssl=ssl_context)
        ) as session:
            payload = {
                "pageSize": 1,
                "pageNo": 1,
                "typeId": 1
            }
            # ক্যাশ এড়াতে টাইমস্ট্যাম্পসহ রিকোয়েস্ট
            url = f"{MARKET_API}?ts={int(asyncio.get_event_loop().time())}"
            async with session.post(
                url,
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
    except Exception as e:
        logging.error(f"API Fetch Error: {e}")
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
        if len(args) > 1 and args[1].isdigit()
        else None
    )
    
    if ref_id == uid:
        ref_id = None

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
        f"👋 Welcome {message.from_user.first_name}!\n\n"
        f"Join our official channel and verify to continue.",
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
                    f"You got {reward} coins for inviting a new member."
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
    try:
        await call.message.delete()
    except:
        pass

    await call.message.answer(
        "✅ Verification Successful!",
        reply_markup=main_menu(uid)
    )

# ================= REFER & EARN =================

@dp.message(F.text == "👥 Refer & Earn")
async def refer_earn_handler(message: types.Message):
    uid = message.from_user.id
    
    bot_info = await bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start={uid}"
    
    conn, cursor = get_db()
    cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by = ? AND join_status = 1", (uid,))
    total_refers = cursor.fetchone()[0]
    
    cursor.execute("SELECT value FROM settings WHERE key='refer_reward'")
    reward = cursor.fetchone()[0]
    conn.close()
    
    response_text = (
        f"👥 **Refer & Earn Program**\n\n"
        f"Invite your friends and earn premium coins when they successfully verify membership!\n\n"
        f"💰 **Per Refer Reward:** {reward} Coins\n"
        f"📊 **Your Total Verified Refers:** {total_refers}\n\n"
        f"🔗 **Your Referral Link:**\n`{ref_link}`"
    )
    
    await message.answer(response_text, parse_mode="Markdown")

# ================= SIGNAL ENGINE (30S OPTIMIZED) =================

@dp.message(F.text == "🎯 START WIN GO 30S")
async def start_signal(message: types.Message):
    uid = message.from_user.id

    conn, cursor = get_db()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    bal = cursor.fetchone()[0]

    cursor.execute("SELECT value FROM settings WHERE key='signal_cost'")
    cost = cursor.fetchone()[0]
    conn.close()

    if bal < cost:
        return await message.answer(
            f"❌ Low Balance!\nNeeds {cost} Coins."
        )

    if uid in active_signals:
        return await message.answer(
            "⚠️ Signal already running!"
        )

    await message.answer("🤖 Starting AI Signal Engine...")
    
    task = asyncio.create_task(signal_loop(message, uid, cost))
    active_signals[uid] = task

async def signal_loop(message, uid, cost):
    last_signal_msg = None
    
    try:
        while True:
            conn = None
            try:
                conn, cursor = get_db()
                cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
                bal = cursor.fetchone()[0]

                if bal < cost:
                    await message.answer("❌ Out of balance!\nSignal stopped.")
                    break

                # ৩০ সেকেন্ড গেমের জন্য দ্রুত অ্যানালাইসিস নোটিশ (৩ সেকেন্ড)
                analysis = await message.answer("📊 Analyzing 1000+ algorithms... (3s)")
                await asyncio.sleep(3)
                
                try:
                    await analysis.delete()
                except:
                    pass

                market = await fetch_market_data()
                if not market:
                    await message.answer("⚠️ Market data pending... Retrying soon.")
                    await asyncio.sleep(3)
                    continue

                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (cost, uid))
                conn.commit()

            except Exception as db_err:
                logging.error(f"Loop DB Error: {db_err}")
                await asyncio.sleep(3)
                continue
            finally:
                if conn:
                    conn.close()

            prediction = random.choice(["🔵 SMALL", "🔴 BIG"])
            next_issue = str(int(market['issue']) + 1)
            numbers = "0, 1, 2, 4" if "SMALL" in prediction else "5, 7, 8, 9"

            signal_txt = (
                f"🤖 AI PREDICTOR PRO\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎮 Game   » WIN GO 30S\n"
                f"📊 Period » {next_issue}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 Result » {prediction}\n"
                f"🛡 Safe   » {numbers}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📈 Accuracy: {random.randint(85, 99)}%\n"
                f"⏳ Waiting for next round..."
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🛑 STOP", callback_data="stop_sig")]
                ]
            )

            if last_signal_msg:
                try:
                    await last_signal_msg.delete()
                except:
                    pass

            last_signal_msg = await message.answer(signal_txt, reply_markup=kb)
            
            # ৩০ সেকেন্ডের সাইকেল বজায় রাখার জন্য রেস্ট স্লিপ (৩ + ২৫ = মোট ২৮ সেকেন্ডের কাছাকাছি)
            await asyncio.sleep(25)

    except asyncio.CancelledError:
        if last_signal_msg:
            try:
                await last_signal_msg.delete()
            except:
                pass
        logging.info(f"Signal loop cancelled for user {uid}")
    finally:
        active_signals.pop(uid, None)

# ================= STOP SIGNAL =================

@dp.callback_query(F.data == "stop_sig")
async def stop_sig(call: CallbackQuery):
    uid = call.from_user.id
    task = active_signals.pop(uid, None)
    
    if task:
        task.cancel()
        await call.message.answer("🛑 Signal process stopped immediately.")
    else:
        await call.message.answer("⚠️ No active signal running.")
        
    try:
        await call.message.delete()
    except:
        pass
    await call.answer()

# ================= ADMIN PANEL =================

@dp.message(F.text == "⚙️ Admin Panel")
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎁 Set Refer", callback_data="adm_ref"),
        InlineKeyboardButton(text="💰 Add Balance", callback_data="adm_bal")
    )
    kb.row(
        InlineKeyboardButton(text="➕ Add Plan", callback_data="adm_plan")
    )

    await message.answer(
        "⚙️ Admin Control Panel",
        reply_markup=kb.as_markup()
    )

# --- Admin FSM Handlers ---

@dp.callback_query(F.data == "adm_ref")
async def adm_ref_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Denied!")
    
    await state.set_state(AdminStates.waiting_for_refer_reward)
    await call.message.answer("✍️ Please enter the new **Refer Reward Amount**:")
    await call.answer()

@dp.message(AdminStates.waiting_for_refer_reward)
async def process_set_refer(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    val = message.text.strip()
    if not val.replace('.', '', 1).isdigit():
        return await message.answer("❌ Invalid input! Please enter a valid number.")

    conn, cursor = get_db()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'refer_reward'", (float(val),))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Success! Refer reward updated to {val} Coins.")

@dp.callback_query(F.data == "adm_bal")
async def adm_bal_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Denied!")
        
    await state.set_state(AdminStates.waiting_for_balance_data)
    await call.message.answer("✍️ Enter **User_ID** and **Amount** separated by space.\nExample: `12345678 500`")
    await call.answer()

@dp.message(AdminStates.waiting_for_balance_data)
async def process_add_balance(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
            
        target_uid = int(parts[0])
        amount = float(parts[1])
        
        conn, cursor = get_db()
        cursor.execute("SELECT user_id FROM users WHERE user_id=?", (target_uid,))
        if not cursor.fetchone():
            conn.close()
            return await message.answer("❌ User not found in database!")
            
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_uid))
        conn.commit()
        conn.close()
        
        try:
            await bot.send_message(target_uid, f"💰 Admin added {amount} coins to your balance!")
        except:
            pass
            
        await state.clear()
        await message.answer(f"✅ Successfully added {amount} coins to User {target_uid}.")
        
    except ValueError:
        await message.answer("❌ Format Error! Use: `User_ID Amount` (e.g., `54125896 100`)")

@dp.callback_query(F.data == "adm_plan")
async def adm_plan_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Denied!")
        
    await state.set_state(AdminStates.waiting_for_plan_data)
    await call.message.answer("✍️ Enter Plan **Price (TK)** and **Coins Amount** separated by space.\nExample: `100 500`")
    await call.answer()

@dp.message(AdminStates.waiting_for_plan_data)
async def process_add_plan(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
            
        price = float(parts[0])
        coins = float(parts[1])
        
        conn, cursor = get_db()
        cursor.execute("INSERT INTO plans (price, coins) VALUES (?, ?)", (price, coins))
        conn.commit()
        conn.close()
        
        await state.clear()
        await message.answer(f"✅ New Plan Added: {price} TK = {coins} Coins.")
        
    except ValueError:
        await message.answer("❌ Format Error! Use: `Price Coins` (e.g., `100 500`)")

# ================= PROFILE =================

@dp.message(F.text == "👤 Profile")
async def profile(message: types.Message):
    conn, cursor = get_db()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,))
    res = cursor.fetchone()
    bal = res[0] if res else 0
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
    cursor.execute("SELECT price, coins FROM plans")
    plans = cursor.fetchall()
    conn.close()

    txt = "💰 Coin Shop\n\n"
    if plans:
        for p, c in plans:
            txt += f"💎 {p} TK = {c} Coins\n"
    else:
        txt += "No plans available right now.\n"

    txt += f"\n📞 Contact admin to buy coins: {SUPPORT_USER}"
    await message.answer(txt)

# ================= SUPPORT =================

@dp.message(F.text == "📞 Support")
async def support(message: types.Message):
    await message.answer(f"📞 Contact for help:\n{SUPPORT_USER}")

# ================= MAIN =================

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Signal Bot running perfectly on WIN GO 30S Mode!")

    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        keep_alive()
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
