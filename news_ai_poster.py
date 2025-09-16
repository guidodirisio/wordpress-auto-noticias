from pathlib import Path

# Código corregido usando urllib.request en lugar de request_kwargs
import os
import random
import requests
import trafilatura
import urllib.request

WP_SITE = os.getenv("WP_SITE")
WP_USER = os.getenv("WP_USER")
WP_PASS = os.getenv("WP_PASS")
TIMEOUT = 90

ARTICULOS = [
    {"url": "https://www.clarin.com/politica/escandalo-audios-ahora-abogado-cristina-denuncio-cerimedo-esposa-funcionaria-spagnuolo-andis_0_c***5oVC5FJ2.html", "seccion": "politica"},
    {"url": "https://www.ambito.com/economia/el-presupuesto-2026-preve-aumentos-jubilados-discapacitados-universidades-y-salud-n6***90773", "seccion": "economia"},
]

def extraer_titulo_y_cuerpo(link):
    req = urllib.request.Request(link, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/117.0.0.0 Safari/537.36'
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read().decode('utf-8')

    downloaded = trafilatura.extract(html, include_comments=False, include_tables=False, output_format="json")
    if not downloaded:
        raise Exception("No se pudo extraer contenido")

    import json
    parsed = json.loads(downloaded)
    titulo = parsed.get("title", "Sin título")
    texto = parsed.get("text", "").strip().replace("\\n", "<br><br>")
    cuerpo = texto + f'<br><br><p><strong>Fuente:</strong> <a href="{link}" target="_blank" rel="noopener">Ver nota original</a></p>'
    return titulo, cuerpo

def crear_post_wp(titulo, cuerpo, fuente_url):
    post_url = f"{WP_SITE}/wp-json/wp/v2/posts"
    data = {
        "title": titulo,
        "content": cuerpo,
        "status": "draft",
        "categories": [1],
        "format": "standard",
    }

    def post_with_retry(url, data, auth, timeout, max_retries=3):
        for intento in range(max_retries):
            try:
                return requests.post(url, json=data, auth=auth, timeout=timeout)
            except requests.exceptions.ReadTimeout:
                print(f"[{intento+1}/3] Timeout al conectar con WordPress. Reintentando en 10s...")
                import time; time.sleep(10)
        raise Exception("No se pudo crear el post tras varios intentos.")

    pr = post_with_retry(post_url, data, auth=(WP_USER, WP_PASS), timeout=TIMEOUT)
    if pr.status_code not in [200, 201]:
        raise Exception(f"Error al publicar: {pr.status_code} - {pr.text}")

    post_id = pr.json().get("id")
    print(f"Entrada creada en borrador (ID={post_id})")

def main():
    articulo = random.choice(ARTICULOS)
    link = articulo["url"]
    seccion = articulo["seccion"]
    print(f"Portal: {link.split('/')[2]} – Sección: {seccion}")
    print(f"Artículo: {link}")

    titulo, cuerpo = extraer_titulo_y_cuerpo(link)
    crear_post_wp(titulo, cuerpo, link)

if __name__ == "__main__":
    main()


# Guardar el archivo actualizado
path = Path("/mnt/data/news_ai_poster_fixed.py")
path.write_text(script_code.strip())

path.name

