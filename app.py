import os
import sys
import uuid
import threading
import time
from flask import Flask, request, jsonify, render_template_string
sys.path.insert(0, os.path.dirname(__file__))
import tiktok_search

app = Flask(__name__)


JOBS: dict = {}
JOBS_LOCK = threading.Lock()


def _new_job(query: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "query": query,
            "status": "running",
            "step": 0,
            "total": 8,
            "message": "Запускаю...",
            "log": [],
            "result": None,
            "error": None,
            "started_at": time.time(),
        }
    return job_id


def _progress(job_id: str):
    def cb(step, total, msg):
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job["step"] = step
            job["total"] = total
            job["message"] = msg
            entry = f"Шаг {step}/{total}: {msg}"
            if not job["log"] or job["log"][-1] != entry:
                job["log"].append(entry)
    return cb


def _run_job(job_id: str, query: str):
    try:
        result = tiktok_search.run_pipeline(query, progress=_progress(job_id))
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return
            job["result"] = result
            job["status"] = "done" if result.get("success") else "error"
            if not result.get("success"):
                job["error"] = result.get("error", "Неизвестная ошибка")
    except Exception as e:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if job:
                job["status"] = "error"
                job["error"] = f"Внутренняя ошибка: {e}"


INDEX_HTML = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>TikTok Viral Search</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background:#0f0f12; color:#eee; margin:0; padding:24px; }
  .wrap { max-width: 820px; margin: 0 auto; }
  h1 { margin: 0 0 8px; font-size: 24px; }
  h3 { margin: 16px 0 8px; }
  p.muted { color: #888; margin: 0 0 24px; }
  form { display:flex; gap:8px; margin-bottom: 24px; }
  input[type=text] { flex:1; padding: 12px 14px; font-size:16px; border-radius:8px; border:1px solid #333; background:#1a1a1f; color:#eee; }
  button { padding: 12px 20px; font-size:16px; border-radius:8px; border:0; background:#ff2d55; color:#fff; cursor:pointer; font-weight:600; }
  button:disabled { opacity:0.5; cursor:wait; }
  .card { background:#1a1a1f; border:1px solid #2a2a30; border-radius:12px; padding:16px; margin-bottom:12px; }
  .progress-bar { background:#1a1a1f; border-radius:8px; height:8px; overflow:hidden; margin: 12px 0; }
  .progress-fill { background: linear-gradient(90deg, #ff2d55, #ff8a00); height:100%; transition: width 0.5s; }
  .log { background:#0a0a0d; border-radius:8px; padding:12px; font-family: monospace; font-size:13px; line-height:1.7; max-height:240px; overflow-y:auto; }
  .log .step { color:#aaa; }
  .log .step.current { color:#fff; font-weight:600; }
  .log .step.done { color:#4caf50; }
  .status-msg { font-size:15px; color:#ccc; margin: 8px 0; }
  .err { background:#3a1a1a; color:#ff6b6b; padding:12px; border-radius:8px; }
  video { width:100%; max-width:400px; border-radius:12px; background:#000; }
  .meta { color:#888; font-size:14px; }
  .top-vid { font-size:14px; padding:6px 0; border-bottom:1px solid #2a2a30; }
  .top-vid:last-child { border:0; }
  a { color:#4cc2ff; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>🔥 Генератор вирусных TikTok</h1>
    <p class="muted">Введи тему — найду топ-автора, проанализирую его формат и сгенерирую новое видео (15-25 мин).</p>

    <form id="searchForm">
      <input type="text" id="query" placeholder="например: fitness, cooking, dance" required>
      <button type="submit" id="submitBtn">Запустить</button>
    </form>

    <div id="progressBox" style="display:none">
      <div class="card">
        <div class="status-msg" id="statusMsg"></div>
        <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
        <div class="log" id="log"></div>
      </div>
    </div>

    <div id="resultBox"></div>
  </div>

<script>
const form = document.getElementById('searchForm');
const btn = document.getElementById('submitBtn');
const progressBox = document.getElementById('progressBox');
const statusMsg = document.getElementById('statusMsg');
const progressFill = document.getElementById('progressFill');
const logEl = document.getElementById('log');
const resultBox = document.getElementById('resultBox');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('query').value.trim();
  if (!query) return;

  btn.disabled = true;
  resultBox.innerHTML = '';
  progressBox.style.display = 'block';
  statusMsg.textContent = '⏳ Запускаю задачу...';
  progressFill.style.width = '0%';
  logEl.innerHTML = '';

  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const { job_id, error } = await res.json();
    if (error) throw new Error(error);
    pollStatus(job_id);
  } catch (err) {
    statusMsg.innerHTML = `<div class="err">❌ ${err.message}</div>`;
    btn.disabled = false;
  }
});

async function pollStatus(jobId) {
  try {
    const r = await fetch(`/status/${jobId}`);
    const state = await r.json();

    renderProgress(state);

    if (state.status === 'done') {
      renderResult(state.result);
      btn.disabled = false;
    } else if (state.status === 'error') {
      renderError(state);
      btn.disabled = false;
    } else {
      setTimeout(() => pollStatus(jobId), 3000);
    }
  } catch (err) {
    statusMsg.innerHTML = `<div class="err">❌ Ошибка опроса: ${err.message}</div>`;
    btn.disabled = false;
  }
}

function renderProgress(state) {
  const pct = (state.step / state.total) * 100;
  progressFill.style.width = pct + '%';
  statusMsg.textContent = `Шаг ${state.step}/${state.total}: ${state.message}`;

  logEl.innerHTML = state.log.map((line, i) => {
    const isLast = i === state.log.length - 1;
    const cls = isLast && state.status === 'running' ? 'current' : 'done';
    const icon = cls === 'done' ? '✓' : '⏳';
    return `<div class="step ${cls}">${icon} ${line}</div>`;
  }).join('');
  logEl.scrollTop = logEl.scrollHeight;
}

function renderResult(result) {
  let html = '';

  if (result.video_url) {
    html += `<div class="card">
      <h3>✅ Сгенерированное видео</h3>
      <video src="${result.video_url}" controls autoplay></video>
      <p class="meta"><a href="${result.video_url}" target="_blank">Открыть в новой вкладке →</a></p>
    </div>`;
  }

  if (result.format_info) {
    const f = result.format_info;
    html += `<div class="card">
      <h3>🎯 Найденный вирусный формат</h3>
      <p><strong>${escapeHtml(f.format_name || '')}</strong> (уверенность: ${escapeHtml(f.confidence || '?')})</p>
      <p>${escapeHtml(f.description || '')}</p>
      <p class="meta"><strong>Почему вирусный:</strong> ${escapeHtml(f.why_viral || '')}</p>
    </div>`;
  }

  if (result.author && result.top_videos && result.top_videos.length) {
    html += `<div class="card">
      <h3>📹 Топ-автор: @${escapeHtml(result.author)}</h3>
      ${result.top_videos.map(v => `
        <div class="top-vid">
          👁 ${v.views.toLocaleString()} · ${escapeHtml(v.title || '(без описания)')}
          ${v.url ? ` · <a href="${v.url}" target="_blank">открыть</a>` : ''}
        </div>
      `).join('')}
    </div>`;
  }

  if (!html) {
    html = `<div class="card">Задача завершилась, но результат пуст.</div>`;
  }

  resultBox.innerHTML = html;
}

function renderError(state) {
  let html = `<div class="card"><div class="err">❌ ${escapeHtml(state.error || 'Ошибка')}</div></div>`;
  if (state.result) {
    // Show partial data if pipeline failed midway
    const fakeOk = { ...state.result, video_url: null };
    resultBox.innerHTML = html;
    if (state.result.format_info || state.result.author) {
      renderResultPartial(state.result);
    }
  } else {
    resultBox.innerHTML = html;
  }
}

function renderResultPartial(result) {
  let html = resultBox.innerHTML;
  if (result.format_info) {
    const f = result.format_info;
    html += `<div class="card">
      <h3>🎯 Найден формат (видео не сгенерировано)</h3>
      <p><strong>${escapeHtml(f.format_name || '')}</strong></p>
      <p>${escapeHtml(f.description || '')}</p>
    </div>`;
  }
  if (result.author && result.top_videos) {
    html += `<div class="card">
      <h3>📹 Топ-автор: @${escapeHtml(result.author)}</h3>
      ${result.top_videos.map(v => `<div class="top-vid">👁 ${v.views.toLocaleString()} · ${escapeHtml(v.title || '')}</div>`).join('')}
    </div>`;
  }
  resultBox.innerHTML = html;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
</script>
</body>
</html>
"""


@app.route('/', methods=['GET'])
def index():
    return render_template_string(INDEX_HTML)


@app.route('/search', methods=['POST'])
def search_endpoint():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Query is required'}), 400

    job_id = _new_job(query)
    thread = threading.Thread(target=_run_job, args=(job_id, query), daemon=True)
    thread.start()
    return jsonify({'job_id': job_id})


@app.route('/status/<job_id>', methods=['GET'])
def status_endpoint(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        return jsonify({
            'status': job['status'],
            'step': job['step'],
            'total': job['total'],
            'message': job['message'],
            'log': job['log'],
            'result': job['result'],
            'error': job['error'],
        })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
