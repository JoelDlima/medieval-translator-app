#!/usr/bin/env python3
"""
Proxy server that serves the frontend and proxies API calls to the backend.
This allows the tunnel to work properly for both local and remote users.
"""

import os
import sys
from flask import Flask, request, jsonify, send_from_directory, send_file
import requests

app = Flask(__name__)

# Backend configuration
BACKEND_URL = "http://localhost:5000"
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

@app.route('/')
def index():
    """Redirect root to frontend"""
    return send_file(os.path.join(FRONTEND_DIR, 'index.html'))

@app.route('/frontend/')
def frontend_index():
    """Serve frontend index"""
    return send_file(os.path.join(FRONTEND_DIR, 'index.html'))

@app.route('/frontend/<path:filename>')
def frontend_files(filename):
    """Serve frontend static files"""
    return send_from_directory(FRONTEND_DIR, filename)

@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files from frontend directory"""
    try:
        return send_from_directory(FRONTEND_DIR, filename)
    except:
        # If file not found, return 404 JSON for API calls, or HTML for others
        if filename.startswith('api/'):
            return jsonify({'error': 'API endpoint not found'}), 404
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/translate', methods=['POST', 'OPTIONS'])
def proxy_translate():
    """Proxy translate requests to backend"""
    if request.method == 'OPTIONS':
        # Handle CORS preflight
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        # Forward request to backend
        backend_response = requests.post(
            f"{BACKEND_URL}/translate",
            json=request.get_json(),
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        # Return backend response
        response = jsonify(backend_response.json())
        response.status_code = backend_response.status_code
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response
        
    except requests.exceptions.ConnectionError:
        return jsonify({
            'error': 'Backend server not running',
            'details': 'Make sure the Flask backend is running on port 5000'
        }), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Backend timeout'}), 504
    except Exception as e:
        return jsonify({'error': 'Proxy error', 'details': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        backend_response = requests.get(f"{BACKEND_URL}/healthz", timeout=5)
        return jsonify({
            'status': 'ok',
            'frontend': 'running',
            'backend': 'running' if backend_response.status_code == 200 else 'error'
        })
    except:
        return jsonify({
            'status': 'partial',
            'frontend': 'running',
            'backend': 'not running'
        }), 503

if __name__ == '__main__':
    print("🏰 Medieval Translator Proxy Server")
    print("Frontend: http://localhost:3000")
    print("Health: http://localhost:3000/health")
    print("Make sure backend is running on http://localhost:5000")
    print("For tunnel: Use port 3000 instead of 8000")
    print()
    app.run(host='0.0.0.0', port=3000, debug=True)
