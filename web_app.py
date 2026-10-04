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
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Study Lens · Góc học tập</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css" onerror="window.mathStyleFailed = true">
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3.4.15/dist/purify.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js"></script>
<style>
:root { color-scheme:light; --ink:#252b29; --muted:#727b76; --line:#e6e9e6; --teal:#237b58; --paper:#f8faf8; }
* { box-sizing:border-box; } [hidden] { display:none !important; }
body { margin:0; font:15px/1.6 'Segoe UI',Arial,sans-serif; color:var(--ink); background:#fff; }
button,input,textarea { font:inherit; } button { cursor:pointer; border:0; background:transparent; color:inherit; } button:disabled { opacity:.45; cursor:default; }
button:focus-visible,a:focus-visible,textarea:focus-visible,input:focus-visible,summary:focus-visible { outline:2px solid var(--teal); outline-offset:4px; }
button { border-radius:9px; } button:hover:not(:disabled) { background:#e8ede9; }
svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; flex-shrink:0; }
h1,h2,h3,p { margin-top:0; } .muted { color:var(--muted); } .small { font-size:12px; } .icon-button { display:inline-flex; align-items:center; justify-content:center; width:38px; height:38px; }
.layout { display:flex; height:100vh; height:100dvh; overflow:hidden; }
.sidebar { width:270px; flex-shrink:0; background:#f5f7f5; border-right:1px solid var(--line); padding:24px 16px 16px; display:flex; flex-direction:column; gap:22px; overflow-y:auto; }
.brand { display:flex; align-items:center; gap:10px; padding:0 8px; font-size:19px; letter-spacing:-.5px; font-weight:650; }
.brand-mark { color:var(--teal); background:#e1eee6; border-radius:12px; display:grid; place-items:center; width:36px; height:36px; }
.brand .icon-button { margin-left:auto; } .new-chat { display:flex; gap:10px; align-items:center; padding:11px 14px; width:100%; border:1px solid #d8e0da; background:#fff; font-weight:600; text-align:left; }
.section-label { color:var(--muted); font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1.3px; margin:0 10px 10px; }
.chat-list { display:flex; flex-direction:column; gap:4px; max-height:220px; overflow-y:auto; } .chat-link { text-align:left; padding:10px 12px; white-space:nowrap; text-overflow:ellipsis; overflow:hidden; width:100%; font-size:14px; } .chat-link.active { background:#e5ece6; font-weight:600; }
.schedule { border-top:1px solid var(--line); padding-top:18px; } .schedule summary { font-weight:600; cursor:pointer; padding:0 8px 12px; } .schedule label { display:block; color:var(--muted); font-size:12px; margin:8px 0 4px; }
.schedule input { width:100%; min-width:0; background:white; border:1px solid #d9dfda; border-radius:8px; padding:9px 10px; }
.schedule button[type=submit] { width:100%; background:#e1ece4; color:#225e40; padding:9px; margin-top:12px; font-weight:600; }
.tasks { list-style:none; padding:0; margin:14px 0; font-size:13px; } .task { border-top:1px solid var(--line); padding:10px 0; overflow-wrap:anywhere; } .task small { display:block; color:var(--muted); } .status { font-size:11px; color:var(--teal); }
.sidebar-footer { margin-top:auto; border-top:1px solid var(--line); padding:16px 8px 0; display:flex; gap:10px; align-items:center; } .avatar { display:grid; place-items:center; width:32px; height:32px; border-radius:50%; background:#e8e4db; font-weight:600; font-size:12px; }
.workspace { flex:1; min-width:0; display:flex; flex-direction:column; position:relative; }
.topbar { height:72px; flex-shrink:0; display:flex; justify-content:space-between; align-items:center; padding:0 32px; border-bottom:1px solid #f1f3f1; gap:12px; }
.topbar-left { display:flex; align-items:center; gap:10px; min-width:0; } .topbar-title { font-size:15px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.badge { display:flex; align-items:center; gap:7px; color:#5b7062; font-size:12px; white-space:nowrap; } .dot { background:#6d9d7b; width:6px; height:6px; border-radius:50%; }
.feed { flex:1; overflow-y:auto; min-height:0; scroll-behavior:smooth; }
.welcome { max-width:760px; margin:0 auto; padding:clamp(38px,10vh,110px) 28px 40px; text-align:center; }
.welcome-icon { margin:0 auto 22px; display:grid; place-items:center; width:60px; height:60px; border-radius:20px; background:#edf5ef; color:var(--teal); } .welcome-icon svg { width:30px; height:30px; }
.eyebrow { font-size:11px; letter-spacing:2px; color:var(--teal); font-weight:600; margin-bottom:12px; }
h1 { font-size:clamp(27px,3.1vw,38px); font-weight:600; letter-spacing:-1.3px; line-height:1.25; margin-bottom:14px; }
.welcome > p { color:var(--muted); font-size:15px; max-width:450px; margin:0 auto; }
.suggestions { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:38px; text-align:left; }
.suggestion { background:#fff; border:1px solid var(--line); padding:18px; text-align:left; border-radius:14px; display:flex; flex-direction:column; gap:8px; } .suggestion:hover { border-color:#b7cbbd; } .suggestion svg { color:var(--teal); margin-bottom:8px; } .suggestion strong { font-size:14px; font-weight:600; } .suggestion span { font-size:12px; color:var(--muted); line-height:1.6; }
.messages { max-width:820px; margin:auto; padding:28px 32px 40px; }
.message { margin-bottom:32px; min-width:0; } .message.user { display:flex; justify-content:flex-end; } .user-bubble { max-width:85%; background:#f0f3f0; padding:12px 20px; border-radius:20px 20px 5px 20px; white-space:pre-wrap; overflow-wrap:anywhere; }
.user-bubble img { display:block; max-width:100%; max-height:240px; border-radius:10px; margin-bottom:8px; }
.assistant-label { display:flex; align-items:center; gap:9px; font-size:13px; font-weight:600; margin-bottom:14px; } .assistant-label .brand-mark { width:27px; height:27px; border-radius:9px; } .assistant-label svg { width:16px; height:16px; }
.message-tools { display:flex; gap:8px; margin-top:12px; } .message-tools button { padding:5px 9px; color:var(--muted); font-size:12px; } .pending { color:var(--muted); } .pending::before { content:' '; display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--teal); margin-right:10px; animation:pulse 1.2s infinite; } @keyframes pulse { 50% { opacity:.25; } }
.composer-area { padding:14px 28px 16px; background:#fff; flex-shrink:0; }
.composer-wrap { max-width:756px; margin:auto; } .composer { border:1px solid #dfe5df; border-radius:22px; padding:14px 16px 10px; box-shadow:0 4px 22px #23382b08; background:#fff; } .composer:focus-within { border-color:#9fb7a6; box-shadow:0 0 0 3px #edf4ef; }
textarea { width:100%; border:0; background:transparent; padding:3px 4px; line-height:1.6; min-height:48px; max-height:160px; resize:none; color:var(--ink); } textarea:focus-visible { outline:none; } textarea::placeholder { color:#89918b; }
.composer-actions { display:flex; align-items:center; justify-content:space-between; gap:10px; } .composer-left { display:flex; align-items:center; gap:8px; } .send { background:#28734f; color:white; border-radius:50%; width:36px; height:36px; display:grid; place-items:center; } .send:hover:not(:disabled) { background:#1a5739; }
.composer-note { text-align:center; color:#8a928c; font-size:11px; margin:10px 0 0; } .attachment { display:flex; align-items:center; gap:10px; background:#f2f6f2; border-radius:10px; padding:8px; margin-bottom:8px; font-size:12px; } .attachment img { width:44px; height:44px; object-fit:cover; border-radius:6px; } .attachment span { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.notice { font-size:13px; } .scrim { display:none; } .sidebar.closed { display:none; } .sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }
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

@media(max-width:760px) { .sidebar { display:none; } .sidebar.mobile-open { display:flex; position:fixed; z-index:30; inset:0 auto 0 0; width:280px; box-shadow:10px 0 40px #0001; } .scrim.open { display:block; position:fixed; inset:0; background:#16201b55; z-index:20; border-radius:0; width:100%; } .topbar { height:60px; padding:0 14px; } .badge { display:none; } .welcome { padding:40px 20px 24px; } .suggestions { gap:8px; margin-top:26px; } .suggestion { padding:12px; } .suggestion span { display:none; } .suggestion strong { font-size:12px; } .messages { padding:20px 18px; } .composer-area { padding:10px 12px; } .composer-note { font-size:10px; } .keyboard-hint { display:none; } .answer-content { font-size:1rem; } }
@media(prefers-reduced-motion:reduce) { .feed { scroll-behavior:auto; } .pending::before { animation:none; } }
</style>
</head>
<body>
<svg aria-hidden="true" style="display:none"><defs>
<symbol id="spark" viewBox="0 0 24 24"><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></symbol>
<symbol id="plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
<symbol id="panel" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></symbol>
<symbol id="arrow" viewBox="0 0 24 24"><path d="M12 19V5m-6 6 6-6 6 6"/></symbol>
<symbol id="clip" viewBox="0 0 24 24"><path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2M5 16 15 6"/></symbol>
<symbol id="book" viewBox="0 0 24 24"><path d="M12 5v15M3 4c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/></symbol>
<symbol id="steps" viewBox="0 0 24 24"><path d="m3 6 2 2 3-4m3 3h10M3 13h5m3 0h10M3 19h5m3 0h10"/></symbol>
</defs></svg>
<div class="layout">
<button id="scrim" class="scrim" aria-label="Đóng thanh bên"></button>
<aside id="sidebar" class="sidebar" aria-label="Điều hướng và lịch học">
<div class="brand"><span class="brand-mark"><svg><use href="#spark"/></svg></span>Study Lens<button id="close-sidebar" class="icon-button" aria-label="Thu gọn thanh bên"><svg><use href="#panel"/></svg></button></div>
<button id="new-chat" class="new-chat"><svg><use href="#plus"/></svg>Cuộc trò chuyện mới</button>
<nav aria-label="Cuộc trò chuyện"><p class="section-label">Lịch sử trò chuyện</p><div id="chat-list" class="chat-list"></div><p id="history-status" class="small muted" role="status">Đang tải lịch sử…</p></nav>
<details class="schedule" open><summary>Lịch nhắc học</summary>
<form id="task-form"><label for="subject">Môn học</label><input id="subject" name="subject" placeholder="Ví dụ: Toán, Tiếng Anh" required maxlength="200"><label for="study-time">Giờ nhắc</label><input id="study-time" name="study_time" type="time" required><button type="submit">Thêm lịch nhắc</button></form>
<p id="task-notice" class="small" role="status"></p><ul id="tasks" class="tasks"></ul>
</details>
<div class="sidebar-footer"><div class="avatar">B</div><div><strong class="small">Góc học tập của bạn</strong><div class="small muted">Từng bước, mỗi ngày.</div></div></div>
</aside>
<main class="workspace">
<header class="topbar"><div class="topbar-left"><button id="toggle-sidebar" class="icon-button" aria-label="Mở hoặc đóng thanh bên" aria-controls="sidebar" aria-expanded="true"><svg><use href="#panel"/></svg></button><span id="chat-title" class="topbar-title">Trợ lý học tập</span></div><span class="badge"><span class="dot"></span>Không gian học tập cá nhân</span></header>
<div id="feed" class="feed">
<section id="welcome" class="welcome"><div class="welcome-icon"><svg><use href="#spark"/></svg></div><div class="eyebrow">MỖI CÂU HỎI, MỘT BƯỚC TIẾN</div><h1>Hôm nay bạn muốn hiểu điều gì?</h1><p>Cùng gỡ rối bài khó, hiểu rõ kiến thức<br>và tìm cách học phù hợp với bạn.</p>
<div class="suggestions"><button class="suggestion" data-prompt="Giải thích kiến thức này thật dễ hiểu và cho mình một ví dụ: "><svg><use href="#book"/></svg><strong>Hiểu bài dễ hơn</strong><span>Giải thích đơn giản, có ví dụ gần gũi.</span></button><button class="suggestion" data-prompt="Hướng dẫn mình giải từng bước bài tập sau: "><svg><use href="#steps"/></svg><strong>Gỡ rối bài tập</strong><span>Nắm cách làm qua từng bước giải.</span></button><button class="suggestion" data-prompt="Tạo 5 câu hỏi ôn tập kèm đáp án về chủ đề: "><svg><use href="#spark"/></svg><strong>Ôn tập kiến thức</strong><span>Tự kiểm tra bằng câu hỏi ngắn.</span></button></div></section>
<div id="messages" class="messages" aria-label="Nội dung trò chuyện" role="log" aria-live="polite" hidden></div>
</div>
<div class="composer-area"><div class="composer-wrap"><p id="composer-notice" class="notice" role="status" hidden></p>
<form id="ask-form" class="composer"><div id="attachment" class="attachment" hidden><img id="preview" alt="Ảnh đề bài đã chọn"><span id="filename"></span><button id="remove-image" type="button" class="icon-button" aria-label="Bỏ ảnh đính kèm">×</button></div>
<label for="question" class="sr-only">Câu hỏi của bạn</label><textarea id="question" name="question" rows="2" placeholder="Hỏi bất cứ điều gì về bài học…"></textarea>
<input id="image" name="image" type="file" accept="image/jpeg,image/png,image/webp" hidden>
<div class="composer-actions"><div class="composer-left"><button id="attach" type="button" class="icon-button" aria-label="Đính kèm ảnh đề bài" title="Đính kèm ảnh JPG, PNG, WEBP · dưới 8 MB"><svg><use href="#clip"/></svg></button><span class="small muted keyboard-hint">Enter để gửi · Shift + Enter để xuống dòng</span></div><button id="ask-button" class="send" type="submit" aria-label="Gửi câu hỏi" disabled><svg><use href="#arrow"/></svg></button></div>
</form><p class="composer-note">AI có thể nhầm. Hãy kiểm tra lời giải. Mỗi câu hỏi được xử lý độc lập.</p></div></div>
</main></div>
<script>
const $ = selector => document.querySelector(selector);
const question = $('#question'), imageInput = $('#image'), feed = $('#feed');
const conversations = [];
let current, busy = false, previewUrl = null;
let historyDB = null, draftTimer;
function openHistory() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('study-lens-history', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('conversations', {keyPath:'id'});
      request.result.createObjectStore('settings');
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('History is blocked'));
  });
}
function historyStatus(text) { $('#history-status').textContent = text; }
function saveHistory() {
  if (!historyDB || !current) return Promise.resolve(false);
  // Save only this conversation, so another tab cannot erase other conversations.
  current.draft = question.value;
  const snapshot = structuredClone(current);
  for (const message of snapshot.messages) delete message.image;
  historyStatus('Đang lưu…');
  return new Promise(resolve => {
    try {
      const transaction = historyDB.transaction(['conversations','settings'], 'readwrite');
      transaction.objectStore('conversations').put(snapshot);
      transaction.objectStore('settings').put(current.id, 'active');
      transaction.oncomplete = () => { historyStatus('Đã lưu trên trình duyệt này.'); resolve(true); };
      transaction.onabort = transaction.onerror = () => { historyStatus('Chưa lưu được thay đổi. Bộ nhớ có thể đã đầy hoặc bị chặn.'); resolve(false); };
    } catch (error) { historyStatus('Chưa lưu được thay đổi. Hãy kiểm tra bộ nhớ trình duyệt.'); resolve(false); }
  });
}
function readHistory() {
  return new Promise((resolve, reject) => {
    const transaction = historyDB.transaction(['conversations','settings'], 'readonly');
    const chats = transaction.objectStore('conversations').getAll();
    const active = transaction.objectStore('settings').get('active');
    transaction.oncomplete = () => resolve({chats:chats.result, active:active.result});
    transaction.onerror = transaction.onabort = () => reject(transaction.error);
  });
}
async function restoreHistory() {
  setBusy(true);
  try {
    historyDB = await openHistory();
    historyDB.onversionchange = () => { historyDB.close(); historyDB = null; historyStatus('Hãy tải lại trang để tiếp tục lưu lịch sử.'); };
    const saved = await readHistory();
    const chats = saved.chats.sort((a,b) => a.createdAt - b.createdAt);
    for (const chat of chats) {
      for (const message of chat.messages) {
        if (message.imageFile instanceof Blob) message.image = URL.createObjectURL(message.imageFile);
        if (message.pending) {
          message.pending = false; message.error = true;
          message.text = 'Lần trả lời trước bị gián đoạn khi đóng hoặc tải lại trang. Nhấn Thử lại để gửi lại câu hỏi.';
        }
      }
    }
    conversations.push(...chats);
    current = conversations.find(chat => chat.id === saved.active) || conversations.at(-1);
    historyStatus('Lịch sử được lưu trên trình duyệt này.');
  } catch (error) {
    if (historyDB) historyDB.close();
    historyDB = null;
    historyStatus('Không mở được lịch sử. Tin nhắn mới chưa được lưu; hãy kiểm tra quyền lưu trữ của trình duyệt.');
  }
  setBusy(false);
  if (current) { question.value = current.draft || ''; renderChats(); renderMessages(); syncComposer(); updateExpanded(); scrollDown(); }
  else newChat();
}
const spark = '<span class="brand-mark"><svg><use href="#spark"/></svg></span>';
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char])); }
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

function notice(node, text) { node.textContent = text; node.hidden = !text; }
function renderAnswer(text, node, warning) {
  mathFailed = false;
  if (window.marked && window.DOMPurify) {
    try {
      node.innerHTML = DOMPurify.sanitize(marked.parse(text), {FORBID_TAGS:['img','style','input','form','button']});
      if (mathFailed) notice(warning, 'Một số công thức chưa hiển thị được. Bạn có thể yêu cầu giải thích công thức bằng lời.');
      return;
    } catch (error) { /* Keep the original response readable. */ }
  }
  node.textContent = text; node.classList.add('plain');
  notice(warning, 'Chưa tải được bộ định dạng. Kiểm tra mạng rồi tải lại trang để xem công thức.');
}
function scrollDown() { requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; }); }
function renderMessages() {
  const container = $('#messages'); container.replaceChildren();
  $('#welcome').hidden = current.messages.length > 0;
  container.hidden = current.messages.length === 0;
  $('#chat-title').textContent = current.title;
  for (const message of current.messages) {
    const item = document.createElement('article'); item.className = 'message ' + message.role;
    if (message.role === 'user') {
      const bubble = document.createElement('div'); bubble.className = 'user-bubble';
      if (message.image) { const img = document.createElement('img'); img.src = message.image; img.alt = 'Ảnh đề bài'; bubble.append(img); }
      bubble.append(document.createTextNode(message.text)); item.append(bubble);
    } else {
      item.innerHTML = '<div class="assistant-label">' + spark + 'Study Lens</div><div class="answer-content"></div><p class="notice" hidden></p>';
      const content = item.querySelector('.answer-content'), warning = item.querySelector('.notice');
      if (message.pending) { content.classList.add('pending'); content.textContent = 'Đang đọc đề và chuẩn bị lời giải…'; }
      else if (message.error) { notice(warning, message.text); const retry = document.createElement('button'); retry.textContent = 'Thử lại'; retry.className = 'new-chat'; retry.disabled = busy; retry.onclick = () => sendMessage(message.request, message); item.append(retry); }
      else {
        renderAnswer(message.text, content, warning);
        const tools = document.createElement('div'); tools.className = 'message-tools';
        const copy = document.createElement('button'); copy.textContent = 'Sao chép'; copy.onclick = async () => {
          try { await navigator.clipboard.writeText(message.text); copy.textContent = 'Đã sao chép'; }
          catch (error) { notice(warning, 'Không sao chép tự động được. Hãy chọn nội dung và nhấn Ctrl+C.'); }
        }; tools.append(copy); item.append(tools);
      }
    }
    container.append(item);
  }
}
function renderChats() {
  $('#chat-list').replaceChildren();
  for (const chat of conversations.slice().reverse()) {
    const button = document.createElement('button'); button.className = 'chat-link' + (chat === current ? ' active' : ''); button.textContent = chat.title; button.title = chat.title; button.disabled = busy;
    if (chat === current) button.setAttribute('aria-current','page');
    button.onclick = () => { clearTimeout(draftTimer); saveHistory(); current = chat; question.value = chat.draft || ''; clearImage(); renderChats(); renderMessages(); syncComposer(); closeMobileSidebar(); scrollDown(); saveHistory(); };
    $('#chat-list').append(button);
  }
}
function newChat() {
  if (busy) return;
  clearTimeout(draftTimer);
  if (current) saveHistory();
  current = {id:crypto.randomUUID(), createdAt:Date.now(), title:'Cuộc trò chuyện mới', messages:[], draft:''}; conversations.push(current);
  question.value = ''; clearImage(); renderChats(); renderMessages(); syncComposer(); closeMobileSidebar(); question.focus();
  saveHistory();
}
function syncComposer() { $('#ask-button').disabled = busy || (!question.value.trim() && !imageInput.files.length); question.style.height = 'auto'; question.style.height = Math.min(question.scrollHeight,160) + 'px'; }
function setBusy(value) { busy = value; for (const selector of ['#question','#attach','#remove-image','#new-chat']) $(selector).disabled = value; $('#messages').setAttribute('aria-busy', String(value)); syncComposer(); renderChats(); }
function clearImage() { if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null; imageInput.value = ''; $('#preview').removeAttribute('src'); $('#attachment').hidden = true; syncComposer(); }
$('#attach').onclick = () => imageInput.click();
$('#remove-image').onclick = clearImage;
imageInput.onchange = () => {
  const file = imageInput.files[0]; notice($('#composer-notice'),'');
  if (!file) { clearImage(); return; }
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size >= 8 * 1024 * 1024) { clearImage(); notice($('#composer-notice'),'Hãy chọn ảnh JPG, PNG hoặc WEBP nhỏ hơn 8 MB.'); return; }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file); $('#preview').src = previewUrl; $('#filename').textContent = file.name; $('#attachment').hidden = false; syncComposer();
};
question.oninput = () => { syncComposer(); clearTimeout(draftTimer); draftTimer = setTimeout(saveHistory, 250); };
document.addEventListener('visibilitychange', () => { if (document.hidden && current) { clearTimeout(draftTimer); saveHistory(); } });
window.addEventListener('pagehide', () => { if (current) saveHistory(); });
question.onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !matchMedia('(pointer: coarse)').matches) { event.preventDefault(); if (!$('#ask-button').disabled) $('#ask-form').requestSubmit(); } };
$('.suggestions').onclick = event => { const button = event.target.closest('[data-prompt]'); if (button) { question.value = button.dataset.prompt; question.focus(); syncComposer(); } };
async function sendMessage(payload, retryMessage = null) {
  if (busy) return;
  notice($('#composer-notice'),''); setBusy(true);
  if (!retryMessage) {
    if (!current.messages.length) current.title = (payload.text || 'Bài tập từ ảnh').slice(0,60);
    current.messages.push({role:'user',text:payload.text,imageFile:payload.file || null,image:payload.file ? URL.createObjectURL(payload.file) : null});
  }
  const reply = retryMessage || {role:'assistant'};
  Object.assign(reply, {pending:true,error:false,text:'',request:payload});
  if (!retryMessage) current.messages.push(reply);
  renderChats(); renderMessages(); scrollDown();
  // Commit the question and retry payload before waiting for the AI response.
  await saveHistory();
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const form = new FormData(); form.append('question', payload.text); if (payload.file) form.append('image', payload.file);
    const response = await fetch('/api/ask', {method:'POST',body:form,signal:controller.signal});
    if (response.status === 413) throw new Error('Ảnh quá lớn. Hãy chọn ảnh nhỏ hơn 8 MB.');
    const data = await response.json();
    if (!response.ok || typeof data.answer !== 'string' || !data.answer.trim()) throw new Error(data.error || 'Chưa nhận được lời giải. Bạn hãy thử lại.');
    reply.text = data.answer; delete reply.request;
  } catch (error) {
    reply.error = true;
    reply.text = error.name === 'AbortError' ? 'AI trả lời lâu hơn dự kiến. Bạn hãy thử lại.' : error instanceof TypeError || error instanceof SyntaxError ? 'Không kết nối được tới ứng dụng. Hãy kiểm tra kết nối rồi thử lại.' : error.message;
  } finally { clearTimeout(timeout); reply.pending = false; await saveHistory(); setBusy(false); renderMessages(); question.focus(); }
}
$('#ask-form').onsubmit = event => {
  event.preventDefault(); if (busy) return;
  const payload = {text:question.value.trim(),file:imageInput.files[0]}; if (!payload.text && !payload.file) return;
  question.value = ''; current.draft = ''; clearImage(); sendMessage(payload);
};
function closeMobileSidebar() { $('#sidebar').classList.remove('mobile-open'); $('#scrim').classList.remove('open'); updateExpanded(); }
function updateExpanded() { $('#toggle-sidebar').setAttribute('aria-expanded', String(matchMedia('(max-width:760px)').matches ? $('#sidebar').classList.contains('mobile-open') : !$('#sidebar').classList.contains('closed'))); }
$('#toggle-sidebar').onclick = () => {
  if (matchMedia('(max-width:760px)').matches) { $('#sidebar').classList.toggle('mobile-open'); $('#scrim').classList.toggle('open'); }
  else $('#sidebar').classList.toggle('closed'); updateExpanded();
};
$('#close-sidebar').onclick = () => { if (matchMedia('(max-width:760px)').matches) closeMobileSidebar(); else $('#sidebar').classList.add('closed'); updateExpanded(); $('#toggle-sidebar').focus(); };
$('#scrim').onclick = closeMobileSidebar;
document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeMobileSidebar(); $('#toggle-sidebar').focus(); } });
matchMedia('(max-width:760px)').addEventListener('change', closeMobileSidebar);
$('#new-chat').onclick = newChat;
async function loadTasks() {
  try {
    const response = await fetch('/api/tasks'); const tasks = await response.json();
    if (!response.ok || !Array.isArray(tasks)) throw new Error('Không đọc được lịch học.');
    $('#tasks').innerHTML = tasks.length ? tasks.map(task => `<li class="task"><strong>${escapeHtml(task.subject)}</strong><small>${escapeHtml(task.study_time)}</small><span class="status">${task.status === 'pending' ? 'Đang chờ nhắc' : 'Đã nhắc'}</span></li>`).join('') : '<li class="muted small">Chưa có lịch. Thêm một giờ học nhé.</li>';
  } catch (error) { $('#tasks').textContent = 'Chưa tải được lịch học. Hãy tải lại trang để thử lại.'; }
}
$('#task-form').onsubmit = async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try {
    const response = await fetch('/api/tasks', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Không lưu được lịch học.');
    event.target.reset(); $('#task-notice').textContent = 'Đã thêm lịch nhắc.'; await loadTasks();
  } catch (error) { $('#task-notice').textContent = error instanceof TypeError || error instanceof SyntaxError ? 'Không kết nối được. Lịch chưa được lưu.' : error.message; }
  finally { button.disabled = false; }
};
restoreHistory(); loadTasks();
</script></body></html>
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
