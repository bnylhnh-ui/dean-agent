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
# Stable across worker restarts. Set SECRET_KEY in Render for best security.
secret = os.environ.get('SECRET_KEY')
if not secret:
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        raise RuntimeError('Set OPENAI_API_KEY in Render Environment')
    secret = hashlib.sha256(('dean-session-v1:' + api_key).encode()).hexdigest()
app.secret_key = secret
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                  SESSION_COOKIE_SAMESITE='Lax', MAX_CONTENT_LENGTH=40000)
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
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
        supplied = request.form.get('csrf', '') or request.headers.get('X-CSRF-Token', '')
        if not secrets.compare_digest(supplied, csrf()):
            if request.path == '/chat':
                return jsonify(error='Session refreshed. Please try again.', code='csrf_expired'), 403
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

HTML = '''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>DEAN - \u05d4\u05e2\u05d5\u05d6\u05e8 \u05e9\u05dc \u05d1\u05e0\u05d9\u05d0\u05dc</title>
<style>
:root{font-family:system-ui,Arial;color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#eaf0ff}header{padding:20px;background:#131b30;border-bottom:1px solid #29334e}h1{margin:0;color:#83e5bb}small,.muted{color:#aebbd4}.wrap{max-width:960px;margin:auto;padding:16px}.grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:16px}.panel{background:#151e32;border:1px solid #2a3654;border-radius:15px;padding:16px;margin-bottom:15px}.messages{height:52vh;overflow:auto;display:flex;flex-direction:column;gap:12px}.bubble{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;border-radius:12px;max-width:95%}.user{background:#245f65;align-self:flex-start}.assistant{background:#26314b;align-self:flex-end}textarea,input{width:100%;padding:12px;border:1px solid #43506a;border-radius:10px;background:#0c1528;color:white;font:inherit}button,.btn{cursor:pointer;border:0;border-radius:10px;padding:10px 15px;background:#45c99b;color:#09221a;font:inherit;font-weight:bold;text-decoration:none;display:inline-block}button.secondary,.btn.secondary{background:#34435f;color:white}button.danger{background:#793b47;color:white}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}.item{border-top:1px solid #34415c;padding:10px 0;overflow-wrap:anywhere}.item form{display:inline}.error{color:#ff9ca7}.notice{background:#343021;padding:10px;border-radius:9px;color:#f3d58a}a{color:#9ae4ff}@media(max-width:730px){.grid{grid-template-columns:1fr}.messages{height:43vh}}
</style></head><body><header><div class="wrap"><h1>DEAN \u2726</h1><small>\u05d4\u05e2\u05d5\u05d6\u05e8 \u05d4\u05d0\u05d9\u05e9\u05d9 \u05e9\u05dc \u05d1\u05e0\u05d9\u05d0\u05dc \u00b7 \u05e6'\u05d0\u05d8, \u05e4\u05ea\u05e7\u05d9\u05dd, \u05de\u05e9\u05d9\u05de\u05d5\u05ea \u05d5\u05d4\u05db\u05e0\u05ea \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd</small></div></header><div class="wrap"><p class="notice">\u05d4\u05d6\u05d9\u05db\u05e8\u05d5\u05df \u05e0\u05e9\u05de\u05e8 \u05d1\u05d3\u05e4\u05d3\u05e4\u05df \u05d4\u05d6\u05d4 \u05d5\u05d1\u05de\u05e1\u05d3 \u05d4\u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05e9\u05dc \u05d4\u05e9\u05e8\u05ea. \u05d1\u05e9\u05e8\u05ea Render \u05d7\u05d9\u05e0\u05de\u05d9 \u05d4\u05d5\u05d0 \u05e2\u05dc\u05d5\u05dc \u05dc\u05d4\u05d9\u05de\u05d7\u05e7 \u05d1\u05e4\u05e8\u05d9\u05e1\u05d4 \u05de\u05d7\u05d3\u05e9 \u05d0\u05d5 \u05d1\u05d0\u05ea\u05d7\u05d5\u05dc. \u05d0\u05d9\u05df \u05e2\u05d3\u05d9\u05d9\u05df \u05d7\u05d9\u05d1\u05d5\u05e8 \u05d0\u05d5\u05d8\u05d5\u05de\u05d8\u05d9 \u05dc\u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7.</p><div class="grid"><main><section class="panel"><h2>\u05e9\u05d9\u05d7\u05d4 \u05e2\u05dd \u05d3\u05d9\u05df</h2><p class="muted">\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea: /help \u00b7 /status \u00b7 /remember \u00b7 /task \u00b7 /tasks \u00b7 /notes \u00b7 /done \u00b7 /facebook</p><div id="messages" class="messages" aria-live="polite">{% for m in messages %}<div class="bubble {{m['role']}}"><b>{{ '\u05d0\u05ea\u05d4' if m['role']=='user' else 'DEAN' }}</b><br>{{m['content']}}</div>{% endfor %}</div><form id="chat" method="post" action="/chat"><input type="hidden" name="csrf" value="{{csrf}}"><textarea name="message" id="message" rows="3" maxlength="6000" required placeholder="\u05d3\u05d1\u05e8 \u05e2\u05dd \u05d3\u05d9\u05df \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea..."></textarea><div class="row"><button id="send">\u05e9\u05dc\u05d7</button><button class="secondary" type="button" id="speak">\U0001f3a4 \u05d3\u05d1\u05e8</button><button class="secondary" type="button" id="read">\U0001f50a \u05d4\u05e7\u05e8\u05d0</button><a class="btn secondary" href="/export">\u05d9\u05d9\u05e6\u05d5\u05d0 \u05d4\u05de\u05d9\u05d3\u05e2 \u05e9\u05dc\u05d9</a></div><p id="status" class="muted"></p></form></section><section class="panel"><h2>\u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7 \u05d0\u05d9\u05e9\u05d9</h2><p>\u05d1\u05e7\u05e9 \u05de\u05d3\u05d9\u05df \u05dc\u05d4\u05db\u05d9\u05df \u05e4\u05d5\u05e1\u05d8, \u05d4\u05e2\u05ea\u05e7 \u05d0\u05d5\u05ea\u05d5 \u05d5\u05e4\u05ea\u05d7 \u05d0\u05ea \u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7. \u05d4\u05e4\u05e8\u05e1\u05d5\u05dd \u05e0\u05e2\u05e9\u05d4 \u05e2\u05dc \u05d9\u05d3\u05da.</p><div class="row"><button class="secondary" type="button" id="copy">\u05d4\u05e2\u05ea\u05e7 \u05ea\u05e9\u05d5\u05d1\u05d4 \u05d0\u05d7\u05e8\u05d5\u05e0\u05d4</button><a class="btn secondary" href="https://www.facebook.com/" target="_blank" rel="noopener noreferrer">\u05e4\u05ea\u05d7 \u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7 \u2197</a></div></section></main><aside><section class="panel"><h2>\U0001f4cc \u05e4\u05ea\u05e7\u05d9\u05dd</h2><form method="post" action="/notes"><input type="hidden" name="csrf" value="{{csrf}}"><input name="content" maxlength="1000" required placeholder="\u05de\u05d4 \u05d3\u05d9\u05df \u05e6\u05e8\u05d9\u05da \u05dc\u05d6\u05db\u05d5\u05e8?"><div class="row"><button>\u05e9\u05de\u05d5\u05e8 \u05e4\u05ea\u05e7</button></div></form>{% for n in notes %}<div class="item">{{n['content']}} <form method="post" action="/notes/{{n['id']}}/delete"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger" aria-label="\u05de\u05d7\u05e7 \u05e4\u05ea\u05e7">\u00d7</button></form></div>{% endfor %}</section><section class="panel"><h2>\u2611 \u05de\u05e9\u05d9\u05de\u05d5\u05ea</h2><form method="post" action="/tasks"><input type="hidden" name="csrf" value="{{csrf}}"><input name="content" maxlength="500" required placeholder="\u05de\u05e9\u05d9\u05de\u05d4 \u05d7\u05d3\u05e9\u05d4"><div class="row"><button>\u05d4\u05d5\u05e1\u05e3 \u05de\u05e9\u05d9\u05de\u05d4</button></div></form>{% for t in tasks %}<div class="item">{{ '\u2705' if t['done'] else '\u2b1c' }} {{t['content']}}<div class="row"><form method="post" action="/tasks/{{t['id']}}/toggle"><input type="hidden" name="csrf" value="{{csrf}}"><button class="secondary">{{'\u05d1\u05d8\u05dc \u05e1\u05d9\u05de\u05d5\u05df' if t['done'] else '\u05e1\u05d9\u05d9\u05de\u05ea\u05d9'}}</button></form><form method="post" action="/tasks/{{t['id']}}/delete"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger">\u05de\u05d7\u05e7</button></form></div></div>{% endfor %}</section><section class="panel"><h2>\u05e4\u05e8\u05d8\u05d9\u05d5\u05ea</h2><p class="muted">\u05d0\u05dc \u05ea\u05db\u05e0\u05d9\u05e1 \u05e1\u05d9\u05e1\u05de\u05d0\u05d5\u05ea \u05d0\u05d5 \u05de\u05e4\u05ea\u05d7\u05d5\u05ea API \u05dc\u05e9\u05d9\u05d7\u05d4. \u05d4\u05d0\u05ea\u05e8 \u05e2\u05d3\u05d9\u05d9\u05df \u05d0\u05d9\u05e0\u05d5 \u05db\u05d5\u05dc\u05dc \u05de\u05e1\u05da \u05db\u05e0\u05d9\u05e1\u05d4.</p><form method="post" action="/clear" onsubmit="return confirm('\u05dc\u05de\u05d7\u05d5\u05e7 \u05d0\u05ea \u05db\u05dc \u05d4\u05e9\u05d9\u05d7\u05d5\u05ea, \u05d4\u05e4\u05ea\u05e7\u05d9\u05dd \u05d5\u05d4\u05de\u05e9\u05d9\u05de\u05d5\u05ea \u05e9\u05dc\u05da?')"><input type="hidden" name="csrf" value="{{csrf}}"><button class="danger">\u05de\u05d7\u05e7 \u05d0\u05ea \u05db\u05dc \u05d4\u05de\u05d9\u05d3\u05e2 \u05e9\u05dc\u05d9</button></form></section></aside></div></div><script>
const box=document.getElementById('messages');box.scrollTop=box.scrollHeight;
const form=document.getElementById('chat'),status=document.getElementById('status');let last={{last_answer|tojson}};
async function sendMessage(fd){let r=await fetch('/chat',{method:'POST',body:fd,credentials:'same-origin'});let data=await r.json();if(r.status===403&&data.code==='csrf_expired'){const t=await fetch('/csrf',{credentials:'same-origin',cache:'no-store'});if(!t.ok)throw Error('\u05d9\u05e9 \u05dc\u05e8\u05e2\u05e0\u05df \u05d0\u05ea \u05d4\u05e2\u05de\u05d5\u05d3');const j=await t.json();form.elements.csrf.value=j.csrf;fd.set('csrf',j.csrf);r=await fetch('/chat',{method:'POST',body:fd,credentials:'same-origin'});data=await r.json();}if(!r.ok)throw Error(data.error||'\u05e9\u05d2\u05d9\u05d0\u05d4');return data;}
form.addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(form),message=String(fd.get('message')||'');if(!message.trim())return;const send=document.getElementById('send');send.disabled=true;status.className='muted';status.textContent='\u05d3\u05d9\u05df \u05d7\u05d5\u05e9\u05d1...';add('user',message);document.getElementById('message').value='';try{const data=await sendMessage(fd);last=data.answer;add('assistant',last);status.textContent='';}catch(err){status.textContent='\u05e9\u05d2\u05d9\u05d0\u05d4: '+err.message+' \u2014 \u05e0\u05e1\u05d4 \u05dc\u05e8\u05e2\u05e0\u05df \u05d0\u05ea \u05d4\u05e2\u05de\u05d5\u05d3';status.className='error';document.getElementById('message').value=message;}finally{send.disabled=false;}});
function add(role,text){const div=document.createElement('div');div.className='bubble '+role;const b=document.createElement('b');b.textContent=role==='user'?'\u05d0\u05ea\u05d4':'DEAN';div.append(b,document.createElement('br'),document.createTextNode(text));box.append(div);box.scrollTop=box.scrollHeight;}
document.getElementById('copy').onclick=async()=>{if(!last)return alert('\u05d0\u05d9\u05df \u05e2\u05d3\u05d9\u05d9\u05df \u05ea\u05e9\u05d5\u05d1\u05d4');try{await navigator.clipboard.writeText(last);alert('\u05d4\u05d5\u05e2\u05ea\u05e7');}catch(e){alert('\u05dc\u05d0 \u05d4\u05e6\u05dc\u05d7\u05ea\u05d9 \u05dc\u05d4\u05e2\u05ea\u05d9\u05e7');}};
document.getElementById('read').onclick=()=>{if(!last)return;const u=new SpeechSynthesisUtterance(last);u.lang='he-IL';speechSynthesis.cancel();speechSynthesis.speak(u)};
document.getElementById('speak').onclick=()=>{const R=window.SpeechRecognition||window.webkitSpeechRecognition;if(!R)return alert('\u05d4\u05d3\u05e4\u05d3\u05e4\u05df \u05d4\u05d6\u05d4 \u05dc\u05d0 \u05ea\u05d5\u05de\u05da \u05d1\u05d4\u05db\u05ea\u05d1\u05d4 \u05db\u05d0\u05df');const r=new R();r.lang='he-IL';r.onresult=e=>document.getElementById('message').value=e.results[0][0].transcript;r.start();};
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

@app.get('/csrf')
def refresh_csrf():
    uid()
    return jsonify(csrf=csrf())

@app.post('/chat')
@protected
def chat():
    message=request.form.get('message','').strip()
    if not message or len(message)>6000:
        return jsonify(error='\u05d4\u05d5\u05d3\u05e2\u05d4 \u05e8\u05d9\u05e7\u05d4 \u05d0\u05d5 \u05d0\u05e8\u05d5\u05db\u05d4 \u05de\u05d3\u05d9'),400
    user=uid()
    if message.startswith('/'):
        command, _, argument = message.partition(' ')
        command, argument = command.lower(), argument.strip()
        reply = None
        if command in ('/help', '/commands'):
            reply = ('\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea DEAN\n/help \u2014 \u05db\u05dc \u05d4\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea\n/status \u2014 \u05d9\u05db\u05d5\u05dc\u05d5\u05ea \u05e7\u05d9\u05d9\u05de\u05d5\u05ea\n'
                     '/remember \u05d8\u05e7\u05e1\u05d8 \u2014 \u05e9\u05de\u05d5\u05e8 \u05e4\u05ea\u05e7\n/notes \u2014 \u05d4\u05e6\u05d2 \u05e4\u05ea\u05e7\u05d9\u05dd\n'
                     '/task \u05d8\u05e7\u05e1\u05d8 \u2014 \u05d4\u05d5\u05e1\u05e3 \u05de\u05e9\u05d9\u05de\u05d4\n/tasks \u2014 \u05d4\u05e6\u05d2 \u05de\u05e9\u05d9\u05de\u05d5\u05ea\n'
                     '/done \u05de\u05e1\u05e4\u05e8 \u2014 \u05e1\u05de\u05df \u05de\u05e9\u05d9\u05de\u05d4 \u05db\u05d1\u05d5\u05e6\u05e2\u05d4\n/facebook \u05e0\u05d5\u05e9\u05d0 \u2014 \u05db\u05ea\u05d5\u05d1 \u05d8\u05d9\u05d5\u05d8\u05ea \u05e4\u05d5\u05e1\u05d8\n'
                     '\u05d0\u05e4\u05e9\u05e8 \u05d2\u05dd \u05dc\u05d3\u05d1\u05e8 \u05d0\u05d9\u05ea\u05d9 \u05e8\u05d2\u05d9\u05dc \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea.')
        elif command == '/status':
            reply = ('\u05e4\u05e2\u05d9\u05dc: \u05e9\u05d9\u05d7\u05d4 \u05e2\u05dd AI, \u05d4\u05d9\u05e1\u05d8\u05d5\u05e8\u05d9\u05d9\u05ea \u05e9\u05d9\u05d7\u05d4, \u05e4\u05ea\u05e7\u05d9\u05dd, \u05de\u05e9\u05d9\u05de\u05d5\u05ea, \u05d2\u05d9\u05d1\u05d5\u05d9 \u05d5\u05d4\u05db\u05e0\u05ea \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd. '
                     '\u05dc\u05d0 \u05de\u05d7\u05d5\u05d1\u05e8: \u05e4\u05e8\u05e1\u05d5\u05dd \u05d1\u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7, \u05d3\u05d5\u05d0\u05f4\u05dc, \u05d9\u05d5\u05de\u05df, \u05d2\u05dc\u05d9\u05e9\u05d4 \u05e2\u05e6\u05de\u05d0\u05d9\u05ea, \u05e9\u05dc\u05d9\u05d8\u05d4 \u05d1\u05d0\u05d9\u05d9\u05e4\u05d3. '
                     '\u05d4\u05d6\u05d9\u05db\u05e8\u05d5\u05df \u05d1\u05e9\u05e8\u05ea \u05d7\u05d9\u05e0\u05de\u05d9 \u05e2\u05dc\u05d5\u05dc \u05dc\u05d4\u05d9\u05de\u05d7\u05e7 \u05d1\u05d0\u05ea\u05d7\u05d5\u05dc.')
        elif command in ('/remember', '/task'):
            limit = 1000 if command == '/remember' else 500
            if not argument or len(argument) > limit:
                reply = f'\u05db\u05ea\u05d5\u05d1 {command} \u05d5\u05d0\u05d7\u05e8\u05d9\u05d5 \u05d8\u05e7\u05e1\u05d8 (\u05e2\u05d3 {limit} \u05ea\u05d5\u05d5\u05d9\u05dd).'
            else:
                table = 'notes' if command == '/remember' else 'tasks'
                with db() as con:
                    con.execute(f'INSERT INTO {table}(user_id,content,created) VALUES(?,?,?)', (user,argument,now()))
                reply = '\u05d4\u05e4\u05ea\u05e7 \u05e0\u05e9\u05de\u05e8.' if table == 'notes' else '\u05d4\u05de\u05e9\u05d9\u05de\u05d4 \u05e0\u05d5\u05e1\u05e4\u05d4.'
        elif command in ('/notes', '/tasks'):
            table = 'notes' if command == '/notes' else 'tasks'
            with db() as con:
                rows = con.execute(f'SELECT id,content' + (',done' if table=='tasks' else '') + f' FROM {table} WHERE user_id=? ORDER BY id DESC LIMIT 40', (user,)).fetchall()
            reply = '\n'.join(f"{r['id']}. " + (('\u2713 ' if r['done'] else '\u25a1 ') if table=='tasks' else '') + r['content'] for r in rows) or '\u05d0\u05d9\u05df \u05e2\u05d3\u05d9\u05d9\u05df \u05e4\u05e8\u05d9\u05d8\u05d9\u05dd.'
        elif command == '/done':
            if argument.isdecimal():
                with db() as con:
                    cur=con.execute('UPDATE tasks SET done=1 WHERE id=? AND user_id=?', (int(argument),user))
                reply = '\u05d4\u05de\u05e9\u05d9\u05de\u05d4 \u05e1\u05d5\u05de\u05e0\u05d4 \u05db\u05d1\u05d5\u05e6\u05e2\u05d4.' if cur.rowcount else '\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d4 \u05de\u05e9\u05d9\u05de\u05d4 \u05e2\u05dd \u05d4\u05de\u05e1\u05e4\u05e8 \u05d4\u05d6\u05d4.'
            else:
                reply = '\u05db\u05ea\u05d5\u05d1 /tasks \u05dc\u05e7\u05d1\u05dc\u05ea \u05de\u05e1\u05e4\u05e8\u05d9 \u05d4\u05de\u05e9\u05d9\u05de\u05d5\u05ea \u05d5\u05d0\u05d6 /done \u05de\u05e1\u05e4\u05e8.'
        elif command == '/facebook':
            if not argument:
                reply = '\u05db\u05ea\u05d5\u05d1 /facebook \u05d5\u05d0\u05d7\u05e8\u05d9\u05d5 \u05e0\u05d5\u05e9\u05d0 \u05d4\u05e4\u05d5\u05e1\u05d8.'
            else:
                message = '\u05db\u05ea\u05d5\u05d1 \u05d8\u05d9\u05d5\u05d8\u05ea \u05e4\u05d5\u05e1\u05d8 \u05e7\u05e6\u05e8\u05d4 \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea \u05dc\u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7 \u05d4\u05d0\u05d9\u05e9\u05d9 \u05e9\u05dc\u05d9 \u05d1\u05e0\u05d5\u05e9\u05d0: '+argument+'; \u05d4\u05d7\u05d6\u05e8 \u05e8\u05e7 \u05d8\u05d9\u05d5\u05d8\u05d4 \u05dc\u05e4\u05e8\u05e1\u05d5\u05dd \u05d9\u05d3\u05e0\u05d9.'
        else:
            reply = '\u05e4\u05e7\u05d5\u05d3\u05d4 \u05dc\u05d0 \u05de\u05d5\u05db\u05e8\u05ea. \u05db\u05ea\u05d5\u05d1 /help.'
        if reply is not None:
            with db() as con:
                con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'user',message,now()))
                con.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(user,'assistant',reply,now()))
            return jsonify(answer=reply)
    with db() as con:
        history=con.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 20',(user,)).fetchall()[::-1]
        notes=con.execute('SELECT content FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 20',(user,)).fetchall()
        tasks=con.execute('SELECT content,done FROM tasks WHERE user_id=? ORDER BY id DESC LIMIT 30',(user,)).fetchall()
    instructions=('\u05d0\u05ea\u05d4 DEAN, \u05d4\u05e2\u05d5\u05d6\u05e8 \u05d4\u05d0\u05d9\u05e9\u05d9 \u05e9\u05dc \u05d1\u05e0\u05d9\u05d0\u05dc. \u05d4\u05e9\u05d1 \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea \u05d8\u05d1\u05e2\u05d9\u05ea, \u05d1\u05e8\u05d5\u05e8\u05d4 \u05d5\u05e7\u05e6\u05e8\u05d4. '
                  '\u05d9\u05e9 \u05d1\u05d0\u05ea\u05e8 \u05e9\u05d9\u05d7\u05d4, \u05e4\u05ea\u05e7\u05d9\u05dd \u05d5\u05de\u05e9\u05d9\u05de\u05d5\u05ea. \u05d0\u05d9\u05df \u05dc\u05da \u05d2\u05d9\u05e9\u05d4 \u05e2\u05e6\u05de\u05d0\u05d9\u05ea \u05dc\u05e4\u05d9\u05d9\u05e1\u05d1\u05d5\u05e7, \u05dc\u05d7\u05e9\u05d1\u05d5\u05e0\u05d5\u05ea, '
                  '\u05dc\u05d2\u05dc\u05d9\u05e9\u05d4 \u05d7\u05d9\u05d4 \u05d0\u05d5 \u05dc\u05e9\u05d9\u05e0\u05d5\u05d9 \u05e7\u05d5\u05d3. \u05d0\u05d9\u05df \u05dc\u05da \u05d4\u05ea\u05e8\u05d0\u05d5\u05ea \u05d9\u05d6\u05d5\u05de\u05d5\u05ea. \u05d0\u05dc \u05ea\u05d8\u05e2\u05df \u05e9\u05d1\u05d9\u05e6\u05e2\u05ea \u05e4\u05e2\u05d5\u05dc\u05d4 \u05e9\u05dc\u05d0 \u05d1\u05d5\u05e6\u05e2\u05d4. '
                  '\u05d0\u05dc \u05ea\u05d1\u05e7\u05e9 \u05e1\u05d9\u05e1\u05de\u05d0\u05d5\u05ea \u05d0\u05d5 \u05de\u05e4\u05ea\u05d7\u05d5\u05ea. \u05e4\u05e2\u05d5\u05dc\u05d5\u05ea \u05de\u05e9\u05de\u05e2\u05d5\u05ea\u05d9\u05d5\u05ea \u05d3\u05d5\u05e8\u05e9\u05d5\u05ea \u05d0\u05d9\u05e9\u05d5\u05e8 \u05de\u05e4\u05d5\u05e8\u05e9. '
                  '\u05e4\u05ea\u05e7\u05d9\u05dd \u05e9\u05de\u05d5\u05e8\u05d9\u05dd:\n'+'\n'.join('- '+n['content'] for n in notes)
                  +'\n\u05de\u05e9\u05d9\u05de\u05d5\u05ea:\n'+'\n'.join(('[\u05d1\u05d5\u05e6\u05e2] ' if t['done'] else '[\u05e4\u05ea\u05d5\u05d7] ')+t['content'] for t in tasks))
    try:
        response=client.responses.create(model=MODEL,instructions=instructions,
            input=[{'role':m['role'],'content':m['content']} for m in history]+[{'role':'user','content':message}],
            max_output_tokens=1200)
        answer=response.output_text.strip() or '\u05dc\u05d0 \u05d4\u05ea\u05e7\u05d1\u05dc\u05d4 \u05ea\u05e9\u05d5\u05d1\u05d4. \u05e0\u05e1\u05d4 \u05e9\u05d5\u05d1.'
    except Exception:
        app.logger.exception('OpenAI request failed')
        return jsonify(error='\u05dc\u05d0 \u05d4\u05e6\u05dc\u05d7\u05ea\u05d9 \u05dc\u05d4\u05ea\u05d7\u05d1\u05e8 \u05dc\u05de\u05d5\u05d3\u05dc \u05db\u05e8\u05d2\u05e2. \u05e0\u05e1\u05d4 \u05e9\u05d5\u05d1 \u05de\u05d0\u05d5\u05d7\u05e8 \u05d9\u05d5\u05ea\u05e8.'),502
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
