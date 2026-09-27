import os

from flask import Flask, request, render_template_string

from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

HTML = """

<!doctype html>

<html dir="rtl" lang="he">

<head>

<meta charset="utf-8">

<meta name="viewport" content="width=device-width, initial-scale=1">

<title>DEAN</title>

<style>

body{font-family:Arial;background:#111;color:white;max-width:800px;margin:auto;padding:20px}

textarea{width:100%;height:100px;font-size:18px;padding:10px}

button{font-size:18px;padding:12px 25px;margin-top:10px}

.answer{background:#222;padding:15px;margin-top:20px;border-radius:10px;white-space:pre-wrap}

</style>

</head>

<body>

<h1>DEAN</h1>

<p>העוזר האישי של בניאל</p>

<form method="post">

<textarea name="message" placeholder="דבר עם DEAN בעברית..."></textarea>

<br>

<button type="submit">שלח</button>

</form>

{% if answer %}

<div class="answer">{{ answer }}</div>

{% endif %}

</body>

</html>

"""

@app.route("/", methods=["GET", "POST"])

def home():

    answer = ""

    if request.method == "POST":

        message = request.form.get("message", "")

        if message:

            response = client.responses.create(

                model="gpt-5-mini",

                instructions="""

אתה DEAN, העוזר האישי של בניאל.

דבר עם בניאל בעברית טבעית, פשוטה וישירה.

המטרה שלך היא להיות עוזר אישי ביצועי ולא רק צ'אט.

לעולם אל תבצע פעולה משמעותית כמו פרסום, שליחת הודעה,

שליחת מייל, מחיקה, רכישה או תשלום ללא אישור מפורש מבניאל.

""",

                input=message

            )

            answer = response.output_text

    return render_template_string(HTML, answer=answer)

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
