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
6. **Detecta pedidos de ayuda** — analiza con IA cada post nuevo y extrae
   pedidos concretos (personas atrapadas, desaparecidos, rescates, refugios,
   suministros) con ubicación, contacto y nivel de confianza.
7. **Muestra** — dashboard auto-refrescante con pedidos de ayuda, resumen,
   tendencias, categorías y secciones por tipo de media. También expone
   `GET /api/trends` (JSON).

### Pedidos de ayuda (análisis con IA)

El módulo `analyze.py` manda cada post nuevo a un LLM y guarda una alerta
estructurada en la tabla `alertas`. La sección **🆘 Pedidos de ayuda** agrupa los
urgentes por municipio. Es una **ayuda a la priorización para humanos**, no una
fuente autoritativa: cada alerta muestra su nivel de confianza y enlaza a la fuente.

El cliente LLM (`llm.py`) es **genérico y compatible con OpenAI** (cero
dependencias, vía `urllib`): funciona con OpenAI, OpenRouter, Groq, modelos
locales, etc. Se configura con `LLM_API_KEY` (si falta, el análisis queda
inactivo), `LLM_MODEL` y, opcionalmente, `LLM_BASE_URL` —si no se define, se
infiere por el prefijo de la llave—.

### Reels y vistas

El dashboard tiene una sección **🎬 Reels más vistos**. El pipeline captura el
número de reproducciones (`videoViewCount` / `videoPlayCount`) cuando la fuente
lo entrega, y rankea por vistas; si no hay vistas, cae a likes + comentarios.

> Aviso: el scraper de Instagram por **hashtag** (actor `APIFY` por defecto) no
> devuelve el contador de vistas. Para vistas reales está registrada (inactiva)
> la fuente `instagram_reels`, que usa `apify/instagram-reel-scraper` —ese sí
> expone `videoViewCount`/`videoPlayCount`—. Ojo: ese actor scrapea **por cuenta
> o URL de reel, no por hashtag**, así que requiere una lista curada de cuentas.
> Se activa al definir `REELS_TOKEN`, `REELS_ACTOR_ID` y `REELS_INPUT_JSON`.

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
| `apify.py`     | Fuentes de datos: ejecución de actores de Apify.            |
| `trends.py`    | Cálculo de trending topics ponderado por recencia.          |
| `llm.py`       | Cliente LLM genérico compatible con OpenAI (cero deps).     |
| `analyze.py`   | Análisis con IA: extracción de pedidos de ayuda.            |
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
| `LLM_API_KEY`           | Llave del proveedor LLM (vacío = análisis inactivo).     |
| `LLM_BASE_URL`          | Endpoint LLM; si falta se infiere por el prefijo de la llave. |
| `LLM_MODEL`             | Modelo a usar (ej. `anthropic/claude-opus-4-8`).         |
| `ANALYZE_LIMIT`         | Máx. posts analizados por corrida (default 20).          |

Esto es polling, no streaming real: Apify entrega datos por corrida del actor.
Baja `POLL_SECONDS` si necesitas más frescura y tu cuota lo permite.
