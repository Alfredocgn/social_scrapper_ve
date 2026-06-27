# social_scrapper_ve

Monitor mínimo para centralizar publicaciones sobre el terremoto en Venezuela del 24 de junio de 2026.

## Uso

```bash
cp .env.example .env
python3 app.py
```

Abre `http://127.0.0.1:8000`.

## Variables

- `APIFY_TOKEN`: token de Apify.
- `APIFY_ACTOR_ID`: actor de Instagram en Apify, por ejemplo `usuario/actor`.
- `APIFY_INPUT_JSON`: JSON enviado al actor.

Esto es polling, no streaming real: Apify entrega datos por corrida del actor. Baja `POLL_SECONDS` si necesitas más frescura y tu cuota lo permite.
