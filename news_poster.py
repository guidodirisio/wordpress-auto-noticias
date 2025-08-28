import os
import requests
import feedparser
from bs4 import BeautifulSoup
import math
from datetime import datetime

# Mapas de portales y URLs de sus feeds RSS por sección
FEEDS = {
    "Clarin": {
        "politica": "https://www.clarin.com/rss/politica/",
        "economia": "https://www.clarin.com/rss/economia/",
        "internacional": "https://www.clarin.com/rss/mundo/"
    },
    "La Nacion": {
        "politica": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/politica/?outputType=xml",
        "economia": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/?outputType=xml",
        "internacional": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/mundo/?outputType=xml"
    },
    "TN": {
        "politica": "https://tn.com.ar/rss.xml",   # TN no tiene feeds por sección, usamos el general
        "economia": "https://tn.com.ar/rss.xml",
        "internacional": "https://tn.com.ar/rss.xml"
    }
}


def elegir_fuente_y_seccion():
    # Número de horas transcurridas (desde época Unix) como entero
    horas_desde_epoch = math.floor(datetime.utcnow().timestamp() / 3600)
    # Tenemos 3 portales y 3 secciones; calculamos índices cíclicos
    indice_portal = horas_desde_epoch % 4   # 0 a 3
    indice_seccion = horas_desde_epoch % 3  # 0 a 2
    # Mapear los índices a nombres reales
    portales = ["Clarin", "La Nacion", "TN"]
    secciones = ["politica", "economia", "internacional"]
    portal = portales[indice_portal]
    seccion = secciones[indice_seccion]
    return portal, seccion

# Elegir el portal y sección para esta ejecución
portal, seccion = elegir_fuente_y_seccion()

feed_url = FEEDS[portal][seccion]
feed = feedparser.parse(feed_url)

if not feed.entries:
    print(f"No se encontraron entradas en el feed {feed_url}")
    exit(1)  # Finaliza si no hay noticias
# Tomar la primera noticia del feed
entrada = feed.entries[0]
titulo = entrada.title
link_noticia = entrada.link

bajada = ""
if 'summary' in entrada:
    bajada = entrada.summary
elif 'description' in entrada:
    bajada = entrada.description
    

# Descargar la página de la noticia
resp = requests.get(link_noticia, timeout=10)
resp.encoding = resp.apparent_encoding  # Usar la codificación correcta si es detectada
html = resp.text

# Parsear el HTML para extraer párrafos
soup = BeautifulSoup(html, 'html.parser')
parrafos = soup.find_all('p')
contenido_parrafos = []
for p in parrafos:
    texto = p.get_text().strip()
    # Filtrar párrafos vacíos o muy cortos (ej. créditos, etc.)
    if texto and len(texto) > 40:
        contenido_parrafos.append(texto)
    if len(contenido_parrafos) >= 2:
        break

# Tomar hasta dos párrafos para el cuerpo
cuerpo = "\n\n".join(contenido_parrafos[:2])

# Construir el contenido HTML de la entrada
html_content = ""
if bajada:
    html_content += f"<p><em>{bajada}</em></p>\n"
if cuerpo:
    # Convertir saltos de línea en párrafos HTML
    for para in cuerpo.split("\n\n"):
        html_content += f"<p>{para}</p>\n"
# Añadir la fuente al final
nombre_fuente = portal if portal != "La Nacion" else "La Nación"
html_content += f"<p><strong>Fuente:</strong> <a href=\"{link_noticia}\" target=\"_blank\" rel=\"noopener\">{nombre_fuente}</a></p>"

# Preparar los datos de la nueva entrada de WordPress
post_data = {
    "title": titulo,
    "content": html_content,
    "status": "draft"  # Publicar como borrador
}

# Credenciales desde variables de entorno
wp_user = os.environ.get("WP_USER")
wp_pass = os.environ.get("WP_PASS")
wp_site = os.environ.get("WP_SITE", "https://interesgeneral.com.ar")

if not wp_user or not wp_pass:
    print("Error: Credenciales de WordPress no encontradas en las variables de entorno.")
    exit(1)

# Realizar la petición POST a la API REST de WordPress
api_url = wp_site.rstrip("/") + "/wp-json/wp/v2/posts"
response = requests.post(api_url, json=post_data, auth=(wp_user, wp_pass))

if response.status_code == 201:
    print(f"Entrada creada con éxito en WordPress: {titulo}")
else:
    print(f"Error al crear la entrada. Código: {response.status_code}, Respuesta: {response.text}")


