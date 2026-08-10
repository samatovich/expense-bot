import asyncio
import re
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiohttp import web

import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "8868559408:AAGKUVWQ2_Dbcqse9FdNpu69QhV-FvduTX")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FSM (Өзгөртүү абалын башкаруу) ---
class EditState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()
    waiting_for_comment = State()

# --- 1. Маалымат базасын түзүү ---
conn = sqlite3.connect("expenses.db", check_same_thread=False)
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

def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Today"), KeyboardButton(text="Statistics")]
        ],
        resize_keyboard=True
    )

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

# --- Командалар ---

@dp.message(Command("start", "menu"))
async def start_cmd(message: types.Message):
    welcome_text = (
        "👋 **Салам! Мен сиздин чыгымдарыңызды эсептөөгө жардам берүүчү ботмун.**\n\n"
        "**Эсептерди кантип жазуу керек?**\n"
        "Сумманы жана категорияны жазып жөнөтүңүз, мен дароо сактап коём.\n"
        "Мисалы:\n"
        "• `Taxi 150`\n"
        "• `Еда 300`\n"
        "• `Market 290 нан, сүт алдым`\n\n"
        "**Өзгөртүү же өчүрүп салуу**\n"
        "Ар бир жазылган чыгымдын астында **«Изменить»** жана **«Отменить»** баскычтары чыгат:\n"
        "• **«Изменить»** — сумманы, категорияны же комментарийди оңдоо.\n"
        "• **«Отменить»** — акыркы жазылган чыгымды базадан өчүрүү.\n\n"
        "**Негизги баскычтар жана командалар:**\n"
        "• **Today** — бүгүнкү чыгымдарыңыздын тизмеси.\n"
        "• **Statistics** — айлык статистика жана мурунку айлардын архиви (`<<` жана `>>` баскычтары аркылуу).\n"
        "• `/reset` — сиздин бардык чыгымдарыңызды толугу менен тазалоо.\n\n"
        "Баары даяр! Жөн гана биринчи чыгымды жазып көрүңүз (мисалы: `Taxi 100`)."
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_reply_keyboard())

@dp.message(Command("reset"))
async def reset_db_cmd(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
    conn.commit()
    await message.answer("🧹 Бардык чыгымдарыңыз толугу менен тазаланды! Эми жаңыдан жаза берсеңиз болот.")

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

# --- Inline баскычтар жана оңдоо логикасы ---

@dp.callback_query(F.data.startswith("edit_opt:"))
async def edit_options(callback: types.CallbackQuery):
    await callback.answer()
    exp_id = callback.data.split(":")[1]
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сумманы өзгөртүү", callback_data=f"edit_amt:{exp_id}")],
        [InlineKeyboardButton(text="Категорияны өзгөртүү", callback_data=f"edit_cat:{exp_id}")],
        [InlineKeyboardButton(text="Описанижени өзгөртүү", callback_data=f"edit_comm:{exp_id}")],
        [InlineKeyboardButton(text="🗑 Удалить трату", callback_data=f"delete_exp:{exp_id}")]
    ])
    await callback.message.edit_text("Эмнени өзгөртүүнү каалайсыз?", reply_markup=kb)

@dp.callback_query(F.data.startswith("cancel_exp:"))
@dp.callback_query(F.data.startswith("delete_exp:"))
async def delete_expense(callback: types.CallbackQuery):
    await callback.answer()
    exp_id = callback.data.split(":")[1]
    
    cursor.execute("DELETE FROM expenses WHERE id = ?", (exp_id,))
    conn.commit()
    
    await callback.message.edit_text("❌ Чыгым базадан өчүрүлдү!")

@dp.callback_query(F.data.startswith("edit_amt:"))
async def edit_amt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    exp_id = callback.data.split(":")[1]
    await state.update_data(exp_id=exp_id)
    await state.set_state(EditState.waiting_for_amount)
    await callback.message.answer("Жаңы сумманы киргизиңиз (мисалы: 50):")

@dp.message(EditState.waiting_for_amount)
async def process_new_amount(message: types.Message, state: FSMContext):
    try:
        new_amt = float(message.text.strip())
        data = await state.get_data()
        cursor.execute("UPDATE expenses SET amount = ? WHERE id = ?", (new_amt, data['exp_id']))
        conn.commit()
        await state.clear()
        await message.answer(f"✅ Сумма **{new_amt}** деп өзгөртүлдү!", parse_mode="Markdown")
    except ValueError:
        await message.answer("Сураныч, бир гана сан киргизиңиз:")

@dp.callback_query(F.data.startswith("edit_cat:"))
async def edit_cat_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    exp_id = callback.data.split(":")[1]
    await state.update_data(exp_id=exp_id)
    await state.set_state(EditState.waiting_for_category)
    await callback.message.answer("Жаңы категорияны жазыңыз (мисалы: Taxi):")

@dp.message(EditState.waiting_for_category)
async def process_new_cat(message: types.Message, state: FSMContext):
    new_cat = message.text.strip().lower()
    data = await state.get_data()
    cursor.execute("UPDATE expenses SET category = ? WHERE id = ?", (new_cat, data['exp_id']))
    conn.commit()
    await state.clear()
    await message.answer(f"✅ Категория **{new_cat}** деп өзгөртүлдү!", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("edit_comm:"))
async def edit_comm_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    exp_id = callback.data.split(":")[1]
    await state.update_data(exp_id=exp_id)
    await state.set_state(EditState.waiting_for_comment)
    await callback.message.answer("Жаңы комментарий киргизиңиз:")

@dp.message(EditState.waiting_for_comment)
async def process_new_comm(message: types.Message, state: FSMContext):
    new_comm = message.text.strip()
    data = await state.get_data()
    cursor.execute("UPDATE expenses SET comment = ? WHERE id = ?", (new_comm, data['exp_id']))
    conn.commit()
    await state.clear()
    await message.answer("✅ Комментарий өзгөртүлдү!", parse_mode="Markdown")

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

# --- Расходду кабыл алуу ---
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
        
        exp_id = cursor.lastrowid
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND month_period = ?", (user_id, month_period))
        month_total = cursor.fetchone()[0] or 0.0
        
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = ? AND month_period = ? AND category = ?", (user_id, month_period, category))
        cat_total = cursor.fetchone()[0] or 0.0
        
        reply = (
            f"✓ <b>{amount:.0f} · {category.capitalize()}</b>\n\n"
            f"В категории «{category.capitalize()}» за текущий период: <b>{cat_total:.0f}</b>\n"
            f"Всего потрачено: <b>{month_total:.0f}</b>"
        )
        
        action_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Изменить", callback_data=f"edit_opt:{exp_id}"),
                    InlineKeyboardButton(text="Отменить", callback_data=f"cancel_exp:{exp_id}")
                ]
            ]
        )
        
        await message.answer(reply, parse_mode="HTML", reply_markup=action_keyboard)
    else:
        await message.answer("⚠️ Формат туура эмес.\nМисалы: <code>Taxi 30</code> же <code>Taxi 30 comment</code>", parse_mode="HTML", reply_markup=get_reply_keyboard())

# --- Render үчүн Web Server жана ботту запуск кылуу ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    print("Бот иштеп жатат...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
