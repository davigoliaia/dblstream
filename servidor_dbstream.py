
#!/usr/bin/env python3
"""
servidor_dbstream.py - Servidor DBStream para Railway
Proxy de streams M3U8, MKV, TS compatible con entornos sin navegador
"""

from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import urllib.request
from urllib.parse import quote
from urllib.error import HTTPError, URLError
import os
import logging

# Configuración
PORT = int(os.environ.get("PORT", 8000))  # Railway usa PORT dinámico
app = Flask(__name__)
CORS(app)

# Configurar logging básico
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "Servidor DBStream activo",
        "endpoints": {
            "proxy": "/proxy?url=STREAM_URL"
        }
    })

@app.route("/proxy")
def proxy():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    logging.info(f"🔄 Proxy solicitado para: {url}")

    headers = {
        'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18',
        'Accept': '*/*',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=30)

        content_type = response.getheader("Content-Type", "application/octet-stream")
        content_length = response.getheader("Content-Length")

        def generate():
            chunk_size = 8192
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        proxy_response = Response(generate(), content_type=content_type)
        proxy_response.headers["Access-Control-Allow-Origin"] = "*"
        proxy_response.headers["Cache-Control"] = "no-cache"
        if content_length:
            proxy_response.headers["Content-Length"] = content_length

        return proxy_response

    except HTTPError as e:
        logging.error(f"❌ HTTPError {e.code}: {e.reason}")
        return jsonify({"error": f"Error HTTP {e.code}: {e.reason}"}), 502
    except URLError as e:
        logging.error(f"❌ URLError: {e.reason}")
        return jsonify({"error": f"Error de conexión: {e.reason}"}), 502
    except Exception as e:
        logging.error(f"❌ Error general: {str(e)}")
        return jsonify({"error": "Error interno en el proxy"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
