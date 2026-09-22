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
PAGE = r"""
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Study Lens</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css" onerror="window.mathStyleFailed = true">
  <script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.4.15/dist/purify.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js"></script>
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
    .hint { color:var(--muted); font-size:.86rem; }
    .answer { display:none; margin-top:28px; padding-top:24px; border-top:1px solid var(--line); } .answer.visible { display:block; }
    .answer-header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:20px; } .answer-header h2 { margin:0; }
    .secondary { background:#e4f1ec; color:var(--teal); padding:9px 12px; white-space:nowrap; } .secondary:hover { background:#d2e8df; }
    .answer-content { font-size:1.05rem; line-height:1.85; overflow-wrap:anywhere; }
    .answer-content > :first-child { margin-top:0; } .answer-content > :last-child { margin-bottom:0; }
    .answer-content h1,.answer-content h2,.answer-content h3,.answer-content h4 { font-size:1.18rem; line-height:1.5; margin:26px 0 10px; color:var(--teal); letter-spacing:normal; }
    .answer-content p { margin:12px 0; } .answer-content ul,.answer-content ol { padding-left:26px; } .answer-content li { margin:8px 0; padding-left:4px; }
    .answer-content li::marker { color:var(--teal); font-weight:700; }
    .answer-content blockquote { margin:20px 0; padding:8px 18px; border-left:4px solid var(--teal); background:#edf6f1; border-radius:0 8px 8px 0; }
    .answer-content pre { padding:16px; background:#f3f4f5; overflow-x:auto; border-radius:8px; }
    .answer-content code { font-size:.9em; background:#f3f4f5; padding:2px 4px; border-radius:4px; } .answer-content pre code { padding:0; }
    .answer-content table { display:block; max-width:100%; overflow-x:auto; border-collapse:collapse; margin:18px 0; }
    .answer-content th,.answer-content td { border:1px solid var(--line); padding:10px 14px; text-align:left; } .answer-content th { background:#edf6f1; }
    .answer-content .katex-display { overflow-x:auto; overflow-y:hidden; padding:18px 12px; margin:18px 0; background:#f5f8f6; border:1px solid #e1ebe5; border-radius:8px; }
    .answer-content .katex { font-size:1.12em; } .answer-content a { color:var(--teal); }
    .answer-content.plain { white-space:pre-wrap; } .notice { color:#8a401f; background:#fff0e6; padding:12px; border-radius:6px; line-height:1.6; }
    .panel { min-width:0; } .grid { grid-template-columns:minmax(0,1fr) 310px; } .shell { max-width:1240px; }
    :focus-visible { outline:3px solid var(--coral); outline-offset:3px; }
    .schedule { margin-top:0; } .schedule form { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:8px; } .schedule input[name=subject] { grid-column:1 / -1; } .tasks { margin:16px 0 0; padding:0; list-style:none; } .task { display:flex; justify-content:space-between; gap:15px; padding:12px 0; border-bottom:1px solid var(--line); } .task small { color:var(--muted); } .status { color:var(--teal); font-size:.8rem; font-weight:700; white-space:nowrap; }
    @media (max-width:760px) { .shell { padding-top:24px; } header,.grid { display:block; } header p { margin-top:18px; } .panel { margin-bottom:18px; } }
  </style>
</head>
<body>
  <main class="shell">
    <header><div><div class="hint">GÓC HỌC TẬP CỦA BẠN</div><h1>Học rõ hơn.<br><span>Nhớ lâu hơn.</span></h1></div><p>Gửi câu hỏi hoặc ảnh đề bài. Cùng hiểu ý tưởng, theo dõi từng bước và nắm chắc cách làm.</p></header>
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
        <section id="answer" class="answer" aria-labelledby="answer-title" aria-live="polite" aria-busy="false">
          <div class="answer-header"><h2 id="answer-title">Lời giải &amp; giải thích</h2><button id="copy-answer" class="secondary" type="button" hidden>Sao chép</button></div>
          <p id="answer-notice" class="notice" role="status" hidden></p>
          <div id="answer-content" class="answer-content"></div>
        </section>
      </article>
      <aside class="panel schedule"><h2>Lịch học</h2><form id="task-form"><input name="subject" placeholder="Môn học" required><input name="study_time" type="time" required><button type="submit" aria-label="Thêm lịch học">+</button></form><ul id="tasks" class="tasks"></ul></aside>
    </section>
  </main>
  <script>
    const answer = document.querySelector('#answer');
    const answerContent = document.querySelector('#answer-content');
    const answerNotice = document.querySelector('#answer-notice');
    const copyButton = document.querySelector('#copy-answer');
    let rawAnswer = '';
    let mathFailed = false;
    function renderFormula(text, displayMode) {
      if (!window.katex || window.mathStyleFailed) {
        mathFailed = true;
        return `<code>${escapeHtml(text)}</code>`;
      }
      try {
        return katex.renderToString(text, {displayMode, throwOnError:true, trust:false, maxExpand:1000, maxSize:20});
      } catch (error) {
        mathFailed = true;
        return `<code>${escapeHtml(text)}</code>`;
      }
    }
    // Recognize math before Markdown consumes backslashes, underscores or asterisks.
    if (window.marked) {
      marked.use({extensions:[{
        name:'studyMath', level:'inline',
        start(src) { return src.search(/\$|\\\(|\\\[/); },
        tokenizer(src) {
          const match = /^(?:\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([^\n]+?)\\\)|\$([^\s$](?:[^$\n]*?[^\s$])?)\$(?!\d))/.exec(src);
          if (match) return {type:'studyMath', raw:match[0], text:match[1] ?? match[2] ?? match[3] ?? match[4], display:match[1] !== undefined || match[2] !== undefined};
        },
        renderer(token) { return renderFormula(token.text, token.display); }
      }], renderer:{
        code(token) {
          if (/^(math|latex|tex)$/i.test(token.lang || '')) return renderFormula(token.text, true);
          return false;
        }
      }});
    }
    function showNotice(message) { answerNotice.textContent = message; answerNotice.hidden = !message; }
    function renderAnswer(text) {
      rawAnswer = text;
      mathFailed = false;
      showNotice('');
      answerContent.classList.remove('plain');
      if (window.marked && window.DOMPurify) {
        try {
          answerContent.innerHTML = DOMPurify.sanitize(marked.parse(text), {FORBID_TAGS:['img', 'style', 'input', 'form', 'button']});
          if (mathFailed) showNotice('Một số công thức chưa hiển thị được. Bạn có thể yêu cầu AI giải thích công thức đó bằng lời; nếu mất mạng, hãy kết nối lại và tải lại trang.');
          return;
        } catch (error) { /* Preserve the full answer if formatting fails. */ }
      }
      answerContent.textContent = text;
      answerContent.classList.add('plain');
      showNotice('Chưa tải được bộ hiển thị công thức và định dạng. Hãy kiểm tra kết nối mạng rồi tải lại trang. Nội dung gốc vẫn được giữ bên dưới.');
    }
    copyButton.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(rawAnswer); copyButton.textContent = 'Đã sao chép'; }
      catch (error) { showNotice('Không sao chép tự động được. Bạn có thể chọn nội dung rồi nhấn Ctrl+C.'); }
    });
    document.querySelector('#ask-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = document.querySelector('#ask-button');
      button.disabled = true; button.textContent = 'Đang đọc bài...';
      answer.classList.add('visible'); answer.setAttribute('aria-busy', 'true');
      showNotice(''); copyButton.hidden = true; copyButton.textContent = 'Sao chép';
      answerContent.textContent = 'Đang đọc đề và chuẩn bị lời giải cho bạn…';
      try {
        const response = await fetch('/api/ask', { method:'POST', body:new FormData(event.target) });
        if (response.status === 413) throw new Error('Ảnh quá lớn. Hãy chọn ảnh nhỏ hơn 8 MB.');
        const data = await response.json();
        if (!response.ok || !data.answer) throw new Error(data.error || 'Chưa nhận được lời giải. Bạn hãy thử lại.');
        renderAnswer(data.answer); copyButton.hidden = false;
      }
      catch (error) { answerContent.textContent = ''; showNotice(error instanceof SyntaxError || error instanceof TypeError ? 'Không kết nối được tới ứng dụng. Hãy thử lại.' : error.message); }
      finally { button.disabled = false; button.textContent = 'Phân tích bài'; answer.setAttribute('aria-busy', 'false'); }
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
