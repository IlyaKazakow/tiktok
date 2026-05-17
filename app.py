import os
import sys
from flask import Flask, request, jsonify
sys.path.insert(0, os.path.dirname(__file__))
import tiktok_search

app = Flask(__name__)

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
