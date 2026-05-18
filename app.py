import os
import sys
from flask import Flask, request, jsonify, render_template_string
sys.path.insert(0, os.path.dirname(__file__))
import tiktok_search

app = Flask(__name__)


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
  .wrap { max-width: 760px; margin: 0 auto; }
  h1 { margin: 0 0 8px; font-size: 24px; }
  p.muted { color: #888; margin: 0 0 24px; }
  form { display:flex; gap:8px; margin-bottom: 24px; }
  input[type=text] { flex:1; padding: 12px 14px; font-size:16px; border-radius:8px; border:1px solid #333; background:#1a1a1f; color:#eee; }
  button { padding: 12px 20px; font-size:16px; border-radius:8px; border:0; background:#ff2d55; color:#fff; cursor:pointer; font-weight:600; }
  button:disabled { opacity:0.5; cursor:wait; }
  .card { background:#1a1a1f; border:1px solid #2a2a30; border-radius:12px; padding:16px; margin-bottom:12px; }
  .card .meta { color:#888; font-size:14px; margin-bottom:8px; }
  .card .text { font-size:15px; line-height:1.4; margin-bottom:8px; }
  .card a { color:#4cc2ff; text-decoration:none; }
  .stat { display:inline-block; margin-right:14px; font-size:14px; }
  .status { padding: 12px; border-radius:8px; margin-bottom: 16px; }
  .status.loading { background:#2a2a30; color:#aaa; }
  .status.error { background:#3a1a1a; color:#ff6b6b; }
</style>
</head>
<body>
  <div class="wrap">
    <h1>🔥 Поиск вирусных TikTok</h1>
    <p class="muted">Введи слово — получишь 5 видео с 1M+ просмотров.</p>

    <form id="searchForm">
      <input type="text" id="query" placeholder="например: fitness" required>
      <button type="submit" id="submitBtn">Найти</button>
    </form>

    <div id="status"></div>
    <div id="results"></div>
  </div>

<script>
const form = document.getElementById('searchForm');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const btn = document.getElementById('submitBtn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('query').value.trim();
  if (!query) return;

  btn.disabled = true;
  resultsEl.innerHTML = '';
  statusEl.innerHTML = '<div class="status loading">⏳ Ищу видео (30-90 сек, потерпи)...</div>';

  try {
    const res = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Ошибка сервера');

    statusEl.innerHTML = `<div class="status">✅ Найдено: ${data.videos_found} (показаны первые ${data.data.length})</div>`;

    if (!data.data || data.data.length === 0) {
      resultsEl.innerHTML = '<div class="card">Видео не найдены. Попробуй другое слово.</div>';
      return;
    }

    resultsEl.innerHTML = data.data.map(v => {
      const text = v.text || v.title || '(без описания)';
      const views = v.views || v.playCount || 0;
      const likes = v.likes || v.diggCount || 0;
      const author = v.authorMeta?.name || v.username || v.author || 'unknown';
      const url = v.webVideoUrl || v.url || '#';
      return `
        <div class="card">
          <div class="meta">@${author}</div>
          <div class="text">${text.slice(0, 200)}${text.length > 200 ? '…' : ''}</div>
          <div>
            <span class="stat">👁 ${views.toLocaleString()}</span>
            <span class="stat">❤️ ${likes.toLocaleString()}</span>
          </div>
          <div style="margin-top:8px"><a href="${url}" target="_blank">Открыть в TikTok →</a></div>
        </div>
      `;
    }).join('');
  } catch (err) {
    statusEl.innerHTML = `<div class="status error">❌ ${err.message}</div>`;
  } finally {
    btn.disabled = false;
  }
});
</script>
</body>
</html>
"""


@app.route('/', methods=['GET'])
def index():
    return render_template_string(INDEX_HTML)


@app.route('/search', methods=['POST'])
def search_endpoint():
    """API endpoint to search viral TikTok formats"""
    data = request.get_json() or {}
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    try:
        # Run the search pipeline
        result = tiktok_search.search_viral_videos(query, min_views=1_000_000, max_results=20)
        return jsonify({
            'status': 'success',
            'videos_found': len(result),
            'data': result[:5]  # Return first 5
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
