import os
import json
import random
import requests
import trafilatura

# CONFIGURACIÓN
WP_SITE = os.getenv("WP_SITE")
WP_USER = os.getenv("WP_USER")
WP_PASS = os.getenv("WP_PASS")
TIMEOUT = 90
CATEGORIA_ID = 1  # ← Cambiá si tu categoría "Noticias" tiene otro ID

# PORTALES Y SECCIONES
portales = {
    "https://www.clarin.com": ["politica", "economia", "internacional"],
    "https://www.lanacion.com.ar": ["politica", "economia", "internacional"],
    "https://www.tn.com.ar": ["politica", "economia", "internacional"],
    "https://www.ambito.com": ["politica", "economia", "internacional"]
}

# OBTENER RSS URL (puede mejorarse)
def construir_rss(portal, seccion):
    if "clarin" in portal:
        return f"https://www.clarin.com/rss/{seccion}/"
    elif "lanacion" in portal:
        return f"https://www.lanacion.com.ar/rss/{seccion}.xml"
    elif "tn.com.ar" in portal:
        return f"https://www.tn.com.ar/rss/{seccion}.xml"
    elif "ambito" in portal:
        return f"https://www.ambito.com/rss/secciones/{seccion}.xml"
    return None

# OBTENER LINK DE NOTA
def extraer_link_de_rss(rss_url):
    try:
        res = requests.get(rss_url, timeout=10)
        if "<item>" in res.text:
            partes = res.text.split("<item>")[1:]
            random.shuffle(partes)
            for parte in partes:
                if "<link>" in parte:
                    url = parte.split("<link>")[1].split("</link>")[0].strip()
                    return url
    except Exception as e:
        print("Error al leer RSS:", e)
    return None

# EXTRAER TEXTO DE NOTA
def extraer_titulo_y_parrafos(link):
    downloaded = trafilatura.fetch_url(link)
    if not downloaded:
        return None, []
    raw = trafilatura.extract(downloaded, output_format="json")
    if not raw:
        return None, []
    try:
        parsed = json.loads(raw)
        titulo = parsed.get("title")
        texto = parsed.get("text") or ""
        parrafos = [p.strip() for p in texto.split("\n") if len(p.strip()) > 40]
        return titulo, parrafos[:3]
    except Exception as e:
        print("Error al extraer título y texto:", e)
        return None, []

# INTENTAR EXTRAER IMAGEN
def extraer_imagen(link):
    try:
        downloaded = trafilatura.fetch_url(link)
        if not downloaded:
            return None
        meta = trafilatura.extract(downloaded, output_format="json")
        if not meta:
            return None
        md = json.loads(meta)
        img = md.get("image")
        if img and img.startswith("http"):
            return img
    except Exception as e:
        print("Error al extraer imagen:", e)
    return None

# SUBIR IMAGEN DESTACADA
def subir_imagen(img_url):
    try:
        r = requests.get(img_url, timeout=10)
        nombre = "destacada.jpg"
        headers = {"Content-Disposition": f"attachment; filename={nombre}"}
        subir = requests.post(
            f"{WP_SITE}/wp-json/wp/v2/media",
            headers=headers,
            data=r.content,
            auth=(WP_USER, WP_PASS),
            timeout=20
        )
        if subir.status_code == 201:
            return subir.json().get("id")
    except Exception as e:
        print("No se pudo subir imagen:", e)
    return None

# CREAR POST EN WORDPRESS
def crear_post_wp(titulo, cuerpo, fuente, imagen_id=None):
    post_url = f"{WP_SITE}/wp-json/wp/v2/posts"
    data = {
        "title": titulo,
        "content": f"{cuerpo}<br><br><a href='{fuente}' target='_blank'>Fuente</a>",
        "status": "draft",
        "categories": [CATEGORIA_ID],
        "format": "standard"
    }
    if imagen_id:
        data["featured_media"] = imagen_id
    pr = requests.post(post_url, json=data, auth=(WP_USER, WP_PASS), timeout=TIMEOUT)
    post_id = pr.json().get("id")
    print(f"Borrador creado: {post_id} → {WP_SITE}/?p={post_id}")

# FLUJO PRINCIPAL
def main():
    portal = random.choice(list(portales.keys()))
    secciones = portales[portal]
    seccion = random.choice(secciones)
    print(f"Portal: {portal} – Sección: {seccion}")

    rss = construir_rss(portal, seccion)
    if not rss:
        print("RSS no válido.")
        return

    link = extraer_link_de_rss(rss)
    if not link:
        print("No se encontró artículo.")
        return
    print(f"Artículo: {link}")

    titulo, parrafos = extraer_titulo_y_parrafos(link)
    if not titulo or not parrafos:
        print("No se pudo extraer contenido.")
        return

    cuerpo = "<br><br>".join(parrafos)
    img_url = extraer_imagen(link)
    feat_id = subir_imagen(img_url) if img_url else None

    crear_post_wp(titulo, cuerpo, link, imagen_id=feat_id)

if __name__ == "__main__":
    main()
