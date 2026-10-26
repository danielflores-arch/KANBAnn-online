import json
import os
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Dict, Any, List

try:
    from _storage import get_all_priorities, save_priorities, get_all_logs, append_audit_log
except ImportError:
    from storage import get_all_priorities, save_priorities, get_all_logs, append_audit_log

# Lista de emails permitidos de PCP (configurable vía ENV)
# Admite comodines (ej. *@sai.com.ar) o emails específicos
RAW_ALLOWED = os.environ.get(
    "ALLOWED_PCP_EMAILS",
    "*@sai.com.ar,danielflores@gmail.com,pcp@sai.com.ar,admin@sai.com.ar"
)
ALLOWED_PCP_EMAILS = [e.strip().lower() for e in RAW_ALLOWED.split(",") if e.strip()]


def is_email_authorized(email: str) -> bool:
    """Valida si el correo pertenece a la lista de usuarios autorizados de PCP."""
    if not email:
        return False
    email = email.lower().strip()
    for pattern in ALLOWED_PCP_EMAILS:
        if pattern == "*" or pattern == email:
            return True
        if pattern.startswith("*@") and email.endswith(pattern[1:]):
            return True
    return False


def verify_google_token(id_token: str) -> Dict[str, Any]:
    """Valida el token de Google contra los servidores oficiales de Google OAuth2."""
    if not id_token:
        return {}
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
        req = urllib.request.Request(url, headers={"User-Agent": "KanbanVercel/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception:
        return {}


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: Any):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self._send_json(200, {"status": "ok"})

    def do_GET(self):
        """Retorna el estado de prioridades, logs de auditoría y configuración de autenticación."""
        priorities = get_all_priorities()
        logs = get_all_logs()

        self._send_json(200, {
            "priorities": priorities,
            "logs": logs,
            "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "allowed_patterns": ALLOWED_PCP_EMAILS,
        })

    def do_POST(self):
        """Asigna o modifica la prioridad de una orden y registra la auditoría."""
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
