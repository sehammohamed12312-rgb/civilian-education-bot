import os
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8406743511

db = sqlite3.connect("library.db", check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER, name TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER, file_id TEXT, caption TEXT)""")
db.commit()


def is_admin(user_id):
    return user_id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_subjects(update, context)


async def show_subjects(update, context):
    rows = db.execute("SELECT id, name FROM subjects").fetchall()
    buttons = [
        [InlineKeyboardButton(name, callback_data=f"s_{sid}")]
        for sid, name in rows
    ]
    if not buttons:
        buttons = [[InlineKeyboardButton("لا توجد مواد حاليًا", callback_data="none")]]
    markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📚 اختار المادة:", reply_markup=markup)
    else:
        await update.message.reply_text("📚 مكتبة المحاضرات\nاختار المادة:", reply_markup=markup)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    buttons = [
        [InlineKeyboardButton("➕ إضافة مادة", callback_data="add_subject")],
        [InlineKeyboardButton("➕ إضافة فصل", callback_data="add_chapter")],
        [InlineKeyboardButton("🎥 رفع فيديو", callback_data="add_video")],
        [InlineKeyboardButton("📚 عرض المواد", callback_data="show_admin")]
    ]
    await update.message.reply_text(
        "⚙️ لوحة تحكم الإدارة",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "none":
        return

    if data.startswith("s_"):
        sid = int(data[2:])
        rows = db.execute(
            "SELECT id, name FROM chapters WHERE subject_id=?", (sid,)
        ).fetchall()
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"c_{cid}")]
            for cid, name in rows
        ]
        buttons.append([InlineKeyboardButton("⬅️ رجوع", callback_data="home")])
        await q.edit_message_text(
            "📖 اختار الفصل:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("c_"):
        cid = int(data[2:])
        rows = db.execute(
            "SELECT file_id, caption FROM videos WHERE chapter_id=?", (cid,)
        ).fetchall()
        if not rows:
            await q.edit_message_text("لا توجد فيديوهات في هذا الفصل حاليًا.")
            return
        await q.edit_message_text("🎬 جاري إرسال فيديوهات الفصل...")
        for file_id, caption in rows:
            await context.bot.send_video(
                chat_id=q.message.chat_id,
                video=file_id,
                caption=caption or ""
            )

    elif data == "home":
        await show_subjects(update, context)

    elif data == "add_subject" and is_admin(q.from_user.id):
        context.user_data["action"] = "subject"
        await q.message.reply_text("اكتب اسم المادة الجديدة:")

    elif data == "add_chapter" and is_admin(q.from_user.id):
        rows = db.execute("SELECT id, name FROM subjects").fetchall()
        buttons = [
            [InlineKeyboardButton(name, callback_data=f"picksub_{sid}")]
            for sid, name in rows
        ]
        await q.message.reply_text(
            "اختار المادة:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("picksub_") and is_admin(q.from_user.id):
        context.user_data["subject_id"] = int(data.split("_")[1])
        context.user_data["action"] = "chapter"
        await q.message.reply_text("اكتب اسم الفصل الجديد:")

    elif data == "add_video" and is_admin(q.from_user.id):
        rows = db.execute(
            """SELECT chapters.id, subjects.name, chapters.name
            FROM chapters JOIN subjects ON chapters.subject_id=subjects.id"""
        ).fetchall()
        buttons = [
            [InlineKeyboardButton(
                f"{subject} - {chapter}", callback_data=f"pickchap_{cid}"
            )]
            for cid, subject, chapter in rows
        ]
        if not buttons:
            await q.message.reply_text("أضف مادة وفصل أولًا.")
            return
        await q.message.reply_text(
            "اختار الفصل الذي تريد رفع الفيديو فيه:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("pickchap_") and is_admin(q.from_user.id):
        context.user_data["chapter_id"] = int(data.split("_")[1])
        context.user_data["action"] = "video"
        await q.message.reply_text("ابعت الفيديو الآن كرسالة فيديو 📹")


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("action")

    if action == "subject":
        db.execute("INSERT INTO subjects(name) VALUES(?)", (update.message.text,))
        db.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ تمت إضافة المادة بنجاح.")

    elif action == "chapter":
        sid = context.user_data["subject_id"]
        db.execute(
            "INSERT INTO chapters(subject_id, name) VALUES(?,?)",
            (sid, update.message.text)
        )
        db.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ تمت إضافة الفصل بنجاح.")

    elif action == "video" and update.message.video:
        cid = context.user_data["chapter_id"]
        file_id = update.message.video.file_id
        caption = update.message.caption or ""
        db.execute(
            "INSERT INTO videos(chapter_id, file_id, caption) VALUES(?,?,?)",
            (cid, file_id, caption)
        )
        db.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ تم حفظ الفيديو بنجاح.")

    elif action == "video":
        await update.message.reply_text("من فضلك ابعت الفيديو باستخدام زر إرفاق فيديو.")


async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    rows = db.execute("SELECT id, name FROM subjects").fetchall()
    if not rows:
        await update.callback_query.message.reply_text("لا توجد مواد.")
        return
    text = "\n".join(f"📚 {name}" for _, name in rows)
    await update.callback_query.message.reply_text(text)


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(
        filters.TEXT | filters.VIDEO, receive
    ))
    app.run_polling()


if __name__ == "__main__":
    main()
