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
            "direct": "/direct?url=STREAM_URL (solo .m3u8/.ts - redirección directa)",
            "proxy": "/proxy?url=STREAM_URL (archivos pesados .mkv/.avi/.mp4)",
            "validate": "/validate?url=STREAM_URL (validar sin transferir)",
            "auto": "El servidor decide automáticamente qué método usar"
        },
        "note": "Archivos pesados y dominios IPTV específicos usan proxy automáticamente"
    })

@app.route("/direct")
def direct_redirect():
    """Redirección directa - NO consume ancho de banda del servidor"""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    # VALIDACIÓN: Archivos pesados DEBEN usar proxy, no redirección directa
    if ('.mkv' in url.lower() or '.avi' in url.lower() or 
        '.mp4' in url.lower() or '/movie/' in url.lower() or
        'e98asvyr.okfsdo.xyz' in url.lower() or 'kcdrdbcx.upne.xyz' in url.lower()):
        
        logging.warning(f"🚫 Archivo pesado detectado, requiere proxy: {url[:100]}...")
        return jsonify({
            "error": "Este tipo de archivo requiere proxy tradicional",
            "suggestion": "use_proxy",
            "proxy_url": f"/proxy?url={quote(url)}",
            "reason": "Archivos .mkv/.avi/.mp4 y URLs de películas necesitan headers específicos"
        }), 400

    # Validar URL (solo para streams compatibles)
    if not is_valid_stream_url(url):
        return jsonify({"error": "URL no válida o inaccesible"}), 400

    logging.info(f"🔄 Redirección directa a: {url[:100]}...")
    
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
    """Proxy tradicional - OPTIMIZADO para archivos pesados (.mkv, .avi, .mp4)"""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Parámetro 'url' requerido"}), 400

    logging.info(f"🔄 Proxy para archivo pesado: {url[:100]}...")

    # Headers optimizados según el dominio/tipo de archivo
    headers = {
        'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18',
        'Accept': '*/*',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache'
    }

    # Headers específicos por dominio IPTV
    if 'kcdrdbcx.upne.xyz' in url:
        headers.update({
            'Referer': 'https://185.233.16.71/',
            'Origin': 'https://185.233.16.71'
        })
        logging.info("🔧 Headers aplicados para kcdrdbcx.upne.xyz")
    elif 'e98asvyr.okfsdo.xyz' in url:
        headers.update({
            'Referer': 'http://185.233.16.71/',
            'Origin': 'http://185.233.16.71'
        })
        logging.info("🔧 Headers aplicados para e98asvyr.okfsdo.xyz")

    # Agregar Range header si lo solicita el cliente
    range_header = request.headers.get('Range')
    if range_header:
        headers['Range'] = range_header
        logging.info(f"📊 Range request: {range_header}")

    try:
        req = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(req, timeout=30)

        content_type = response.getheader("Content-Type", "application/octet-stream")
        content_length = response.getheader("Content-Length")

        logging.info(f"✅ Conexión exitosa - Content-Type: {content_type}")

        def generate():
            # Chunks más grandes para archivos pesados
            chunk_size = 32768  # 32KB chunks
            total_bytes = 0
            
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                
                yield chunk
                total_bytes += len(chunk)
                
                # Log progreso cada 5MB para archivos grandes
                if total_bytes % (5 * 1024 * 1024) == 0:
                    logging.info(f"📊 Transferidos: {total_bytes // (1024*1024)}MB")
            
            logging.info(f"✅ Transferencia completada: {total_bytes // (1024*1024)}MB total")

        proxy_response = Response(generate(), content_type=content_type)
        proxy_response.headers["Access-Control-Allow-Origin"] = "*"
        proxy_response.headers["Cache-Control"] = "no-cache"
        
        # Pasar headers importantes para reproducción
        for header in ['Content-Length', 'Accept-Ranges', 'Content-Range']:
            value = response.getheader(header)
            if value:
                proxy_response.headers[header] = value

        # Status code apropiado para Range requests
        if range_header and response.getcode() == 206:
            proxy_response.status_code = 206

        return proxy_response

    except HTTPError as e:
        logging.error(f"❌ HTTPError {e.code}: {e.reason} para {url[:50]}")
        return jsonify({"error": f"Error HTTP {e.code}: {e.reason}"}), 502
    except URLError as e:
        logging.error(f"❌ URLError: {e.reason} para {url[:50]}")
        return jsonify({"error": f"Error de conexión: {e.reason}"}), 502
    except Exception as e:
        logging.error(f"❌ Error general: {str(e)} para {url[:50]}")
        return jsonify({"error": "Error interno en el proxy"}), 500

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
    
    # NUNCA redirección directa para archivos pesados o dominios IPTV específicos
    forbidden_patterns = [
        '.mkv', '.avi', '.mp4',
        '/movie/', '/serie/',
        'e98asvyr.okfsdo.xyz', 'kcdrdbcx.upne.xyz'
    ]
    
    for pattern in forbidden_patterns:
        if pattern in url.lower():
            return False
    
    # URLs que SÍ funcionan con redirección directa
    direct_compatible = [
        '.m3u8',
        '.ts'
    ]
    
    return any(url.lower().endswith(ext) for ext in direct_compatible)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
