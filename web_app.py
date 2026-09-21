"""Web local cho trợ lý học tập: hỏi bài bằng chữ/ảnh và quản lý lịch."""

import logging
import atexit

from flask import Flask, jsonify, render_template_string, request

import ai_engine
import database
import scheduler


logger = logging.getLogger(__name__)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
background_scheduler = None

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PAGE = """
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Study Lens</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root { --ink:#202a36; --muted:#657180; --paper:#f5f1e8; --card:#fffdf8; --teal:#0b7771; --coral:#d95d45; --line:#d9d5ca; }
    * { box-sizing:border-box; } body { margin:0; color:var(--ink); background:radial-gradient(circle at 90% 0%, #d9eee7 0, transparent 28%), var(--paper); font-family:'DM Sans', sans-serif; }
    .shell { max-width:1120px; margin:0 auto; padding:36px 22px 70px; } header { display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:34px; }
    h1,h2,h3 { font-family:'Space Grotesk', sans-serif; margin:0; } h1 { font-size:clamp(2.3rem, 6vw, 5rem); line-height:.92; letter-spacing:-.04em; max-width:620px; } h1 span { color:var(--coral); } header p { max-width:310px; color:var(--muted); margin:0 0 5px; line-height:1.5; }
    .grid { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(300px,.75fr); gap:22px; align-items:start; } .panel { background:rgba(255,253,248,.88); border:1px solid var(--line); border-radius:8px; padding:24px; box-shadow:0 14px 35px rgba(37,42,48,.07); }
    .panel h2 { font-size:1.45rem; margin-bottom:18px; } label { display:block; font-size:.78rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin:16px 0 8px; }
    textarea,input { width:100%; border:1px solid var(--line); border-radius:5px; padding:13px 14px; font:inherit; color:var(--ink); background:#fff; } textarea { min-height:128px; resize:vertical; } input[type=file] { padding:10px; }
    button { border:0; border-radius:5px; background:var(--teal); color:white; font:700 .95rem 'DM Sans',sans-serif; padding:13px 18px; cursor:pointer; } button:hover { background:#095c58; } button:disabled { opacity:.55; cursor:wait; } .actions { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-top:16px; }
    .hint { color:var(--muted); font-size:.86rem; } .answer { display:none; margin-top:22px; padding:18px; border-left:4px solid var(--coral); background:#fff; white-space:pre-wrap; line-height:1.65; } .answer.visible { display:block; }
    .schedule { margin-top:22px; } .schedule form { display:grid; grid-template-columns:1fr 130px auto; gap:8px; } .tasks { margin:16px 0 0; padding:0; list-style:none; } .task { display:flex; justify-content:space-between; gap:15px; padding:12px 0; border-bottom:1px solid var(--line); } .task small { color:var(--muted); } .status { color:var(--teal); font-size:.8rem; font-weight:700; white-space:nowrap; }
    @media (max-width:760px) { .shell { padding-top:24px; } header,.grid { display:block; } header p { margin-top:18px; } .panel { margin-bottom:18px; } .schedule form { grid-template-columns:1fr 110px; } .schedule form button { grid-column:1 / -1; } }
  </style>
</head>
<body>
  <main class="shell">
    <header><div><div class="hint">LOCAL STUDY DESK / GEMINI VISION</div><h1>Học rõ hơn.<br><span>Nhớ lâu hơn.</span></h1></div><p>Chụp đề bài, ghi câu hỏi, rồi nhận lời giải có cấu trúc từ một gia sư AI học thuật.</p></header>
    <section class="grid">
      <article class="panel">
        <h2>Hỏi bài</h2>
        <form id="ask-form">
          <label for="question">Câu hỏi của bạn</label>
          <textarea id="question" name="question" placeholder="Ví dụ: Giải thích vì sao bước này dùng định luật bảo toàn năng lượng..."></textarea>
          <label for="image">Ảnh đề bài (không bắt buộc)</label>
          <input id="image" name="image" type="file" accept="image/jpeg,image/png,image/webp">
          <div class="actions"><span class="hint">JPG, PNG, WEBP · tối đa 8 MB</span><button id="ask-button" type="submit">Phân tích bài</button></div>
        </form>
        <div id="answer" class="answer"></div>
      </article>
      <aside class="panel schedule"><h2>Lịch học</h2><form id="task-form"><input name="subject" placeholder="Môn học" required><input name="study_time" type="time" required><button type="submit" aria-label="Thêm lịch học">+</button></form><ul id="tasks" class="tasks"></ul></aside>
    </section>
  </main>
  <script>
    const answer = document.querySelector('#answer');
    document.querySelector('#ask-form').addEventListener('submit', async (event) => {
      event.preventDefault(); const button = document.querySelector('#ask-button'); button.disabled = true; button.textContent = 'Đang đọc bài...'; answer.classList.remove('visible');
      try { const response = await fetch('/api/ask', { method:'POST', body:new FormData(event.target) }); const data = await response.json(); answer.textContent = data.answer || data.error || 'Không nhận được câu trả lời.'; answer.classList.add('visible'); }
      catch (error) { answer.textContent = 'Không kết nối được tới web local.'; answer.classList.add('visible'); }
      finally { button.disabled = false; button.textContent = 'Phân tích bài'; }
    });
    async function loadTasks() { const response = await fetch('/api/tasks'); const tasks = await response.json(); document.querySelector('#tasks').innerHTML = tasks.length ? tasks.map(task => `<li class="task"><span><strong>${escapeHtml(task.subject)}</strong><br><small>${task.study_time}</small></span><span class="status">${task.status === 'pending' ? 'Đang chờ' : 'Đã nhắc'}</span></li>`).join('') : '<li class="hint">Chưa có lịch học.</li>'; }
    document.querySelector('#task-form').addEventListener('submit', async (event) => { event.preventDefault(); await fetch('/api/tasks', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(Object.fromEntries(new FormData(event.target))) }); event.target.reset(); loadTasks(); });
    function escapeHtml(value) { return value.replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char])); }
    loadTasks();
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE)


@app.post("/api/ask")
def ask():
    question = request.form.get("question", "")
    uploaded = request.files.get("image")
    image_bytes = None
    mime_type = None
    if uploaded and uploaded.filename:
        mime_type = uploaded.mimetype
        if mime_type not in ALLOWED_IMAGE_TYPES:
            return jsonify(error="Chỉ nhận ảnh JPG, PNG hoặc WEBP."), 400
        image_bytes = uploaded.read()
        if not image_bytes:
            return jsonify(error="Ảnh tải lên đang trống."), 400
    if not question.strip() and image_bytes is None:
        return jsonify(error="Hãy nhập câu hỏi hoặc tải ảnh đề bài."), 400
    return jsonify(answer=ai_engine.answer_study_question(question, image_bytes, mime_type))


@app.get("/api/tasks")
def tasks():
    try:
        return jsonify(database.get_all_tasks())
    except Exception as exc:
        logger.warning("Không thể đọc lịch học trên web (%s).", type(exc).__name__)
        return jsonify(error="Không đọc được lịch học."), 500


@app.post("/api/tasks")
def add_task():
    payload = request.get_json(silent=True) or {}
    try:
        task_id = database.add_task(payload.get("subject", ""), payload.get("study_time", ""))
        return jsonify(id=task_id), 201
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        logger.warning("Không thể thêm lịch học trên web (%s).", type(exc).__name__)
        return jsonify(error="Không thể lưu lịch học."), 500


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    database.init_db()
    background_scheduler = scheduler.start_scheduler()
    atexit.register(background_scheduler.shutdown, wait=True)
    app.run(host="127.0.0.1", port=5000, debug=True)
