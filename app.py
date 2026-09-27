import os
import json
import sqlite3
import secrets
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, Response, abort
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=40_000)
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
DB_PATH = os.environ.get('DB_PATH', '/tmp/dean.sqlite3')
MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5-mini')

def db():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL)')
    con.execute('CREATE INDEX IF NOT EXISTS msg_user_idx ON messages(user_id,id)')
    con.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, content TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL)')
    return con

def uid():
    if 'uid' not in session:
        session['uid'] = secrets.token_urlsafe(24)
    return session['uid']

def csrf():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']

def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not secrets.compare_digest(request.form.get('csrf', '') or request.headers.get('X-CSRF-Token', ''), csrf()):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

HTML = '''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>DEAN â ××¢×××¨ ×©× ×× ×××</title>
<style>
:root{font-family:system-ui,Arial;color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#eaf0ff}header{padding:20px;background:#131b30;border-bottom:1px solid #29334e}h1{margin:0;color:#83e5bb}small,.muted{color:#aebbd4}.wrap{max-width:960px;margin:auto;padding:16px}.grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:16px}.panel{background:#151e32;border:1px solid #2a3654;border-radius:15px;padding:16px;margin-bottom:15px}.messages{height:52vh;overflow:auto;display:flex;flex-direction:column;gap:12px}.bubble{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;border-radius:12px;max-width:95%}.user{background:#245f65;align-self:flex-start}.assistant{background:#26314b;align-self:flex-end}textarea,input{width:100%;padding:12px;border:1px solid #43506a;border-radius:10px;background:#0c1528;color:white;font:inherit}button,.btn{cursor:pointer;border:0;border-radius:10px;padding:10px 15px;background:#45c99b;color:#09221a;font:inherit;font-weight:bold;text-decoration:none;display:inline-block}button.secondary,.btn.secondary{background:#34435f;color:white}button.danger{background:#793b47;color:white}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}.item{border-top:1px solid #34415c;padding:10px 0;overflow-wrap:anywhere}.item form{display:inline}.error{color:#ff9ca7}.notice{background:#343021;padding:10px;border-radius:9px;color:#f3d58a}label{display:block;margin:10px 0}a{color:#9ae4ff}@media(max-width:730px){.grid{grid-template-columns:1fr}.messages{height:43vh}}
</style></head><body><header><div class="wrap"><h1>DEAN â¦</h1><small>××¢×××¨ ××××©× ×©× ×× ××× Â· ×¦'××, ×¤×ª×§××, ××©××××ª ×××× ×ª ×¤××¡×××</small></div></header><div class="wrap"><p class="notice">×××××¨×× × ×©××¨ ×××¤××¤× ××× ××××¡× ×× ×ª×× ×× ×©× ××©×¨×ª. ××©×¨×ª Render ××× ×× ××× ×¢××× ××××××§ ××¤×¨××¡× ××××© ×× ×××ª×××. ××× ×¢×××× ×××××¨ ××××××× ××¤×××¡×××§.</p><div class="grid"><main><section class="panel"><h2>×©××× ×¢× ×××</h2><p class="muted">×¤×§××××ª ××××¨××ª: /help Â· /status Â· /remember Â· /task Â· /tasks Â· /notes Â· /done Â· /facebook</p><div id="messages" class="messages" aria-live="polite">{% for m in messages %}<div class="bubble {{m['role']}}"><b>{{ '××ª×' if m['role']=='user' else 'DEAN' }}</b><br>{{m['content']}}</div>{% endfor %}</div><form id="chat" method="post" action="/chat"><input type="hidden" name="csrf" value="{{csrf}}"><textarea name="message" id="message" rows="3" maxlength="6000" required placeholder="×××¨ ×¢× ××× ××¢××¨××ª..."></textarea><div class="row"><button id="send">×©××</button><button class="secondary" type="button" id="speak" title="×××ª×× ×§××××ª ×××¤××¤× ×× × ×ª××××">ð¤ ×××¨</button><button class="secondary" type="button" id="read" title="××§×¨××ª ×ª×©×××">ð ××§×¨×</button><a class="btn secondary" href="/export">×××¦×× ×××××¢ ×©××</a></div><p id="status" class="muted"></p></form></section><section class="panel"><h2>×¤×××¡×××§ ×××©×</h2><p>××§×© ×××× ×××ª×× ×¤××¡×. ××¢×ª×§ ×××ª× ××××¥ ×¢× ×¤×ª×××ª ×¤×××¡×××§. ××¤×¨×¡×× ×¢×¦×× × ×¢×©× ×¢× ×××.</p><div class="row"><button class="secondary" type="button" id="copy">××¢×ª×§ ×ª×©××× ×××¨×× ×</button><a class="btn secondary" href="https://www.facebook.com/" target="_blank" rel="noopener noreferrer">×¤×ª× ×¤×××¡×××§ â</a></div></section></main><aside><section class="panel"><h2>ð ×¤×ª×§××</h2><form method="post" action="/notes"><input type="hidden" name="csrf" value="{{csrf}}"><input name="content" maxlength="1000" required placeholder="×× ××× ×¦×¨×× ×××××¨?"><div class="row"><button>×©×××¨ ×¤×ª×§</button></div></form>{% for n in notes %}<div class="item">{{n['content']}} <form method="post" action="/notes/{{n['id']}}/delete"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger" aria-label="×××§ ×¤×ª×§">Ã</button></form></div>{% endfor %}</section><section class="panel"><h2>â ××©××××ª</h2><form method="post" action="/tasks"><input type="hidden" name="csrf" value="{{csrf}}"><input name="content" maxlength="500" required placeholder="××©××× ×××©×"><div class="row"><button>×××¡×£ ××©×××</button></div></form>{% for t in tasks %}<div class="item">{{ 'â' if t['done'] else 'â¬' }} {{t['content']}}<div class="row"><form method="post" action="/tasks/{{t['id']}}/toggle"><input type="hidden" name="csrf" value="{{csrf}}"><button class="secondary">{{'××× ×¡××××' if t['done'] else '×¡××××ª×'}}</button></form><form method="post" action="/tasks/{{t['id']}}/delete"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger">×××§</button></form></div></div>{% endfor %}</section><section class="panel"><h2>×¤×¨××××ª</h2><p class="muted">××× ×××× ××¡ ×¡××¡××××ª ×× ××¤×ª×××ª API ××©×××. ×× ×©×¤××ª× ××ª ×××¤××¤× ×©×× ×¢×©×× ××¨×××ª ××ª ×××××¢ ××.</p><form method="post" action="/clear" onsubmit="return confirm('×××××§ ××ª ××©××××ª, ××¤×ª×§×× ××××©××××ª ×©××?')"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger">×××§ ××ª ×× ×××××¢ ×©××</button></form></section></aside></div></div><script>
const box=document.getElementById('messages');box.scrollTop=box.scrollHeight;const form=document.getElementById('chat'),status=document.getElementById('status');let last={{last_answer|tojson}};
form.addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(form),message=fd.get('message');if(!message.trim())return;const send=document.getElementById('send');send.disabled=true;status.textContent='××× ×××©×...';add('user',message);document.getElementById('message').value='';try{const r=await fetch('/chat',{method:'POST',body:fd});const data=await r.json();if(!r.ok)throw Error(data.error||'×©××××');last=data.answer;add('assistant',last);status.textContent='';}catch(err){status.textContent='×©××××: '+err.message;status.className='error';}finally{send.disabled=false;}});
function add(role,text){const div=document.createElement('div');div.className='bubble '+role;const b=document.createElement('b');b.textContent=role==='user'?'××ª×':'DEAN';div.append(b,document.createElement('br'),document.createTextNode(text));box.append(div);box.scrollTop=box.scrollHeight;}
document.getElementById('copy').onclick=async()=>{if(!last)return alert('××× ×¢×××× ×ª×©×××');try{await navigator.clipboard.writeText(last);alert('×××¢×ª×§');}catch(e){alert('×××¢×ª×§× ×× × ×ª×××ª ×××¤××¤× ×××');}};
document.getElementById('read').onclick=()=>{if(!last)return;const u=new SpeechSynthesisUtterance(last);u.lang='he-IL';speechSynthesis.cancel();speechSynthesis.speak(u)};
document.getElementById('speak').onclick=()=>{const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R)return alert('×××¤××¤× ××× ×× ×ª××× ××××ª×× ×××');const r=new R();r.lang='he-IL';r.onresult=e=>document.getElementById('message').value=e.results[0][0].transcript;r.start();};
</script></body></html>'''

@app.get('/')
def home():
    user=uid()
    with db() as con:
        messages=con.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 40',(user,)).fetchall()[::-1]
        notes=con.execute('SELECT id,content FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 30',(user,)).fetchall()
        tasks=con.execute('SELECT id,content,done FROM tasks WHERE user_id=? ORDER BY id DESC LIMIT 50',(user,)).fetchall()
    last_answer=next((m['content'] for m in reversed(messages) if m['role']=='assistant'),'')
    return render_template_string(HTML,messages=messages,notes=notes,tasks=tasks,csrf=csrf(),last_answer=last_answer)

@app.post('/chat')
@protected
def chat():
    message=request.form.get('message','').strip()
    if not message or len(message)>6000:
        return jsonify(error='××××¢× ×¨××§× ×× ××¨××× ×××'),400
    user=uid()
    # Local slash commands are executed by Flask, not merely described by the model.
    if message.startswith('/'):
        command, _, argument = message.partition(' ')
        command, argument = command.lower(), argument.strip()
        reply = None
        if command in ('/help', '/commands'):
            reply = ('×¤×§××××ª DEAN\n/help â ×× ××¤×§××××ª\n/status â ××××××ª ×§×××××ª\n'
                     '/remember ××§×¡× â ×©×××¨ ×¤×ª×§\n/notes â ××¦× ×¤×ª×§××\n'
                     '/task ××§×¡× â ×××¡×£ ××©×××\n/tasks â ××¦× ××©××××ª\n'
                     '/done ××¡×¤×¨ â ×¡×× ××©××× ××××¦×¢×\n/facebook × ××©× â ××ª×× ×××××ª ×¤××¡×\n'
                     '××¤×©×¨ ×× ××××¨ ×××ª× ×¨××× ××¢××¨××ª.')
        elif command == '/status':
            reply = ('×¤×¢××: ×©××× ×¢× AI, ×××¡×××¨×××ª ×©×××, ×¤×ª×§××, ××©××××ª, ××××× ×××× ×ª ×¤××¡×××. '
                     '×× ×××××¨: ×¤×¨×¡×× ××¤×××¡×××§, ××××´×, ××××, ××××©× ×¢×¦××××ª, ×©×××× ×××××¤×. '
                     '×××××¨×× ××©×¨×ª ××× ×× ×¢××× ××××××§ ×××ª×××.')
        elif command in ('/remember', '/task'):
            limit = 1000 if command == '/remember' else 500
            if not argument or len(argument) > limit:
                reply = f'××ª×× {command} ××××¨×× ××§×¡× (×¢× {limit} ×ª××××).'
            else:
                table = 'notes' if command == '/remember' else 'tasks'
                with db() as con:
                    con.execute(f'INSERT INTO {table}(user_id,content,created) VALUES(?,?,?)', (user,argument,now()))
                reply = '××¤×ª×§ × ×©××¨.' if table == 'notes' else '×××©××× × ××¡×¤×.'
        elif command in ('/notes', '/tasks'):
            table = 'notes' if command == '/notes' else 'tasks'
            with db() as con:
                rows = con.execute(f'SELECT id,content' + (',done' if table=='tasks' else '') + f' FROM {table} WHERE user_id=? ORDER BY id DESC LIMIT 40', (user,)).fetchall()
            reply = '\n'.join(f"{r['id']}. " + (('â ' if r['done'] else 'â¡ ') if table=='tasks' else '') + r['content'] for r in rows) or '××× ×¢×××× ×¤×¨××××.'
        elif command == '/done':
            if argument.isdecimal():
                with db() as con:
                    cur=con.execute('UPDATE tasks SET done=1 WHERE id=? AND user_id=?', (int(argument),user))
                reply = '×××©××× ×¡××× × ××××¦×¢×.' if cur.rowcount else '×× × ××¦×× ××©××× ×¢× ×××¡×¤×¨ ×××.'
            else:
                reply = '××ª×× /tasks ××§×××ª ××¡×¤×¨× ×××©××××ª ××× /done ××¡×¤×¨.'
        elif command == '/facebook':
            if not argument:
                reply = '××ª×× /facebook ××××¨×× × ××©× ××¤××¡×.'
            else:
                message = '××ª×× ×××××ª ×¤××¡× ×§×¦×¨× ××¢××¨××ª ××¤×××¡×××§ ××××©× ×©×× ×× ××©×: '+argument+'; ××××¨ ×¨×§ ××××× ××¤×¨×¡×× ××× ×.'
        else:
            reply = '×¤×§××× ×× ××××¨×ª. ××ª×× /help.'
        if reply is not None:
            with db() as con:
                con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'user',message,now()))
                con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'assistant',reply,now()))
            return jsonify(answer=reply)
    with db() as con:
        history=con.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20',(user,)).fetchall()[::-1]
        notes=con.execute('SELECT content FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 20',(user,)).fetchall()
        tasks=con.execute('SELECT content,done FROM tasks WHERE user_id=? ORDER BY id DESC LIMIT 30',(user,)).fetchall()
    instructions='''××ª× DEAN, ××¢×××¨ ××××©× ×©× ×× ×××. ××©× ××¢××¨××ª ×××¢××ª, ××¨××¨× ××§×¦×¨×.
××ª× ×¤××¢× ×××ª×¨ Flask ×¢× ×©×××, ×¤×ª×§×× ×××©××××ª. ××× ×× ×××©× ×¢×¦××××ª ××¤×××¡×××§, ×××©××× ××ª, ×××××©× ××× ×× ××©×× ×× ×§××, ×××× ×× ××¢×¨××ª ×ª××××¨××ª ×©×©××××ª ××ª×¨×××ª. ×× ×ª××¢× ×©×××¦×¢×ª ×¤×¢××× ×©×× ×××¦×¢×.
××ª× ×¨×©×× ××××× ×¤××¡××× ××¤×××¡×××§ ××××©× ×××¢×ª×§× ××× ××ª, ××× ×× ××¤×¨×¡× ×××ª×.
×× ×ª××§×© ×¡××¡××××ª ×× ××¤×ª×××ª. ××§×© ×××©××¨ ××¤××¨×© ××¤× × ×¤×¢××××ª ××©××¢××ª×××ª ×××©×¨ ×××× ××××ª××× ×××× ×××× ××.
×¤×ª×§×× ×©×××¨××:\n'''+ '\n'.join('- '+n['content'] for n in notes)+ '\n××©××××ª:\n'+ '\n'.join(('[×××¦×¢] ' if t['done'] else '[×¤×ª××] ')+t['content'] for t in tasks)
    try:
        response=client.responses.create(model=MODEL,instructions=instructions,input=[{'role':m['role'],'content':m['content']} for m in history]+[{'role':'user','content':message}],max_output_tokens=1200)
        answer=response.output_text.strip() or '×× ××ª×§××× ×ª×©×××. × ×¡× ×©××.'
    except Exception:
        app.logger.exception('OpenAI request failed')
        return jsonify(error='×× ××¦×××ª× ×××ª×××¨ ××××× ××¨××¢. × ×¡× ×©×× ×××××¨ ×××ª×¨.'),502
    with db() as con:
        con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'user',message,now()))
        con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'assistant',answer,now()))
    return jsonify(answer=answer)

@app.post('/notes')
@protected
def add_note():
    content=request.form.get('content','').strip()
    if content and len(content)<=1000:
        with db() as con: con.execute('INSERT INTO notes(user_id,content,created) VALUES(?,?,?)',(uid(),content,now()))
    return redirect(url_for('home'))

@app.post('/notes/<int:item>/delete')
@protected
def del_note(item):
    with db() as con: con.execute('DELETE FROM notes WHERE id=? AND user_id=?',(item,uid()))
    return redirect(url_for('home'))

@app.post('/tasks')
@protected
def add_task():
    content=request.form.get('content','').strip()
    if content and len(content)<=500:
        with db() as con: con.execute('INSERT INTO tasks(user_id,content,created) VALUES(?,?,?)',(uid(),content,now()))
    return redirect(url_for('home'))

@app.post('/tasks/<int:item>/toggle')
@protected
def toggle_task(item):
    with db() as con: con.execute('UPDATE tasks SET done=1-done WHERE id=? AND user_id=?',(item,uid()))
    return redirect(url_for('home'))

@app.post('/tasks/<int:item>/delete')
@protected
def del_task(item):
    with db() as con: con.execute('DELETE FROM tasks WHERE id=? AND user_id=?',(item,uid()))
    return redirect(url_for('home'))

@app.get('/export')
def export():
    user=uid()
    with db() as con:
        data={name:[dict(r) for r in con.execute(f'SELECT * FROM {name} WHERE user_id=? ORDER BY id',(user,)).fetchall()] for name in ('messages','notes','tasks')}
    return Response(json.dumps(data,ensure_ascii=False,indent=2),mimetype='application/json',headers={'Content-Disposition':'attachment; filename=dean-backup.json','Cache-Control':'no-store'})

@app.post('/clear')
@protected
def clear():
    with db() as con:
        for name in ('messages','notes','tasks'): con.execute(f'DELETE FROM {name} WHERE user_id=?',(uid(),))
    return redirect(url_for('home'))

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))
