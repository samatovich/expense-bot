import asyncio
import re
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

BOT_TOKEN = "8868559408:AAGKUVWQ2_Dbcqse9FdNpu69QhV-FvduTXw"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- 1. Маалымат базасын түзүү ---
conn = sqlite3.connect("expenses.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    amount REAL,
    comment TEXT,
    created_at TEXT,
    date_str TEXT,
    month_period TEXT
)
""")
conn.commit()

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def get_month_str(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month]} {year}"

def shift_month(year: int, month: int, shift: int):
    month += shift
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1
    return year, month

# --- 2. Төмөнкү туруктуу баскычтар ---
def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Today"), KeyboardButton(text="Statistics")]
        ],
        resize_keyboard=True
    )

# --- 3. Интерактивдүү статистика менюсун түзүү ---
def build_stats_keyboard(user_id: int, year: int, month: int):
    month_period = f"{month:02d}.{year}"
    
    cursor.execute(
        "SELECT category, SUM(amount) FROM expenses WHERE user_id = ? AND month_period = ? GROUP BY category ORDER BY SUM(amount) ASC",
        (user_id, month_period)
    )
    rows = cursor.fetchall()
    total = sum(amt for _, amt in rows)
    
    keyboard = []
    for cat, amt in rows:
        btn_text = f"{cat.capitalize()}: -{amt:.1f}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"cat_detail:{month_period}:{cat}")])
    
    prev_y, prev_m = shift_month(year, month, -1)
    next_y, next_m = shift_month(year, month, 1)
    
    nav_row = [
        InlineKeyboardButton(text="<<", callback_data=f"page:{prev_y}:{prev_m}"),
        InlineKeyboardButton(text=">>", callback_data=f"page:{next_y}:{next_m}")
    ]
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="Back", callback_data="close_menu")])
    
    header_text = f"<b>{get_month_str(year, month)}</b>\nExpenses: <b>-{total:.1f}</b>"
    return header_text, InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- 4. Командалар жана баскычтарды иштетүү ---

@dp.message(Command("start", "menu"))
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Бот ишке түштү!\n\nФормат: <code>Taxi -30</code> же <code>Taxi 30</code> же <code>Taxi 30 comment</code>",
        parse_mode="HTML",
        reply_markup=get_reply_keyboard()
    )

@dp.message(F.text == "Today")
async def today_cmd(message: types.Message):
    user_id = message.from_user.id
    today_str = datetime.now().strftime("%d.%m.%Y")
    
    cursor.execute(
        "SELECT category, amount, comment, created_at FROM expenses WHERE user_id = ? AND date_str = ? ORDER BY id DESC",
        (user_id, today_str)
    )
    rows = cursor.fetchall()
    
    if not rows:
        await message.answer("📅 Бүгүн эч кандай расход жазыла элек.", reply_markup=get_reply_keyboard())
        return
    
    text = f"📅 <b>Бүгүнкү чыгымдар ({today_str}):</b>\n\n"
    total = 0
    for cat, amt, comm, time_str in rows:
        comm_text = f" ({comm})" if comm != "—" else ""
        text += f"• <b>{cat.capitalize()}</b>: -{amt:.1f}{comm_text}\n"
        total += amt
    text += f"\n💰 <b>Жалпы:</b> -{total:.1f}"
    
    await message.answer(text, parse_mode="HTML", reply_markup=get_reply_keyboard())

@dp.message(F.text == "Statistics")
async def stats_cmd(message: types.Message):
    now = datetime.now()
    text, markup = build_stats_keyboard(message.from_user.id, now.year, now.month)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

# --- 5. Inline баскыч иштеткичтери ---

@dp.callback_query(F.data.startswith("page:"))
async def page_cb(callback: types.CallbackQuery):
    await callback.answer()
    _, y_str, m_str = callback.data.split(":")
    text, markup = build_stats_keyboard(callback.from_user.id, int(y_str), int(m_str))
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("cat_detail:"))
async def cat_detail_cb(callback: types.CallbackQuery):
    await callback.answer()
    _, month_period, cat = callback.data.split(":")
    user_id = callback.from_user.id
    
    cursor.execute(
        "SELECT amount, comment, created_at FROM expenses WHERE user_id = ? AND month_period = ? AND category = ? ORDER BY id DESC",
        (user_id, month_period, cat)
    )
    rows = cursor.fetchall()
    
    m, y = map(int, month_period.split("."))
    text = f"📂 <b>{cat.capitalize()}</b> ({get_month_str(y, m)}):\n\n"
    total = 0
    for amt, comm, date_str in rows:
        comm_text = f" ({comm})" if comm != "—" else ""
        text += f"📅 <code>{date_str}</code> — <b>-{amt:.1f}</b>{comm_text}\n"
        total += amt
    text += f"\n💰 <b>Жалпы:</b> -{total:.1f}"
    
    back_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data=f"page:{y}:{m}")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_markup)

@dp.callback_query(F.data == "close_menu")
async def close_menu_cb(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()

# --- 6. Расходду кабыл алуу логикасы ---
@dp.message()
async def process_expense(message: types.Message):
    text = message.text.strip()
    match = re.match(r"^([a-zA-Zа-яА-ЯөүңӨҮҢ]+)\s*[-:]?\s*(-?\d+(?:\.\d+)?)(?:\s+(.+))?$", text)
    
    if match:
        category = match.group(1).lower()
        amount = abs(float(match.group(2)))
        comment = match.group(3) if match.group(3) else "—"
        user_id = message.from_user.id
        
        now_dt = datetime.now()
        created_at = now_dt.strftime("%d.%m.%Y %H:%M")
        date_str = now_dt.strftime("%d.%m.%Y")
        month_period = now_dt.strftime("%m.%Y")
        
        cursor.execute(
            "INSERT INTO expenses (user_id, category, amount, comment, created_at, date_str, month_period) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, category, amount, comment, created_at, date_str, month_period)
        )
        conn.commit()
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND month_period = ?", (user_id, month_period))
        month_total = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND date_str = ?", (user_id, date_str))
        today_total = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND month_period = ? AND category = ?", (user_id, month_period, category))
        cat_total = cursor.fetchone()[0] or 0.0
        
        reply = (
            f"Saved\n"
            f"<b>-{amount:.2f} category {category}</b>\n\n"
            f"--------\n"
            f"this month: <b>-{month_total:.1f}</b>\n"
            f"today: <b>-{today_total:.1f}</b>\n"
            f"In the category {category}: <b>-{cat_total:.1f}</b>"
        )
        
        await message.answer(reply, parse_mode="HTML", reply_markup=get_reply_keyboard())
    else:
        await message.answer("⚠️ Формат туура эмес.\nМисалы: <code>Taxi 30</code> же <code>Taxi -30 comment</code>", parse_mode="HTML", reply_markup=get_reply_keyboard())

# --- 7. Ботту иштетүү ---
async def main():
    print("Бот иштеп жатат...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())