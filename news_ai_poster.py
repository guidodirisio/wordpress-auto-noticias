import os, requests, base64, datetime
from zoneinfo import ZoneInfo      # Para manejar huso horario
from bs4 import BeautifulSoup      # Para parsear HTML y extraer contenido
import feedparser                 # Para leer fuentes RSS (Google News)
import openai                      # Cliente de OpenAI API

# Leer variables de entorno (credenciales y configuraciones)
WP_SITE = os.environ["WP_SITE"]       # URL del sitio WordPress, ej: "https://interesgeneral.com.ar"
WP_USER = os.environ["WP_USER"]       # Usuario de WP
WP_PASS = os.environ["WP_PASS"]       # Contraseña de aplicación de WP
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]  # Clave de API de OpenAI
CATEGORY_ID = os.environ["NEWS_CATEGORY_ID"]   # ID de categoría "Noticias"
openai.api_key = OPENAI_API_KEY       # Configurar clave para OpenAI

# Lista de fuentes/portales para rotar en horarios no principales
news_sources = [
    {"name": "Clarín - Internacional", "url": "https://www.clarin.com/rss/lo-ultimo/"},
    {"name": "La Nación - Deportes", "url": "https://www.lanacion.com.ar/rss/deportes/"},
    {"name": "TN - Sociedad", "url": "https://tn.com.ar/rss/sociedad.xml"},
    {"name": "Infobae - Economía", "url": "https://www.infobae.com/feeds/rss/economia.xml"},
    {"name": "Ámbito - Últimas", "url": "https://www.ambito.com/ultimo-momento.xml"},
    {"name": "El Canciller - Política", "url": "https://elcanciller.com/rss"} 
]


# Determinar hora actual en Argentina
now = datetime.datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
current_hour = now.hour
current_minute = now.minute

use_google_news = False
if current_hour == 8 and current_minute == 30:
    use_google_news = True
if current_hour == 18 and current_minute == 30:
    use_google_news = True

if use_google_news:
    feed_url = "https://news.google.com/rss?hl=es-419&gl=AR&ceid=AR:es-419"
    feed = feedparser.parse(feed_url)
    if feed.entries:
        top_entry = feed.entries[0]
        original_title = top_entry.title
        original_url = top_entry.link
    else:
        print("Google News RSS sin entradas.")
        # Si no se pudo obtener nada de Google News, salimos del script.
        exit(0)

else:
    # Seleccionar una fuente de la lista en función de la hora actual (ejemplo de rotación)
    index = (current_hour // 2) % len(news_sources)
    source = news_sources[index]
    source_name = source["name"]
    source_url = source["url"]
    print(f"Fuente seleccionada: {source_name} - {source_url}")
    # Obtener la noticia más reciente de esa fuente (suponiendo que es RSS)
    if source_url.endswith(".xml") or source_url.endswith("/rss") or source_url.endswith("/rss/"):
        feed = feedparser.parse(source_url)
        if feed.entries:
            entry = feed.entries[0]
            original_title = entry.title
            original_url = entry.link
        else:
            print(f"No se encontraron entradas en {source_name}.")
            exit(0)
    else:
        # Si la fuente no es RSS sino una página HTML, hacer scraping:
        resp = requests.get(source_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        # (Aquí se debería extraer el enlace de la noticia principal de la página)
        # Esto es muy específico de cada portal; como ejemplo básico:
        first_article = soup.find('a')  # *Esto se debe ajustar según la estructura real*
        if not first_article:
            print(f"No se pudo extraer noticia de {source_name}")
            exit(0)
        original_url = first_article['href']
        original_title = first_article.get_text() or "Título no disponible"


# Descargar la página de la noticia original
headers = {"User-Agent": "Mozilla/5.0"}  # Cabecera de agente para simular navegador
try:
    resp = requests.get(original_url, headers=headers, timeout=10)
except Exception as e:
    print(f"Error al solicitar la noticia original: {e}")
    exit(0)

if resp.status_code != 200:
    print(f"No se pudo obtener la noticia, código {resp.status_code}")
    exit(0)

html = resp.text
soup = BeautifulSoup(html, "html.parser")

# Extraer título (si no lo teníamos de antes o para confirmarlo)
page_title = ""
title_tag = soup.find('meta', property='og:title')
if title_tag and title_tag.get("content"):
    page_title = title_tag["content"]
else:
    # fallback: buscar <title> o <h1>
    if soup.title:
        page_title = soup.title.get_text()
    elif soup.find('h1'):
        page_title = soup.find('h1').get_text()
# Usaremos el título de la página preferentemente, pero 
# mantenemos original_title como respaldo
if page_title:
    original_title = page_title.strip()

# Extraer primeros 2-3 párrafos del cuerpo
paragraphs = soup.find_all('p')
content_text = ""
para_count = 0
for p in paragraphs:
    text = p.get_text().strip()
    # Omite párrafos vacíos o muy cortos que puedan ser subtítulos o datos irrelevantes
    if len(text) < 30:
        continue
    content_text += text + "\n\n"
    para_count += 1
    if para_count >= 3:
        break

if not content_text:
    content_text = "(No se pudo extraer el contenido del artículo)"

# Extraer URL de imagen destacada
img_url = None
img_tag = soup.find('meta', property='og:image')
if img_tag and img_tag.get("content"):
    img_url = img_tag["content"]
else:
    img_tag = soup.find('meta', attrs={"name": "twitter:image"})
    if img_tag and img_tag.get("content"):
        img_url = img_tag["content"]
# Si aún no, buscar la primera <img> en el contenido
if not img_url:
    first_img = soup.find('img')
    if first_img and first_img.get("src"):
        img_url = first_img["src"]

# Descargar la imagen si hay URL
image_data = None
if img_url:
    try:
        img_resp = requests.get(img_url, headers=headers, timeout=10)
        if img_resp.status_code == 200:
            image_data = img_resp.content  # bytes de la imagen
    except Exception as e:
        print(f"No se pudo descargar la imagen: {e}")
        image_data = None

# Preparar prompt para OpenAI
prompt = (
    "Reformula la siguiente noticia en un tono informativo, neutro y factual.\n"
    "1. Crea un título nuevo de máximo 20 palabras.\n"
    "2. Escribe un cuerpo (texto principal) de exactamente 100 caracteres.\n\n"
    f"Título original: {original_title}\n"
    f"Contenido original: {content_text}\n\n"
    "Devuelve la respuesta con el formato:\n"
    "TÍTULO: <nuevo título>\n"
    "CUERPO: <texto de 100 caracteres>\n"
)
try:
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0  # 0 para mayor determinismo en la respuesta
    )
except Exception as e:
    print(f"Error al llamar a OpenAI API: {e}")
    exit(0)

reply = response['choices'][0]['message']['content']
# Parsear la respuesta para separar título y cuerpo
new_title = ""
new_body = ""
for line in reply.splitlines():
    line = line.strip()
    if line.lower().startswith("título"):
        new_title = line.split(":", 1)[1].strip()
    elif line.lower().startswith("cuerpo"):
        new_body = line.split(":", 1)[1].strip()
# En caso de que la respuesta no viniera formateada como esperamos:
if not new_title or not new_body:
    # Como respaldo, tomar la primera línea como título y el resto como cuerpo
    lines = reply.splitlines()
    if lines:
        new_title = lines[0].strip()
        new_body = "".join(lines[1:]).strip()
# Asegurar que el cuerpo tenga exactamente 100 caracteres
new_body = new_body.strip()
if len(new_body) != 100:
    # Si es más largo, recortar; si es más corto, podemos rellenar con un espacio o ajustar.
    new_body = new_body[:100]
    new_body = new_body.ljust(100)[:100]

media_id = None
if image_data:
    media_endpoint = f"{WP_SITE}/wp-json/wp/v2/media"
    filename = "destacada.jpg"
    try:
        media_resp = requests.post(
            media_endpoint,
            auth=(WP_USER, WP_PASS),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
            files={"file": image_data}
        )
    except Exception as e:
        print(f"Error al subir imagen destacada: {e}")
        media_resp = None
    if media_resp and media_resp.status_code == 201:
        media_id = media_resp.json().get("id")
        print(f"Imagen subida. ID={media_id}")
    else:
        if media_resp:
            print(f"No se pudo subir la imagen. Código: {media_resp.status_code}, Respuesta: {media_resp.text}")

# Construir el contenido del post incluyendo la fuente original
post_content = new_body.strip()
post_content += f"\n\n<p>Fuente: <a href=\"{original_url}\" target=\"_blank\">Ver noticia original</a></p>"

# Construir los datos del post
post_data = {
    "title": new_title.strip(),
    "content": post_content,
    "status": "draft",             # Publicar como borrador
    "categories": [int(CATEGORY_ID)],  # Asignar categoría "Noticias"
    "format": "standard"          # Formato estándar de post
}
if media_id:
    post_data["featured_media"] = media_id

# Enviar petición para crear el post
posts_endpoint = f"{WP_SITE}/wp-json/wp/v2/posts"
try:
    post_resp = requests.post(posts_endpoint, auth=(WP_USER, WP_PASS), json=post_data)
except Exception as e:
    print(f"Error al crear la entrada de WP: {e}")
    exit(0)

if post_resp.status_code == 201:
    post_id = post_resp.json().get("id")
    print(f"Entrada de WordPress creada exitosamente (ID={post_id})")
else:
    print(f"Fallo al crear entrada. Código: {post_resp.status_code}, Respuesta: {post_resp.text}")
