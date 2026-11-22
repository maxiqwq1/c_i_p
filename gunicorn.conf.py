# Configuración del servidor web en producción (Railway define la variable PORT).
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
timeout = 120          # generar la lámina con matplotlib puede tardar unos segundos
