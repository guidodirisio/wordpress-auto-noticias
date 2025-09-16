# news_ai_poster.py
import os, re, math, time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import trafilatura

# ---------- Config ----------
WP_SITE = os.getenv("WP_SITE", "").rstrip("/")
WP_USER = os.getenv("WP_USER")
WP_PASS = os.getenv("WP_PASS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_CATEGORY_ID = int(os.getenv("NEWS_CATEGORY_ID", "0"))  # obligatorio idealmente

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InteresGeneralBot/1.0; +https://interesgeneral.com.ar)"
}
TIMEOUT = 15

# Portales (home) y heurísticas de enlace "válido"
PORTALES = [
    "https://www.clarin.com/",
    "https://www.lanacion.com.ar/",
    "https://tn.com.ar/",
    "https://www.infobae.com/",
    "https://www.ambito.com/",
    "https://elcanciller.com/"
]

SECCIONES = ["politica", "economia", "internacional"]

# Palabras que suelen aparecer en URLs de notas (heurística simple)
ARTICLE_HINTS = [
    "/politica", "/economia", "/internacional", "/mundo", "/opinion", "/sociedad",
    "/deportes", "/show", "/negocios", "/n/","/nota","/noticia","/articulo","/202","/20"
]
# Evitar links no-nota
BLOCK_HINTS = ["/tag/", "/tags/", "/author", "/autores", "/suscripcion", "/subscribe",
               "/newsletter", "/temas", "/ayuda", "/faq", "/login", "/registro", "/terminos"]

# ---------- Helpers ----------
def elegir_portal_y_seccion():
    horas = math.floor(datetime.utcnow().timestamp()/3600)
    portal = PORTALES[horas % len(PORTALES)]
    seccion = SECCIONES[horas % len(SECCIONES)]
    return portal, seccion

def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text

def absolutize(base, href):
    if not href: return None
    if href.startswith("http"): return href
    if href.startswith("//"): return "https:" + href
    return urljoin(base, href)

def es_link_nota(base, href):
    if not href: return False
    href = absolutize(base, href)
    if not href: return False
    if urlparse(href).netloc not in urlparse(base).netloc:
        return False
    if any(b in href for b in BLOCK_HINTS):
        return False
    return any(h in href for h in ARTICLE_HINTS)

def encontrar_primer_link_nota(home_url, html, seccion_hint=None):
    soup = BeautifulSoup(html, "html.parser")
    # priorizar links que contengan la sección sugerida
    anchors = soup.find_all("a", href=True)
    # 1) si hay seccion, priorizamos
    if seccion_hint:
        for a in anchors:
            href = absolutize(home_url, a["href"])
            if href and seccion_hint in href and es_link_nota(home_url, href):
                return href
    # 2) si no, primer enlace "de nota" creíble
    for a in anchors:
        href = absolutize(home_url, a["href"])
        if es_link_nota(home_url, href):
            return href
    return None

def extraer_titulo_y_parrafos(url):
    # Usamos trafilatura para extraer main text y meta
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None, []
    
    json_text = trafilatura.extract(
    downloaded,
    include_comments=False,
    include_tables=False,
    favor_recall=True,
    output_format="json"
    )

    if not json_text:
        return None, []
    
    import json
    data = json.loads(json_text)
    titulo = data.get("title")
    texto = data.get("text") or ""
    paras = [p.strip() for p in texto.split("\n") if p.strip()]
    return titulo, paras[:3]


def extraer_imagen(url, fallback_html=None):
    # intentar metadatos con trafilatura primero
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        meta = trafilatura.extract(downloaded, output_format="json")
        if not meta:
            return None
        try:
            md = json.loads(meta)
        except json.JSONDecodeError:
            return None
        img = md.get("image")
        if img and img.startswith("http"):
            return img

    
    # fallback: parsear HTML si se pasó
    html = fallback_html or get_html(url)
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:image")
    if og and og.get("content"): return absolutize(url, og["content"])
    tw = soup.find("meta", attrs={"name":"twitter:image"})
    if tw and tw.get("content"): return absolutize(url, tw["content"])
    img = soup.find("img")
    if img and img.get("src"): return absolutize(url, img["src"])
    return None

def openai_reformatear(titulo, parrafos):
    """Devuelve (titulo_limpio, cuerpo_100_chars)."""
    body_src = (titulo or "") + "\n\n" + "\n\n".join(parrafos or [])
    body_src = body_src.strip()[:2000]  # limitar tokens de entrada
    # Prompt para garantizar formato exacto
    system = (
        "Sos redactor. Devolvés exactamente dos bloques:\n"
        "1) Una sola línea: TÍTULO (sin comillas)\n"
        "2) Una sola línea: CUERPO de EXACTAMENTE 100 caracteres (sin contar saltos de línea).\n"
        "Tono informativo, neutro, sin inventar datos."
    )
    user = (
        "Reescribí el siguiente material de noticia. Título en una línea, "
        "y luego CUERPO de exactamente 100 caracteres (cortá con criterio si hace falta):\n\n"
        f"{body_src}"
    )
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.2,
            max_tokens=180
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        # Fallback sin IA: recortar
        print("OpenAI error:", e)
        return (titulo[:120] if titulo else "Noticias"), compone_cuerpo_100(" ".join(parrafos) if parrafos else "")

    # Parsear dos líneas
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return (titulo[:120] if titulo else "Noticias"), compone_cuerpo_100(" ".join(parrafos) if parrafos else "")
    title_out = lines[0]
    body_out = lines[-1] if len(lines) > 1 else ""
    # Asegurar 100 caracteres exactos
    body_out = compone_cuerpo_100(body_out)
    return title_out, body_out

def compone_cuerpo_100(texto):
    # Limpia y ajusta a EXACTAMENTE 100 caracteres, sin cortar groseramente la última palabra
    s = re.sub(r"\s+", " ", texto).strip()
    if len(s) == 100:
        return s
    if len(s) > 100:
        # cortar a <=100, intentando no partir palabra
        cut = s[:100]
        # si cortó en medio de palabra, retrocede hasta espacio si existe
        if len(s) > 100 and not s[100:101].isspace():
            if " " in cut:
                cut = cut[:cut.rfind(" ")]
        return cut[:100].rstrip().ljust(100, " ")[:100]
    # si es más corto, rellena con espacios (para EXACTO 100). Si no querés rellenar, podés no hacerlo.
    return s.ljust(100, " ")[:100]

def upload_image_to_wp(img_url):
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        content = r.content
        # inferir mime por extensión
        ext = img_url.split("?")[0].split(".")[-1].lower()
        mime = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(ext,"image/jpeg")
        filename = os.path.basename(urlparse(img_url).path) or "image.jpg"
        media_url = f"{WP_SITE}/wp-json/wp/v2/media"
        mr = requests.post(
            media_url,
            headers={"Content-Type": mime, "Content-Disposition": f'attachment; filename="{filename}"'},
            data=content,
            auth=(WP_USER, WP_PASS),
            timeout=TIMEOUT
        )
        if mr.status_code in (200,201):
            return mr.json().get("id")
        print("Fallo media:", mr.status_code, mr.text[:300])
    except Exception as e:
        print("No se pudo subir imagen:", e)
    return None

def crear_post_wp(titulo, cuerpo100, fuente_url, imagen_id=None):
    post_url = f"{WP_SITE}/wp-json/wp/v2/posts"
    html = f"<p>{cuerpo100}</p>\n<p><strong>Fuente:</strong> <a href=\"{fuente_url}\" target=\"_blank\" rel=\"noopener\">Leer original</a></p>"
    data = {
        "title": titulo,
        "content": html,
        "status": "draft",
        "format": "standard"
    }
    if NEWS_CATEGORY_ID:
        data["categories"] = [NEWS_CATEGORY_ID]
    if imagen_id:
        data["featured_media"] = imagen_id
    pr = requests.post(post_url, json=data, auth=(WP_USER, WP_PASS), timeout=TIMEOUT)
    if pr.status_code in (200,201):
        out = pr.json()
        print("Borrador creado:", out.get("id"), out.get("link"))
    else:
        print("Error creando post:", pr.status_code, pr.text[:400])

def main():
    if not all([WP_SITE, WP_USER, WP_PASS]):
        raise SystemExit("Faltan WP_SITE / WP_USER / WP_PASS")
    if not OPENAI_API_KEY:
        print("Aviso: falta OPENAI_API_KEY, se usará fallback sin IA.")

    portal_home, seccion = elegir_portal_y_seccion()
    print("Portal:", portal_home, "- Sección:", seccion)

    # 1) Obtener home y primer link de nota
    home_html = get_html(portal_home)
    link = encontrar_primer_link_nota(portal_home, home_html, seccion_hint=seccion)
    if not link:
        raise SystemExit("No se encontró link de nota en el home")

    print("Artículo:", link)

    # 2) Extraer título + 3 párrafos
    titulo_src, parrafos = extraer_titulo_y_parrafos(link)
    if not titulo_src and not parrafos:
        raise SystemExit("No se pudo extraer contenido de la nota")

    # 3) Imagen
    img_url = extraer_imagen(link, fallback_html=home_html)
    feat_id = upload_image_to_wp(img_url) if img_url else None

    # 4) IA: TÍTULO + CUERPO 100 caracteres
    titulo_final, cuerpo_100 = openai_reformatear(titulo_src, parrafos)

    # 5) Crear post en WP (borrador)
    crear_post_wp(titulo_final, cuerpo_100, link, imagen_id=feat_id)

if __name__ == "__main__":
    main()

    print(f"Entrada de WordPress creada exitosamente (ID={post_id})")
else:
    print(f"Fallo al crear entrada. Código: {post_resp.status_code}, Respuesta: {post_resp.text}")
