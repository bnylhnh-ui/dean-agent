import os

import json

import sqlite3

import secrets

import hashlib

from datetime import datetime, timezone

from functools import wraps

from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, Response, abort

from openai import OpenAI

app = Flask(__name__)

# Single-owner app: the owner id survives browser/cookie resets.

OWNER_ID = os.environ.get("DEAN_OWNER_ID", "owner")

secret = os.environ.get("SECRET_KEY")

if not secret:

    api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:

        raise RuntimeError("Set OPENAI_API_KEY in Render Environment")

    secret = hashlib.sha256(("dean-session-v2:" + api_key).encode()).hexdigest()

app.secret_key = secret

app.config.update(

    SESSION_COOKIE_HTTPONLY=True,

    SESSION_COOKIE_SECURE=True,

    SESSION_COOKIE_SAMESITE="Lax",

    MAX_CONTENT_LENGTH=40000,

)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

# IMPORTANT:

# On Render, set DB_PATH to a path on a Persistent Disk,

# for example /data/dean.sqlite3.

DB_PATH = os.environ.get("DB_PATH", "/data/dean.sqlite3")

def db():

    parent = os.path.dirname(DB_PATH)

    if parent:

        os.makedirs(parent, exist_ok=True)

    con = sqlite3.connect(DB_PATH, timeout=15)

    con.row_factory = sqlite3.Row

    con.execute("PRAGMA busy_timeout=15000")

    con.execute("""

        CREATE TABLE IF NOT EXISTS messages (

            id INTEGER PRIMARY KEY,

            user_id TEXT NOT NULL,

            role TEXT NOT NULL,

            content TEXT NOT NULL,

            created TEXT NOT NULL

        )

    """)

    con.execute(

        "CREATE INDEX IF NOT EXISTS msg_user_idx ON messages(user_id,id)"

    )

    con.execute("""

        CREATE TABLE IF NOT EXISTS notes (

            id INTEGER PRIMARY KEY,

            user_id TEXT NOT NULL,

            content TEXT NOT NULL,

            created TEXT NOT NULL

        )

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

    return con

def uid():

    # Always use the same owner id.

    # Browser cookies no longer create a new user.

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

            or request.headers.get("X-CSRF-Token", "")

        )

        if not secrets.compare_digest(supplied, csrf()):

            if request.path == "/chat":

                return jsonify(

                    error="Session refreshed. Please try again.",

                    code="csrf_expired"

                ), 403

            abort(403)

        return fn(*args, **kwargs)

    return wrapper

def now():

    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def save_note(content):

    content = content.strip()

    if not content or len(content) > 1000:

        return False

    with db() as con:

        # Don't save the exact same memory repeatedly.

        exists = con.execute(

            "SELECT 1 FROM notes WHERE user_id=? AND content=? LIMIT 1",

            (uid(), content),

        ).fetchone()

        if exists:

            return False

        con.execute(

            """

            INSERT INTO notes(user_id,content,created)

            VALUES(?,?,?)

            """,

            (uid(), content, now()),

        )

    return True

def auto_remember(text):

    """

    Lightweight automatic memory.

    It stores clear personal/preference statements,

    rather than saving every sentence.

    """

    text = " ".join(text.split())

    if not text or len(text) > 1000:

        return []

    triggers = (

        "תזכור",

        "תזכרי",

        "מהיום",

        "מעכשיו",

        "קוראים לי",

        "אני גר",

        "אני גרה",

        "אני אוהב",

        "אני אוהבת",

        "אני לא אוהב",

        "אני לא אוהבת",

        "אני מעדיף",

        "אני מעדיפה",

        "אני רוצה ש",

        "אני רוצה שת",

        "חשוב לי ש",

        "תמיד ת",

        "אל תשכח",

        "אל תשכחי",

    )

    lower_text = text.lower()

    if not any(trigger in lower_text for trigger in triggers):

        return []

    candidates = []

    if lower_text.startswith(("תזכור", "תזכרי")):

        memory = (

            text.split(" ", 1)[1].strip()

            if " " in text

            else ""

        )

    else:

        memory = text

    if memory and len(memory) >= 3:

        candidates.append(memory[:1000])

    saved = []

    for memory in candidates[:2]:

        if save_note(memory):

            saved.append(memory)

    return saved

HTML = """<!doctype html>

<html lang="he" dir="rtl">

<head>

<meta charset="utf-8">

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>DEAN - העוזר של בניאל</title>

<style>

:root{

font-family:system-ui,Arial;

color-scheme:dark

}

*{

box-sizing:border-box

}

body{

margin:0;

background:#0b1020;

color:#eaf0ff

}

header{

padding:20px;

background:#131b30;

border-bottom:1px solid #29334e

}

h1{

margin:0;

color:#83e5bb

}

small,.muted{

color:#aebbd4

}

.wrap{

max-width:960px;

margin:auto;

padding:16px

}

.grid{

display:grid;

grid-template-columns:minmax(0,2fr) minmax(240px,1fr);

gap:16px

}

.panel{

background:#151e32;

border:1px solid #2a3654;

border-radius:15px;

padding:16px;

margin-bottom:15px

}

.messages{

height:52vh;

overflow:auto;

display:flex;

flex-direction:column;

gap:12px

}

.bubble{

white-space:pre-wrap;

overflow-wrap:anywhere;

padding:12px;

border-radius:12px;

max-width:95%

}

.user{

background:#245f65;

align-self:flex-start

}

.assistant{

background:#26314b;

align-self:flex-end

}

textarea,input{

width:100%;

padding:12px;

border:1px solid #43506a;

border-radius:10px;

background:#0c1528;

color:white;

font:inherit

}

button,.btn{

cursor:pointer;

border:0;

border-radius:10px;

padding:10px 15px;

background:#45c99b;

color:#09221a;

font:inherit;

font-weight:bold;

text-decoration:none;

display:inline-block

}

button.secondary,.btn.secondary{

background:#34435f;

color:white

}

button.danger{

background:#793b47;

color:white

}

.row{

display:flex;

gap:8px;

flex-wrap:wrap;

align-items:center;

margin-top:10px

}

.item{

border-top:1px solid #34415c;

padding:10px 0;

overflow-wrap:anywhere

}

.item form{

display:inline

}

.error{

color:#ff9ca7

}

.notice{

background:#343021;

padding:10px;

border-radius:9px;

color:#f3d58a

}

a{

color:#9ae4ff

}

@media(max-width:730px){

.grid{

grid-template-columns:1fr

}

.messages{

height:43vh

}

}

</style>

</head>

<body>

<header>

<div class="wrap">

<h1>DEAN ✦</h1>

<small>

העוזר האישי של בניאל · צ'אט, פתקים, משימות והכנת פוסטים

</small>

</div>

</header>

<div class="wrap">

<p class="notice">

הזיכרון האוטומטי פעיל.

הזיכרון נשמר במסד הנתונים.

ב-Render יש להגדיר DB_PATH על Persistent Disk כדי שהמידע יישאר גם אחרי אתחול.

</p>

<div class="grid">

<main>

<section class="panel">

<h2>שיחה עם דין</h2>

<p class="muted">

פקודות:

 /help · /status · /remember · /task · /tasks · /notes · /done · /facebook

</p>

<div id="messages" class="messages" aria-live="polite">

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

<form id="chat" method="post" action="/chat">

<input type="hidden" name="csrf" value="{{csrf}}">

<textarea

name="message"

id="message"

rows="3"

maxlength="6000"

required

placeholder="דבר עם דין בעברית..."

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

<a

class="btn secondary"

href="/export"

>

ייצוא המידע שלי

</a>

</div>

<p id="status" class="muted"></p>

</form>

</section>

<section class="panel">

<h2>פייסבוק אישי</h2>

<p>

בקש מדין להכין פוסט,

העתק אותו ופתח את פייסבוק.

הפרסום עצמו נעשה על ידך.

</p>

<div class="row">

<button

class="secondary"

type="button"

id="copy"

>

העתק תשובה אחרונה

</button>

<a

class="btn secondary"

href="https://www.facebook.com/"

target="_blank"

rel="noopener noreferrer"

>

פתח פייסבוק ↗

</a>

</div>

</section>

</main>

<aside>

<section class="panel">

<h2>📌 פתקים</h2>

<form method="post" action="/notes">

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

שמור פתק

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

aria-label="מחק פתק"

>

×

</button>

</form>

</div>

{% endfor %}

</section>

<section class="panel">

<h2>☑ משימות</h2>

<form method="post" action="/tasks">

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

הוסף משימה

</button>

</div>

</form>

{% for t in tasks %}

<div class="item">

{{ '✅' if t['done'] else '⬜' }}

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

{{'בטל סימון' if t['done'] else 'סיימתי'}}

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

פעולות משמעותיות דורשות אישור מפורש.

</p>

<form

method="post"

action="/clear"

onsubmit="return confirm('למחוק את כל השיחות, הפתקים והמשימות שלך?')"

>

<input

type="hidden"

name="csrf"

value="{{csrf}}"

>

<button class="danger">

מחק את כל המידע שלי

</button>

</form>

</section>

</aside>

</div>

</div>

<script>

const box=document.getElementById('messages');

box.scrollTop=box.scrollHeight;

const form=document.getElementById('chat');

const status=document.getElementById('status');

let last={{last_answer|tojson}};

async function sendMessage(fd){

let r=await fetch(

'/chat',

{

method:'POST',

body:fd,

credentials:'same-origin'

}

);

let data=await r.json();

if(

r.status===403 &&

data.code==='csrf_expired'

){

const t=await fetch(

'/csrf',

{

credentials:'same-origin',

cache:'no-store'

}

);

if(!t.ok)

throw Error('יש לרענן את העמוד');

const j=await t.json();

form.elements.csrf.value=j.csrf;

fd.set('csrf',j.csrf);

r=await fetch(

'/chat',

{

method:'POST',

body:fd,

credentials:'same-origin'

}

);

data=await r.json();

}

if(!r.ok)

throw Error(data.error||'שגיאה');

return data;

}

form.addEventListener(

'submit',

async e=>{

e.preventDefault();

const fd=new FormData(form);

const message=String(

fd.get('message')||''

);

if(!message.trim())

return;

const send=document.getElementById('send');

send.disabled=true;

status.className='muted';

status.textContent='דין חושב...';

add('user',message);

document.getElementById('message').value='';

try{

const data=await sendMessage(fd);

last=data.answer;

add('assistant',last);

status.textContent=

data.memory_saved

?'נשמר בזיכרון.'

:'';

}

catch(err){

status.textContent=

'שגיאה: '+

err.message+

' — נסה לרענן את העמוד';

status.className='error';

document.getElementById('message').value=message;

}

finally{

send.disabled=false;

}

});

function add(role,text){

const div=document.createElement('div');

div.className='bubble '+role;

const b=document.createElement('b');

b.textContent=

role==='user'

?'אתה'

:'DEAN';

div.append(

b,

document.createElement('br'),

document.createTextNode(text)

);

box.append(div);

box.scrollTop=box.scrollHeight;

}

document.getElementById('copy').onclick=

async()=>{

if(!last)

return alert('אין עדיין תשובה');

try{

await navigator.clipboard.writeText(last);

alert('הועתק');

}

catch(e){

alert('לא הצלחתי להעתיק');

}

};

document.getElementById('read').onclick=()=>{

if(!last)

return;

const u=

new SpeechSynthesisUtterance(last);

u.lang='he-IL';

speechSynthesis.cancel();

speechSynthesis.speak(u);

};

document.getElementById('speak').onclick=()=>{

const R=

window.SpeechRecognition||

window.webkitSpeechRecognition;

if(!R)

return alert(

'הדפדפן הזה לא תומך בהכתבה כאן'

);

const r=new R();

r.lang='he-IL';

r.onresult=e=>

document.getElementById('message').value=

e.results[0][0].transcript;

r.start();

};

</script>

</body>

</html>"""

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

            LIMIT 40

            """,

            (user,),

        ).fetchall()[::-1]

        notes = con.execute(

            """

            SELECT id,content

            FROM notes

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 30

            """,

            (user,),

        ).fetchall()

        tasks = con.execute(

            """

            SELECT id,content,done

            FROM tasks

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 50

            """,

            (user,),

        ).fetchall()

    last_answer = next(

        (

            m["content"]

            for m in reversed(messages)

            if m["role"] == "assistant"

        ),

        "",

    )

    return render_template_string(

        HTML,

        messages=messages,

        notes=notes,

        tasks=tasks,

        csrf=csrf(),

        last_answer=last_answer,

    )

@app.get("/csrf")

def refresh_csrf():

    uid()

    return jsonify(

        csrf=csrf()

    )

def command_reply(message,user):

    command,_,argument=message.partition(" ")

    command=command.lower()

    argument=argument.strip()

    if command in ("/help","/commands"):

        return (

            "פקודות DEAN\n"

            "/help — כל הפקודות\n"

            "/status — יכולות קיימות\n"

            "/remember טקסט — שמור זיכרון\n"

            "/notes — הצג זיכרונות\n"

            "/task טקסט — הוסף משימה\n"

            "/tasks — הצג משימות\n"

            "/done מספר — סמן משימה כבוצעה\n"

            "/facebook נושא — כתוב טיוטת פוסט\n"

            "אפשר גם לדבר איתי רגיל בעברית."

        )

    if command=="/status":

        return (

            "פעיל: שיחה עם AI, "

            "היסטוריית שיחה, "

            "זיכרון אוטומטי, "

            "פתקים, "

            "משימות, "

            "גיבוי והכנת פוסטים.\n"

            "לא מחובר: פרסום עצמאי בפייסבוק, "

            "דוא״ל, יומן, גלישה עצמאית "

            "ושליטה באייפד."

        )

    if command in ("/remember","/task"):

        limit=1000 if command=="/remember" else 500

        if not argument or len(argument)>limit:

            return (

                f"כתוב {command} ואחריו טקסט "

                f"(עד {limit} תווים)."

            )

        if command=="/remember":

            save_note(argument)

            return "נשמר בזיכרון."

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

                    user,

                    argument,

                    now()

                ),

            )

        return "המשימה נוספה."

    if command in ("/notes","/tasks"):

        table="notes" if command=="/notes" else "tasks"

        with db() as con:

            rows=con.execute(

                "SELECT id,content"+

                (",done" if table=="tasks" else "")+

                f"""

                FROM {table}

                WHERE user_id=?

                ORDER BY id DESC

                LIMIT 40

                """,

                (user,),

            ).fetchall()

        return "\n".join(

            f"{r['id']}. "+

            (

                ("✓ " if r["done"] else "□ ")

                if table=="tasks"

                else ""

            )+

            r["content"]

            for r in rows

        ) or "אין עדיין פריטים."

    if command=="/done":

        if argument.isdecimal():

            with db() as con:

                cur=con.execute(

                    """

                    UPDATE tasks

                    SET done=1

                    WHERE id=?

                    AND user_id=?

                    """,

                    (

                        int(argument),

                        user

                    ),

                )

            return (

                "המשימה סומנה כבוצעה."

                if cur.rowcount

                else

                "לא נמצאה משימה עם המספר הזה."

            )

        return (

            "כתוב /tasks לקבלת מספרי המשימות "

            "ואז /done מספר."

        )

    if command=="/facebook":

        if not argument:

            return (

                "כתוב /facebook ואחריו "

                "נושא הפוסט."

            )

        return (

            "כתוב טיוטת פוסט קצרה בעברית "

            "לפייסבוק האישי שלי בנושא: "

            + argument +

            ". החזר רק טיוטה לפרסום ידני."

        )

    return "פקודה לא מוכרת. כתוב /help."

@app.post("/chat")

@protected

def chat():

    message=request.form.get(

        "message",

        ""

    ).strip()

    if not message or len(message)>6000:

        return jsonify(

            error="הודעה ריקה או ארוכה מדי"

        ),400

    user=uid()

    if message.startswith("/"):

        reply=command_reply(

            message,

            user

        )

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

                ),

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

                ),

            )

        return jsonify(

            answer=reply,

            memory_saved=False

        )

    # Automatic memory.

    memories=auto_remember(

        message

    )

    with db() as con:

        history=con.execute(

            """

            SELECT role,content

            FROM messages

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 20

            """,

            (user,),

        ).fetchall()[::-1]

        notes=con.execute(

            """

            SELECT content

            FROM notes

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 20

            """,

            (user,),

        ).fetchall()

        tasks=con.execute(

            """

            SELECT content,done

            FROM tasks

            WHERE user_id=?

            ORDER BY id DESC

            LIMIT 30

            """,

            (user,),

        ).fetchall()

    instructions=(

        "אתה DEAN, העוזר האישי של בניאל. "

        "ענה בעברית טבעית, ברורה וקצרה. "

        "אתה יכול להשתמש בזיכרונות ובמשימות שסופקו לך. "

        "אל תטען שביצעת פעולה שלא ביצעת. "

        "אין לך גישה עצמאית לפייסבוק, "

        "לחשבונות, לגלישה חיה או לשינוי קוד. "

        "פעולות משמעותיות דורשות אישור מפורש. "

        "זיכרונות שמורים:\n"+

        "\n".join(

            "- "+n["content"]

            for n in notes

        )+

        "\nמשימות:\n"+

        "\n".join(

            (

                "[בוצע] "

                if t["done"]

                else

                "[פתוח] "

            )+

            t["content"]

            for t in tasks

        )

    )

    try:

        response=client.responses.create(

            model=MODEL,

            instructions=instructions,

            input=[

                {

                    "role":m["role"],

                    "content":m["content"]

                }

                for m in history

            ]+

            [

                {

                    "role":"user",

                    "content":message

                }

            ],

            max_output_tokens=1200,

        )

        answer=(

            response.output_text.strip()

            or

            "לא התקבלה תשובה. נסה שוב."

        )

    except Exception:

        app.logger.exception(

            "OpenAI request failed"

        )

        return jsonify(

            error=(

                "לא הצלחתי להתחבר "

                "למודל כרגע. "

                "נסה שוב מאוחר יותר."

            )

        ),502

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

            ),

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

            ),

        )

    return jsonify(

        answer=answer,

        memory_saved=bool(memories)

    )

@app.post("/notes")

@protected

def add_note():

    content=request.form.get(

        "content",

        ""

    ).strip()

    if content and len(content)<=1000:

        save_note(

            content

        )

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

            ),

        )

    return redirect(

        url_for("home")

    )

@app.post("/tasks")

@protected

def add_task():

    content=request.form.get(

        "content",

        ""

    ).strip()

    if content and len(content)<=500:

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

                ),

            )

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

            ),

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

            ),

        )

    return redirect(

        url_for("home")

    )

@app.get("/export")

def export():

    user=uid()

    with db() as con:

        data={

            name:[

                dict(r)

                for r in con.execute(

                    f"""

                    SELECT *

                    FROM {name}

                    WHERE user_id=?

                    ORDER BY id

                    """,

                    (user,),

                ).fetchall()

            ]

            for name

            in (

                "messages",

                "notes",

                "tasks"

            )

        }

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

                "no-store",

        },

    )

@app.post("/clear")

@protected

def clear():

    with db() as con:

        for name in (

            "messages",

            "notes",

            "tasks"

        ):

            con.execute(

                f"""

                DELETE FROM {name}

                WHERE user_id=?

                """,

                (uid(),)

            )

    return redirect(

        url_for("home")

    )

if __name__=="__main__":

    app.run(

        host="0.0.0.0",

        port=int(

            os.environ.get(

                "PORT",

                "10000"

            )

        ),

    )
