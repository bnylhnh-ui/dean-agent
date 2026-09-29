import os

import json

import sqlite3

import secrets

import hashlib

from datetime import datetime, timezone

from functools import wraps

from flask import (

    Flask,

    request,

    render_template_string,

    session,

    redirect,

    url_for,

    jsonify,

    Response,

    abort,

)

from openai import OpenAI

# ============================================================

# DEAN

# ============================================================

app = Flask(__name__)

OWNER_ID = os.environ.get("DEAN_OWNER_ID", "owner")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:

    raise RuntimeError(

        "Set OPENAI_API_KEY in Render Environment"

    )

SECRET_KEY = os.environ.get("SECRET_KEY")

if not SECRET_KEY:

    SECRET_KEY = hashlib.sha256(

        (

            "dean-session-v4:"

            + OPENAI_API_KEY

        ).encode()

    ).hexdigest()

app.secret_key = SECRET_KEY

app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SECURE=True,

    SESSION_COOKIE_SAMESITE="Lax",

    MAX_CONTENT_LENGTH=40000,

)

client = OpenAI(

    api_key=OPENAI_API_KEY

)

MODEL = os.environ.get(

    "OPENAI_MODEL",

    "gpt-5.6-luna"

)

DB_PATH = os.environ.get(

    "DB_PATH",

    "/data/dean.sqlite3"

)

# ============================================================

# DATABASE

# ============================================================

def db():

    parent = os.path.dirname(DB_PATH)

    if parent:

        os.makedirs(

            parent,

            exist_ok=True

        )

    con = sqlite3.connect(

        DB_PATH,

        timeout=30,

        check_same_thread=False

    )

    con.row_factory = sqlite3.Row

    con.execute(

        "PRAGMA busy_timeout=30000"

    )

    con.execute(

        "PRAGMA journal_mode=WAL"

    )

    con.execute("""

        CREATE TABLE IF NOT EXISTS messages (

            id INTEGER PRIMARY KEY,

            user_id TEXT NOT NULL,

            role TEXT NOT NULL,

            content TEXT NOT NULL,

            created TEXT NOT NULL

        )

    """)

    con.execute("""

        CREATE INDEX IF NOT EXISTS msg_user_idx

        ON messages(user_id,id)

    """)

    con.execute("""

        CREATE TABLE IF NOT EXISTS notes (

            id INTEGER PRIMARY KEY,

            user_id TEXT NOT NULL,

            content TEXT NOT NULL,

            created TEXT NOT NULL

        )

    """)

    con.execute("""

        CREATE INDEX IF NOT EXISTS note_user_idx

        ON notes(user_id,id)

    """)

    con.execute("""

        CREATE TABLE IF NOT EXISTS tasks (

            id INTEGER PRIMARY KEY,

            user_id TEXT NOT NULL,

            content TEXT NOT NULL,

            done INTEGER NOT NULL DEFAULT 0,

            created TEXT NOT NULL

        )

    """)

    con.execute("""

        CREATE INDEX IF NOT EXISTS task_user_idx

        ON tasks(user_id,id)

    """)

    con.commit()

    return con

# ============================================================

# BASIC HELPERS

# ============================================================

def uid():

    session["uid"] = OWNER_ID

    return OWNER_ID

def csrf():

    if "csrf" not in session:

        session["csrf"] = secrets.token_urlsafe(32)

    return session["csrf"]

def protected(fn):

    @wraps(fn)

    def wrapper(*args, **kwargs):

        supplied = (

            request.form.get("csrf", "")

            or request.headers.get(

                "X-CSRF-Token",

                ""

            )

        )

        if not supplied:

            abort(403)

        if not secrets.compare_digest(

            supplied,

            csrf()

        ):

            if request.path == "/chat":

                return jsonify(

                    error=(

                        "Session refreshed. "

                        "Please try again."

                    ),

                    code="csrf_expired"

                ), 403

            abort(403)

        return fn(*args, **kwargs)

    return wrapper

def now():

    return datetime.now(

        timezone.utc

    ).isoformat(

        timespec="seconds"

    )

# ============================================================

# MEMORY

# ============================================================

def save_note(content):

    content = " ".join(

        content.strip().split()

    )

    if not content:

        return False

    if len(content) > 1000:

        return False

    user = uid()

    with db() as con:

        exists = con.execute(

            """

            SELECT 1

            FROM notes

            WHERE user_id=?

            AND content=?

            LIMIT 1

            """,

            (

                user,

                content

            )

        ).fetchone()

        if exists:

            return False

        con.execute(

            """

            INSERT INTO notes(

                user_id,

                content,

                created

            )

            VALUES(?,?,?)

            """,

            (

                user,

                content,

                now()

            )

        )

    return True

def auto_remember(text):

    text = " ".join(

        text.strip().split()

    )

    if not text:

        return False

    if len(text) > 1000:

        return False

    triggers = (

        "תזכור",

        "תזכרי",

        "תשמור",

        "תשמרי",

        "שמור",

        "שמרי",

        "מהיום",

        "מעכשיו",

        "קוראים לי",

        "אני גר",

        "אני גרה",

        "אני אוהב",

        "אני אוהבת",

        "אני מעדיף",

        "אני מעדיפה",

        "אני רוצה שת",

        "אני רוצה ש",

        "חשוב לי ש",

        "אל תשכח",

        "אל תשכחי",

    )

    lower = text.lower()

    if not any(

        trigger in lower

        for trigger in triggers

    ):

        return False

    memory = text

    prefixes = (

        "תזכור ",

        "תזכרי ",

        "תשמור ",

        "תשמרי ",

        "שמור ",

        "שמרי ",

    )

    for prefix in prefixes:

        if lower.startswith(

            prefix.lower()

        ):

            memory = text[

                len(prefix):

            ].strip()

            break

    if not memory:

        return False

    return save_note(

        memory[:1000]

    )

# ============================================================

# TASKS

# ============================================================

def add_task(content):

    content = content.strip()

    if not content:

        return False

    if len(content) > 500:

        return False

    with db() as con:

        con.execute(

            """

            INSERT INTO tasks(

                user_id,

                content,

                created

            )

            VALUES(?,?,?)

            """,

            (

                uid(),

                content,

                now()

            )

        )

    return True

# ============================================================

# COMMANDS

# ============================================================

def command_reply(message):

    command, _, argument = (

        message.partition(" ")

    )

    command = command.lower().strip()

    argument = argument.strip()

    if command in (

        "/help",

        "/commands"

    ):

        return (

            "אפשר פשוט לדבר איתי רגיל.\n\n"

            "פקודות זמינות:\n"

            "/status\n"

            "/remember טקסט\n"

            "/notes\n"

            "/task טקסט\n"

            "/tasks\n"

            "/done מספר\n"

            "/facebook נושא"

        )

    if command == "/status":

        return (

            "DEAN פעיל.\n"

            "שיחה טבעית: פעילה\n"

            "היסטוריה: פעילה\n"

            "זיכרון קבוע: פעיל\n"

            "פתקים: פעילים\n"

            "משימות: פעילות\n"

            "חיפוש אינטרנט: פעיל\n"

            "פייסבוק: עדיין לא מחובר ישירות\n"

            "שליטה באייפד: עדיין לא מחוברת"

        )

    if command == "/remember":

        if not argument:

            return (

                "כתוב אחרי /remember "

                "מה אתה רוצה שאזכור."

            )

        if save_note(argument):

            return "זכרתי ושמרתי את זה."

        return (

            "המידע כבר שמור "

            "או שהוא ארוך מדי."

        )

    if command == "/notes":

        with db() as con:

            rows = con.execute(

                """

                SELECT id,content

                FROM notes

                WHERE user_id=?

                ORDER BY id DESC

                LIMIT 50

                """,

                (uid(),)

            ).fetchall()

        if not rows:

            return (

                "אין לי עדיין "

                "זיכרונות שמורים."

            )

        return "\n".join(

            f"{row['id']}. {row['content']}"

            for row in rows

        )

    if command == "/task":

        if not argument:

            return (

                "כתוב אחרי /task "

                "את המשימה."

            )

        if add_task(argument):

            return "המשימה נוספה."

        return (

            "לא הצלחתי להוסיף "

            "את המשימה."

        )

    if command == "/tasks":

        with db() as con:

            rows = con.execute(

                """

                SELECT id,content,done

                FROM tasks

                WHERE user_id=?

                ORDER BY id DESC

                LIMIT 50

                """,

                (uid(),)

            ).fetchall()

        if not rows:

            return "אין כרגע משימות."

        return "\n".join(

            (

                f"{row['id']}. "

                f"{'✅' if row['done'] else '⬜'} "

                f"{row['content']}"

            )

            for row in rows

        )

    if command == "/done":

        if not argument.isdecimal():

            return (

                "כתוב /done "

                "ואחריו מספר משימה."

            )

        with db() as con:

            cur = con.execute(

                """

                UPDATE tasks

                SET done=1

                WHERE id=?

                AND user_id=?

                """,

                (

                    int(argument),

                    uid()

                )

            )

        if cur.rowcount:

            return (

                "סימנתי את המשימה "

                "כבוצעה."

            )

        return (

            "לא מצאתי את המשימה."

        )

    if command == "/facebook":

        if not argument:

            return (

                "כתוב /facebook "

                "ואחריו נושא."

            )

        return (

            "כתוב פוסט קצר וטבעי "

            "בעברית לפייסבוק "

            "בנושא: "

            + argument

            + "."

        )

    return None

# ============================================================

# DEAN PERSONALITY / INSTRUCTIONS

# ============================================================

SYSTEM_INSTRUCTIONS = """

אתה DEAN.

אתה העוזר האישי של בניאל.

המטרה שלך היא לנהל עם בניאל שיחה טבעית ורציפה.

אל תתנהג כמו תפריט.

אל תציג אפשרויות בכל הודעה.

אל תציע רשימת אפשרויות אם בניאל לא ביקש אותה.

אל תשאל "איזה מהבאים אתה רוצה?" כאשר אפשר להבין את הכוונה.

דבר איתו כמו עוזר אישי אמיתי.

ענה בעברית טבעית.

היה ברור.

היה ישיר.

היה קצר כשאפשר.

אל תחזור על עצמך.

אל תסבך דברים פשוטים.

אם בניאל אומר:

"היי דין"

ענה לו כמו בן אדם.

אם בניאל אומר:

"מה נשמע?"

ענה לו כמו בן אדם.

אם בניאל מספר משהו,

המשך את השיחה באופן טבעי.

אם בניאל שואל שאלה,

ענה על השאלה.

אם הוא מבקש לבצע פעולה,

בדוק האם יש לך כלי מתאים.

אם אין לך כלי מתאים,

תגיד את זה ישירות.

לעולם אל תטען שביצעת פעולה

אם לא ביצעת אותה בפועל.

========================

זיכרון

========================

המערכת שומרת היסטוריית שיחה במסד הנתונים.

המערכת שומרת גם זיכרונות קבועים

במסד הנתונים תחת "הזיכרונות של בניאל".

כאשר מידע מופיע תחת

"הזיכרונות של בניאל",

זהו זיכרון קבוע.

אל תגיד שהזיכרון ייעלם

ברענון הדפדפן אם הוא מופיע

ברשימת הזיכרונות.

אל תגיד שהיסטוריית השיחה

נעלמת ברענון אם היא מופיעה

בהיסטוריה שסופקה לך.

כאשר בניאל אומר:

"תזכור..."

"תזכרי..."

"תשמור..."

"תשמרי..."

"שמור..."

"שמרי..."

"מהיום..."

"מעכשיו..."

או אומר בצורה ברורה

שהוא רוצה שתזכור מידע,

המערכת עשויה לשמור אותו

באופן אוטומטי.

אם המידע נשמר,

אל תשאל שוב אם הוא רוצה לשמור.

לדוגמה:

בניאל:

"תזכור שהמילה הסודית היא בננה."

תשובה נכונה:

"סבבה, זכרתי."

לא נכון:

"רוצה שאשמור את זה?"

לא נכון:

"רוצה שזה יהיה רק לשיחה?"

לא נכון:

"אם תרצה אני יכול לשמור."

כאשר בניאל שואל:

"אתה זוכר?"

בדוק את ההיסטוריה

ואת הזיכרונות שסופקו לך

וענה בהתאם.

אם המידע נמצא שם,

תגיד שאתה זוכר אותו.

אם הוא לא נמצא,

אל תמציא.

אל תיתן נאומי אבטחה

כאשר אין צורך בהם.

אם בניאל מנסה לשמור

סיסמה אמיתית,

מפתח API או מידע אבטחה רגיש,

הזהר אותו בקצרה.

========================

היסטוריית שיחה

========================

היסטוריית השיחה שסופקה לך

היא חלק מהשיחה עם בניאל.

השתמש בהקשר הקודם.

אל תתייחס לכל הודעה כאילו

היא שיחה חדשה.

אל תחזור לשאול דבר

שכבר נענה בהיסטוריה.

========================

חיפוש מידע

========================

כאשר בניאל מבקש מידע עדכני,

חדשות,

מחירים,

מוצרים,

אתרים,

חברות,

אירועים,

או מידע שיכול להשתנות,

השתמש בחיפוש האינטרנט

כאשר כלי החיפוש זמין.

כאשר אין צורך בחיפוש,

אל תחפש סתם.

========================

יכולות

========================

כרגע יש לך:

- שיחה עם AI

- היסטוריית שיחה

- זיכרון קבוע

- פתקים

- משימות

- חיפוש אינטרנט

יכולות נוספות כמו:

- פייסבוק

- WhatsApp

- אימייל

- יומן

- גלישה אוטומטית

- שליטה באייפד

- שליחת הודעות

- ביצוע פעולות באתרים

- APIs חיצוניים

- אוטומציות

דורשות חיבור וכלי מתאים.

אל תטען שהן מחוברות

אם הן לא מחוברות.

המטרה היא לבנות את DEAN

בהדרגה כעוזר אישי אמיתי

עם כלים וחיבורים נוספים.

"""

# ============================================================

# CHAT

# ============================================================

@app.post("/chat")

@protected

def chat():

    message = request.form.get(

        "message",

        ""

    ).strip()

    if not message:

        return jsonify(

            error="הודעה ריקה"

        ), 400

    if len(message) > 6000:

        return jsonify(

            error="ההודעה ארוכה מדי"

        ), 400

    user = uid()

    # --------------------------------------------------------

    # Commands

    # --------------------------------------------------------

    if message.startswith("/"):

        reply = command_reply(

            message

        )

        if reply is not None:

            with db() as con:

                con.execute(

                    """

                    INSERT INTO messages(

                        user_id,

                        role,

                        content,

                        created

                    )

                    VALUES(?,?,?,?)

                    """,

                    (

                        user,

                        "user",

                        message,

                        now()

                    )

                )

                con.execute(

                    """

                    INSERT INTO messages(

                        user_id,

                        role,

                        content,

                        created

                    )

                    VALUES(?,?,?,?)

                    """,

                    (

                        user,

                        "assistant",

                        reply,

                        now()

                    )

                )

            return jsonify(

                answer=reply,

                memory_saved=False

            )

    # --------------------------------------------------------

    # Automatic memory

    # --------------------------------------------------------

    memory_saved = auto_remember(

        message

    )

    # --------------------------------------------------------

    # Load history and memory

    # --------------------------------------------------------

    with db() as con:

        history = con.execute(

            """

            SELECT role,content

            FROM messages

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 40

            """,

            (user,)

        ).fetchall()[::-1]

        notes = con.execute(

            """

            SELECT content

            FROM notes

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 50

            """,

            (user,)

        ).fetchall()

        tasks = con.execute(

            """

            SELECT content,done

            FROM tasks

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 50

            """,

            (user,)

        ).fetchall()

    memory_text = "\n".join(

        "- " + row["content"]

        for row in notes

    )

    task_text = "\n".join(

        (

            "- "

            + (

                "[בוצע] "

                if row["done"]

                else "[פתוח] "

            )

            + row["content"]

        )

        for row in tasks

    )

    instructions = (

        SYSTEM_INSTRUCTIONS

        + "\n\n"

        + "הזיכרונות של בניאל:\n"

        + (

            memory_text

            if memory_text

            else "אין עדיין זיכרונות."

        )

        + "\n\n"

        + "המשימות של בניאל:\n"

        + (

            task_text

            if task_text

            else "אין כרגע משימות."

        )

    )

    # --------------------------------------------------------

    # Build conversation

    # --------------------------------------------------------

    model_input = []

    for row in history:

        if row["role"] not in (

            "user",

            "assistant"

        ):

            continue

        model_input.append(

            {

                "role": row["role"],

                "content": row["content"]

            }

        )

    model_input.append(

        {

            "role": "user",

            "content": message

        }

    )

    # --------------------------------------------------------

    # OpenAI Responses API

    # --------------------------------------------------------

    try:

        response = client.responses.create(

            model=MODEL,

            instructions=instructions,

            tools=[

                {

                    "type": "web_search"

                }

            ],

            input=model_input,

            max_output_tokens=2000

        )

        answer = (

            response.output_text.strip()

            if response.output_text

            else

            "לא התקבלה תשובה. נסה שוב."

        )

    except Exception:

        app.logger.exception(

            "OpenAI request failed"

        )

        return jsonify(

            error=(

                "לא הצלחתי להתחבר "

                "למודל כרגע. נסה שוב."

            )

        ), 502

    # --------------------------------------------------------

    # Save conversation

    # --------------------------------------------------------

    with db() as con:

        con.execute(

            """

            INSERT INTO messages(

                user_id,

                role,

                content,

                created

            )

            VALUES(?,?,?,?)

            """,

            (

                user,

                "user",

                message,

                now()

            )

        )

        con.execute(

            """

            INSERT INTO messages(

                user_id,

                role,

                content,

                created

            )

            VALUES(?,?,?,?)

            """,

            (

                user,

                "assistant",

                answer,

                now()

            )

        )

    return jsonify(

        answer=answer,

        memory_saved=bool(

            memory_saved

        )

    )

# ============================================================

# HOME

# ============================================================

@app.get("/")

def home():

    user = uid()

    with db() as con:

        messages = con.execute(

            """

            SELECT role,content

            FROM messages

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 60

            """,

            (user,)

        ).fetchall()[::-1]

        notes = con.execute(

            """

            SELECT id,content

            FROM notes

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 50

            """,

            (user,)

        ).fetchall()

        tasks = con.execute(

            """

            SELECT id,content,done

            FROM tasks

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 50

            """,

            (user,)

        ).fetchall()

    last_answer = next(

        (

            row["content"]

            for row in reversed(messages)

            if row["role"] == "assistant"

        ),

        ""

    )

    return render_template_string(

        HTML,

        messages=messages,

        notes=notes,

        tasks=tasks,

        csrf=csrf(),

        last_answer=last_answer

    )

# ============================================================

# CSRF

# ============================================================

@app.get("/csrf")

def refresh_csrf():

    uid()

    return jsonify(

        csrf=csrf()

    )

# ============================================================

# NOTES

# ============================================================

@app.post("/notes")

@protected

def add_note():

    content = request.form.get(

        "content",

        ""

    ).strip()

    if content:

        save_note(content)

    return redirect(

        url_for("home")

    )

@app.post("/notes/<int:item>/delete")

@protected

def del_note(item):

    with db() as con:

        con.execute(

            """

            DELETE FROM notes

            WHERE id=?

            AND user_id=?

            """,

            (

                item,

                uid()

            )

        )

    return redirect(

        url_for("home")

    )

# ============================================================

# TASKS

# ============================================================

@app.post("/tasks")

@protected

def add_task_route():

    content = request.form.get(

        "content",

        ""

    ).strip()

    if content:

        add_task(content)

    return redirect(

        url_for("home")

    )

@app.post("/tasks/<int:item>/toggle")

@protected

def toggle_task(item):

    with db() as con:

        con.execute(

            """

            UPDATE tasks

            SET done=1-done

            WHERE id=?

            AND user_id=?

            """,

            (

                item,

                uid()

            )

        )

    return redirect(

        url_for("home")

    )

@app.post("/tasks/<int:item>/delete")

@protected

def del_task(item):

    with db() as con:

        con.execute(

            """

            DELETE FROM tasks

            WHERE id=?

            AND user_id=?

            """,

            (

                item,

                uid()

            )

        )

    return redirect(

        url_for("home")

    )

# ============================================================

# EXPORT

# ============================================================

@app.get("/export")

def export():

    user = uid()

    with db() as con:

        data = {}

        for table in (

            "messages",

            "notes",

            "tasks"

        ):

            rows = con.execute(

                f"""

                SELECT *

                FROM {table}

                WHERE user_id=?

                ORDER BY id

                """,

                (user,)

            ).fetchall()

            data[table] = [

                dict(row)

                for row in rows

            ]

    return Response(

        json.dumps(

            data,

            ensure_ascii=False,

            indent=2

        ),

        mimetype="application/json",

        headers={

            "Content-Disposition":

                "attachment; filename=dean-backup.json",

            "Cache-Control":

                "no-store"

        }

    )

# ============================================================

# CLEAR

# ============================================================

@app.post("/clear")

@protected

def clear():

    with db() as con:

        for table in (

            "messages",

            "notes",

            "tasks"

        ):

            con.execute(

                f"""

                DELETE FROM {table}

                WHERE user_id=?

                """,

                (uid(),)

            )

    return redirect(

        url_for("home")

    )

# ============================================================

# HTML

# ============================================================

HTML = """

<!doctype html>

<html lang="he" dir="rtl">

<head>

<meta charset="utf-8">

<meta

name="viewport"

content="width=device-width,initial-scale=1"

>

<title>DEAN - העוזר של בניאל</title>

<style>

*{

box-sizing:border-box;

}

body{

margin:0;

background:#0b1020;

color:#eaf0ff;

font-family:system-ui,Arial;

}

header{

padding:20px;

background:#131b30;

border-bottom:1px solid #29334e;

}

.wrap{

max-width:1000px;

margin:auto;

padding:16px;

}

h1{

margin:0;

color:#83e5bb;

}

.grid{

display:grid;

grid-template-columns:minmax(0,2fr) minmax(240px,1fr);

gap:16px;

}

.panel{

background:#151e32;

border:1px solid #2a3654;

border-radius:15px;

padding:16px;

margin-bottom:15px;

}

.messages{

height:55vh;

overflow:auto;

display:flex;

flex-direction:column;

gap:12px;

}

.bubble{

white-space:pre-wrap;

overflow-wrap:anywhere;

padding:12px;

border-radius:12px;

max-width:95%;

}

.user{

background:#245f65;

align-self:flex-start;

}

.assistant{

background:#26314b;

align-self:flex-end;

}

textarea,

input{

width:100%;

padding:12px;

border:1px solid #43506a;

border-radius:10px;

background:#0c1528;

color:white;

font:inherit;

}

button,

.btn{

cursor:pointer;

border:0;

border-radius:10px;

padding:10px 15px;

background:#45c99b;

color:#09221a;

font:inherit;

font-weight:bold;

text-decoration:none;

display:inline-block;

}

button.secondary,

.btn.secondary{

background:#34435f;

color:white;

}

button.danger{

background:#793b47;

color:white;

}

.row{

display:flex;

gap:8px;

flex-wrap:wrap;

align-items:center;

margin-top:10px;

}

.item{

border-top:1px solid #34415c;

padding:10px 0;

overflow-wrap:anywhere;

}

.muted{

color:#aebbd4;

}

.error{

color:#ff9ca7;

}

.notice{

background:#343021;

padding:10px;

border-radius:9px;

color:#f3d58a;

}

@media(max-width:730px){

.grid{

grid-template-columns:1fr;

}

.messages{

height:48vh;

}

}

</style>

</head>

<body>

<header>

<div class="wrap">

<h1>DEAN ✦</h1>

<div class="muted">

העוזר האישי של בניאל

</div>

</div>

</header>

<div class="wrap">

<p class="notice">

פשוט דבר עם דין.

אין צורך להשתמש בפקודות.

</p>

<div class="grid">

<main>

<section class="panel">

<h2>שיחה עם דין</h2>

<div

id="messages"

class="messages"

aria-live="polite"

>

{% for m in messages %}

<div class="bubble {{m['role']}}">

<b>

{{ 'אתה' if m['role']=='user' else 'DEAN' }}

</b>

<br>

{{m['content']}}

</div>

{% endfor %}

</div>

<form

id="chat"

method="post"

action="/chat"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<textarea

name="message"

id="message"

rows="3"

maxlength="6000"

required

placeholder="דבר עם דין..."

></textarea>

<div class="row">

<button id="send">

שלח

</button>

<button

class="secondary"

type="button"

id="speak"

>

🎤 דבר

</button>

<button

class="secondary"

type="button"

id="read"

>

🔊 הקרא

</button>

<button

class="secondary"

type="button"

id="copy"

>

העתק תשובה

</button>

<a

class="btn secondary"

href="/export"

>

גיבוי

</a>

</div>

<p

id="status"

class="muted"

></p>

</form>

</section>

</main>

<aside>

<section class="panel">

<h2>📌 זיכרון</h2>

<form

method="post"

action="/notes"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<input

name="content"

maxlength="1000"

required

placeholder="מה דין צריך לזכור?"

>

<div class="row">

<button>

שמור

</button>

</div>

</form>

{% for n in notes %}

<div class="item">

{{n['content']}}

<form

method="post"

action="/notes/{{n['id']}}/delete"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<button

class="danger"

>

×

</button>

</form>

</div>

{% endfor %}

</section>

<section class="panel">

<h2>☑ משימות</h2>

<form

method="post"

action="/tasks"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<input

name="content"

maxlength="500"

required

placeholder="משימה חדשה"

>

<div class="row">

<button>

הוסף

</button>

</div>

</form>

{% for t in tasks %}

<div class="item">

{{'✅' if t['done'] else '⬜'}}

{{t['content']}}

<div class="row">

<form

method="post"

action="/tasks/{{t['id']}}/toggle"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<button class="secondary">

{{'בטל' if t['done'] else 'סיימתי'}}

</button>

</form>

<form

method="post"

action="/tasks/{{t['id']}}/delete"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<button class="danger">

מחק

</button>

</form>

</div>

</div>

{% endfor %}

</section>

<section class="panel">

<h2>פרטיות</h2>

<p class="muted">

אל תכניס סיסמאות או מפתחות API לשיחה.

</p>

<form

method="post"

action="/clear"

onsubmit="return confirm('למחוק את כל המידע?')"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<button class="danger">

מחק הכול

</button>

</form>

</section>

</aside>

</div>

</div>

<script>

const box =

document.getElementById(

"messages"

);

box.scrollTop =

box.scrollHeight;

const form =

document.getElementById(

"chat"

);

const status =

document.getElementById(

"status"

);

let last =

{{last_answer|tojson}};

async function sendMessage(fd){

let response =

await fetch(

"/chat",

{

method:"POST",

body:fd,

credentials:"same-origin"

}

);

let data =

await response.json();

if(

response.status === 403 &&

data.code === "csrf_expired"

){

const tokenResponse =

await fetch(

"/csrf",

{

credentials:"same-origin",

cache:"no-store"

}

);

if(!tokenResponse.ok){

throw new Error(

"יש לרענן את העמוד"

);

}

const token =

await tokenResponse.json();

form.elements.csrf.value =

token.csrf;

fd.set(

"csrf",

token.csrf

);

response =

await fetch(

"/chat",

{

method:"POST",

body:fd,

credentials:"same-origin"

}

);

data =

await response.json();

}

if(!response.ok){

throw new Error(

data.error || "שגיאה"

);

}

return data;

}

form.addEventListener(

"submit",

async event => {

event.preventDefault();

const fd =

new FormData(form);

const message =

String(

fd.get("message") || ""

);

if(!message.trim()){

return;

}

const send =

document.getElementById(

"send"

);

send.disabled = true;

status.className =

"muted";

status.textContent =

"דין חושב...";

add(

"user",

message

);

document.getElementById(

"message"

).value = "";

try{

const data =

await sendMessage(fd);

last =

data.answer;

add(

"assistant",

last

);

status.textContent =

data.memory_saved

? "נשמר בזיכרון."

: "";

}

catch(error){

status.className =

"error";

status.textContent =

"שגיאה: "

+ error.message;

document.getElementById(

"message"

).value =

message;

}

finally{

send.disabled = false;

}

});

function add(

role,

text

){

const div =

document.createElement(

"div"

);

div.className =

"bubble " + role;

const b =

document.createElement(

"b"

);

b.textContent =

role === "user"

? "אתה"

: "DEAN";

div.append(

b,

document.createElement("br"),

document.createTextNode(text)

);

box.append(div);

box.scrollTop =

box.scrollHeight;

}

document.getElementById(

"copy"

).onclick =

async () => {

if(!last){

alert(

"אין עדיין תשובה"

);

return;

}

try{

await navigator.clipboard.writeText(

last

);

alert("הועתק");

}

catch(error){

alert(

"לא הצלחתי להעתיק"

);

}

};

document.getElementById(

"read"

).onclick =

() => {

if(!last){

return;

}

const utterance =

new SpeechSynthesisUtterance(

last

);

utterance.lang =

"he-IL";

speechSynthesis.cancel();

speechSynthesis.speak(

utterance

);

};

document.getElementById(

"speak"

).onclick =

() => {

const Recognition =

window.SpeechRecognition ||

window.webkitSpeechRecognition;

if(!Recognition){

alert(

"הדפדפן לא תומך בהכתבה כאן"

);

return;

}

const recognition =

new Recognition();

recognition.lang =

"he-IL";

recognition.onresult =

event => {

document.getElementById(

"message"

).value =

event.results[0][0].transcript;

};

recognition.start();

};

</script>

</body>

</html>

"""

# ============================================================

# START

# ============================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=int(

            os.environ.get(

                "PORT",

                "10000"

            )

        )

    )
