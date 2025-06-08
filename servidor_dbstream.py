
#!/usr/bin/env python3
"""
servidor_dbstream_optimizado.py - Servidor con redirección directa
Minimiza el tráfico del servidor usando redirects y URLs temporales
"""

from flask import Flask, request, Response, jsonify, redirect
from flask_cors import CORS
import urllib.request
from urllib.parse import quote, urlparse
from urllib.error import HTTPError, URLError
import os
import logging
import time
import hashlib

# Configuración
PORT = int(os.environ.get("PORT", 8000))
app = Flask(__name__)
CORS(app)

# Cache de URLs validadas (evita validar repetidamente)
url_cache = {}
CACHE_TTL = 300  # 5 minutos

logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "Servidor DBStream Optimizado",
        "endpoints": {
            "direct": "/direct?url=STREAM_URL (redirección directa)",
            "proxy": "/proxy?url=STREAM_URL (proxy tradicional)",
            "validate": "/validate?url=STREAM_URL (solo validar)"
        }
    })

@app.route("/direct")
def direct_redirect():
    """Redirección directa - NO consume ancho de banda del servidor"""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    # Validar URL primero (opcional)
    if not is_valid_stream_url(url):
        return jsonify({"error": "URL no válida o inaccesible"}), 400

    logging.info(f"🔄 Redirección directa a: {url}")
    
    # Redirección 302 - el cliente conecta directamente al stream
    return redirect(url, code=302)

@app.route("/validate")
def validate_url():
    """Solo valida si la URL funciona sin transferir datos"""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    try:
        # Solo hacer HEAD request para verificar
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'VLC/3.0.18 LibVLC/3.0.18')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            content_type = response.getheader("Content-Type", "")
            content_length = response.getheader("Content-Length", "unknown")
            
            return jsonify({
                "status": "valid",
                "url": url,
                "content_type": content_type,
                "content_length": content_length
            })
    
    except Exception as e:
        logging.error(f"❌ Validación falló: {str(e)}")
        return jsonify({
            "status": "invalid",
            "error": str(e)
        }), 400

@app.route("/proxy")
def proxy():
    """Proxy tradicional - solo usar si la redirección directa falla"""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    # Verificar si realmente necesita proxy
    if can_use_direct(url):
        logging.info(f"🔀 Recomendando redirección directa para: {url}")
        return jsonify({
            "suggestion": "use_direct",
            "direct_url": f"/direct?url={quote(url)}",
            "message": "Esta URL puede usar redirección directa para mejor rendimiento"
        })

    logging.info(f"🔄 Proxy requerido para: {url}")

    headers = {
        'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18',
        'Accept': '*/*',
        'Range': request.headers.get('Range', '')  # Soporte para ranges
    }

    try:
        req = urllib.request.Request(url, headers={k:v for k,v in headers.items() if v})
        response = urllib.request.urlopen(req, timeout=30)

        content_type = response.getheader("Content-Type", "application/octet-stream")
        
        def generate():
            # Chunks más grandes para reducir overhead
            chunk_size = 32768  # 32KB chunks
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        proxy_response = Response(generate(), content_type=content_type)
        proxy_response.headers["Access-Control-Allow-Origin"] = "*"
        
        # Pasar headers importantes
        for header in ['Content-Length', 'Accept-Ranges', 'Content-Range']:
            value = response.getheader(header)
            if value:
                proxy_response.headers[header] = value

        return proxy_response

    except Exception as e:
        logging.error(f"❌ Error en proxy: {str(e)}")
        return jsonify({"error": "Error en el proxy"}), 500

def is_valid_stream_url(url):
    """Cache de validación para evitar verificaciones repetidas"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    current_time = time.time()
    
    # Verificar cache
    if url_hash in url_cache:
        cached_time, is_valid = url_cache[url_hash]
        if current_time - cached_time < CACHE_TTL:
            return is_valid
    
    # Validar URL
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'VLC/3.0.18 LibVLC/3.0.18')
        urllib.request.urlopen(req, timeout=5)
        
        # Guardar en cache
        url_cache[url_hash] = (current_time, True)
        return True
    except:
        url_cache[url_hash] = (current_time, False)
        return False

def can_use_direct(url):
    """Determina si una URL puede usar redirección directa"""
    parsed = urlparse(url)
    
    # URLs que típicamente funcionan con redirección directa
    direct_compatible = [
        '.m3u8',
        '.ts',
        '.mp4',
        '.mkv',
        '.avi'
    ]
    
    return any(url.lower().endswith(ext) for ext in direct_compatible)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
