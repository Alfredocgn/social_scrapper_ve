# social_scrapper_ve

Monitor para centralizar publicaciones de redes sobre eventos en Venezuela
(arrancó con el terremoto del 24 de junio de 2026). Recolecta posts vía Apify,
los guarda en SQLite y muestra un dashboard con **tendencias recientes** y las
publicaciones separadas por tipo de media (videos / imágenes / texto).

## Uso

```bash
cp .env.example .env   # completa APIFY_TOKEN
python3 app.py
```

Abre `http://127.0.0.1:8000`.

Pruebas rápidas de extremo a extremo:

```bash
python3 app.py --self-test
```

## Qué hace

1. **Recolecta** — cada `POLL_SECONDS` corre un actor de Apify (Instagram por
   hashtags) y normaliza los resultados.
2. **Centraliza** — guarda en SQLite evitando duplicados (`unique(source, external_id)`)
   y registra el tipo de media y la fecha real del post.
3. **Analiza tendencias** — calcula los términos más hablados *recientemente*,
   ponderando cada post por su frescura (decaimiento por vida media) y por su
   engagement (likes + comentarios).
4. **Categoriza** — guarda los `hashtags` (normalizados sin acentos ni emojis
   para unir variantes) y muestra los más frecuentes como categorías navegables.
5. **Refresca** — los posts ya vistos se actualizan (upsert) para reflejar su
   evolución de engagement, no solo la primera captura.
6. **Muestra** — dashboard auto-refrescante con resumen, tendencias, categorías
   y secciones por tipo de media. También expone `GET /api/trends` (JSON).

### Reels y vistas

El dashboard tiene una sección **🎬 Reels más vistos**. El pipeline captura el
número de reproducciones (`videoViewCount` / `videoPlayCount`) cuando la fuente
lo entrega, y rankea por vistas; si no hay vistas, cae a likes + comentarios.

> Aviso: el scraper de Instagram por **hashtag** (actor `APIFY` por defecto) no
> devuelve el contador de vistas. Para tener vistas reales de reels, registra una
> segunda fuente con un actor especializado en reels (ver más abajo) que sí
> exponga `videoViewCount`/`videoPlayCount`.

### Múltiples fuentes

`apify.py` define las fuentes en `SOURCES` como `(nombre, prefijo_env)`. Cada
fuente lee `{PREFIJO}_TOKEN`, `{PREFIJO}_ACTOR_ID` y `{PREFIJO}_INPUT_JSON`.
Instagram usa el prefijo `APIFY`. Para agregar otra (p. ej. TikTok) basta con
registrar `("tiktok", "TIKTOK")` y definir esas tres variables; el resto del
pipeline (normalización, dedup, tendencias) funciona igual al ser agnóstico.

### Filtrado por categoría

Las chips de **Categorías** y **Tendencias** son clicables: al presionarlas el
dashboard se filtra a los posts que coinciden con ese término
(`GET /?q=<término>`), buscando tanto en el texto como en los hashtags. Un banner
permite quitar el filtro.

## Arquitectura (módulos)

| Archivo        | Responsabilidad                                              |
| -------------- | ----------------------------------------------------------- |
| `app.py`       | Entrypoint: CLI, arranque del poller y del servidor.        |
| `config.py`    | Carga de `.env` y helpers de entorno.                       |
| `db.py`        | Esquema, migración suave, consultas y filtrado SQLite.      |
| `normalize.py` | Normalización + detección de media, fecha y hashtags.       |
| `apify.py`     | Fuente de datos: ejecución del actor de Apify.              |
| `trends.py`    | Cálculo de trending topics ponderado por recencia.          |
| `poller.py`    | Loop de polling en background.                              |
| `render.py`    | Plantillas HTML del dashboard.                              |
| `server.py`    | Servidor HTTP y rutas (`/`, `/api/trends`).                |

> Las bases de datos creadas con versiones anteriores se **migran solas**:
> al iniciar se agregan las columnas nuevas (`created_ts`, `media_type`,
> `media_url`, `hashtags`) sin perder datos.

## Variables

| Variable                | Descripción                                              |
| ----------------------- | -------------------------------------------------------- |
| `APIFY_TOKEN`           | Token de Apify.                                          |
| `APIFY_ACTOR_ID`        | Actor de Instagram en Apify (`usuario/actor`).           |
| `APIFY_INPUT_JSON`      | JSON enviado al actor.                                   |
| `POLL_SECONDS`          | Frecuencia del polling (default 120).                    |
| `DATABASE_PATH`         | Ruta del SQLite.                                         |
| `HOST` / `PORT`         | Dirección del servidor.                                  |
| `UI_REFRESH_SECONDS`    | Auto-refresco del dashboard (default 15).                |
| `TREND_WINDOW_HOURS`    | Ventana de tiempo para tendencias (default 24).          |
| `TREND_HALF_LIFE_HOURS` | Vida media del peso por recencia (default 6).            |

Esto es polling, no streaming real: Apify entrega datos por corrida del actor.
Baja `POLL_SECONDS` si necesitas más frescura y tu cuota lo permite.
