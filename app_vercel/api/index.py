import json
import logging
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Asegurar que el directorio api/ esté en el path de importación
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from _data import fetch_kanban_data
from _priority import (
    get_all_priorities,
    get_all_logs,
    save_priorities,
    append_audit_log,
    is_email_authorized,
    verify_google_token,
    ALLOWED_PCP_EMAILS
)

logger = logging.getLogger("vercel-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class handler(BaseHTTPRequestHandler):
    """
    Punto de entrada único para la API Serverless en Vercel.
    Enruta /api/data y /api/priority de forma unificada.
    """

    def _send_json(self, status_code: int, data: any, headers_extra: dict = None):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if headers_extra:
            for k, v in headers_extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self._send_json(200, {"status": "ok"})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/").lower()

        # Endpoint 1: /api/priority
        if path.endswith("/priority"):
            priorities = get_all_priorities()
            logs = get_all_logs()
            self._send_json(200, {
                "priorities": priorities,
                "logs": logs,
                "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "allowed_patterns": ALLOWED_PCP_EMAILS,
            })
            return

        # Endpoint 2: /api/data (y fallback por defecto para /api)
        try:
            query = parse_qs(parsed.query)
            requested_sector = query.get("sector", [None])[0]
            data = fetch_kanban_data(requested_sector=requested_sector)
            self._send_json(200, data, {
                "Cache-Control": "public, s-maxage=5, stale-while-revalidate=15"
            })
        except Exception as e:
            logger.error(f"Error procesando solicitud /api/data: {e}")
            self._send_json(500, {"error": str(e)})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/").lower()

        # Solo /api/priority admite POST
        if not path.endswith("/priority"):
            self._send_json(404, {"error": "Ruta no encontrada para POST"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            self._send_json(400, {"error": "Cuerpo JSON inválido"})
            return

        of_code = str(body.get("of", "")).strip()
        new_priority = str(body.get("prioridad", "NORMAL")).upper().strip()
        id_token = body.get("id_token")
        user_info = body.get("user", {})

        if not of_code:
            self._send_json(400, {"error": "El código de OF es requerido"})
            return

        if new_priority not in ["ALTA", "NORMAL"]:
            new_priority = "NORMAL"

        user_email = ""
        user_name = ""

        # Verificación con Google Token si fue provisto
        if id_token:
            token_data = verify_google_token(id_token)
            if token_data and "email" in token_data:
                user_email = token_data.get("email", "").lower()
                user_name = token_data.get("name") or token_data.get("email")
            else:
                self._send_json(401, {"error": "Token de Google inválido o expirado"})
                return
        else:
            # Modo manual / desarrollo
            user_email = str(user_info.get("email", "")).lower().strip()
            user_name = str(user_info.get("name") or user_email)

        if not is_email_authorized(user_email):
            self._send_json(403, {
                "error": f"El correo '{user_email}' no tiene permisos de PCP autorizados.",
                "allowed_patterns": ALLOWED_PCP_EMAILS
            })
            return

        priorities = get_all_priorities()
        prev_data = priorities.get(of_code, {})
        old_priority = prev_data.get("prioridad", "NORMAL")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Actualizar mapa de prioridades
        if new_priority == "NORMAL":
            if of_code in priorities:
                del priorities[of_code]
        else:
            priorities[of_code] = {
                "prioridad": new_priority,
                "user_email": user_email,
                "user_name": user_name,
                "updated_at": now_str,
                "denominacion": body.get("denominacion", ""),
                "sector": body.get("sector", "")
            }

        # Crear entrada en el log de auditoría
        log_entry = {
            "id": f"log_{datetime.now().strftime('%Y%m%d%H%M%S')}_{of_code}",
            "of": of_code,
            "denominacion": body.get("denominacion", ""),
            "sector": body.get("sector", ""),
            "old_priority": old_priority,
            "new_priority": new_priority,
            "user_email": user_email,
            "user_name": user_name,
            "timestamp": now_str,
        }

        save_priorities(priorities, log_entry=log_entry)
        append_audit_log(log_entry)

        self._send_json(200, {
            "success": True,
            "of": of_code,
            "prioridad": new_priority,
            "priorities": priorities,
            "log": log_entry
        })
