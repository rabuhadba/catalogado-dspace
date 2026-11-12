"""
Módulo de ingestión a DSpace 7 para la colección SIGES (Iniciativas / Proyectos).
Maneja carga de CSV, validación, mapeo de metadatos y depósito directo con Handle.
"""
import os
import csv
import datetime
import pandas as pd
import requests

DEFAULT_SIGES_COLLECTION_UUID = "ab25c4c6-e0f6-4505-8623-b23fa0566bf3"

MULTIVALUE_FIELDS = {
    "fia.equipo-tecnico",
    "fia.beneficiario-directo",
    "fia.participante-individual",
    "fia.consultor",
    "fia.ejecutor-tecnico",
    "fia.institucion-visitada",
    "fia.participante-individual-consultoría",
    "fia.participante-individual-consultoria",
    "fia.expositor",
    "fia.tema",
}


class CargadorSiges:
    """Motor de carga e ingestión para iniciativas SIGES a DSpace 7."""

    def __init__(self, dspace_url, email=None, password=None,
                 collection_uuid=DEFAULT_SIGES_COLLECTION_UUID,
                 log=None, progress=None):
        self.dspace_url = (dspace_url or "").rstrip("/")
        self.email = email
        self.password = password
        self.collection_uuid = collection_uuid or DEFAULT_SIGES_COLLECTION_UUID
        self.log = log or (lambda msg: None)
        self.progress = progress or (lambda cur, tot: None)
        self._cancelado = False

        self.session = None
        self.token = None
        self.csrf_token = None

    def cancelar(self):
        """Solicita cancelar el proceso en ejecución."""
        self._cancelado = True

    def reset(self):
        """Reinicia estado de cancelación."""
        self._cancelado = False

    def leer_csv(self, ruta_csv):
        """
        Lee el CSV detectando delimitador (, o ;) y codificación (utf-8, latin-1, cp1252).
        Retorna (lista_items, stats).
        """
        if not os.path.exists(ruta_csv):
            raise FileNotFoundError(f"No existe el archivo: {ruta_csv}")

        df = None
        for enc in ["utf-8", "utf-8-sig", "latin1", "cp1252"]:
            for sep in [";", ",", "\t"]:
                try:
                    candidate = pd.read_csv(ruta_csv, sep=sep, encoding=enc, dtype=str)
                    if len(candidate.columns) >= 2 and any(
                        "fia" in c.lower() or "dc" in c.lower() for c in candidate.columns
                    ):
                        df = candidate
                        break
                except Exception:
                    continue
            if df is not None:
                break

        if df is None:
            raise ValueError("No se pudo detectar el formato ni delimitador del CSV.")

        df.columns = [c.strip() for c in df.columns]

        items = []
        validos = 0
        advertencias = 0

        for idx, row in df.iterrows():
            item_data = {}
            for col in df.columns:
                val = str(row.get(col, "")).strip()
                if val.lower() == "nan":
                    val = ""
                item_data[col] = val

            item_data["_fila"] = idx + 2  # Fila en Excel/CSV (cabecera en fila 1)
            inic = item_data.get("fia.iniciativa", "").strip()
            title = item_data.get("dc.title", "").strip()

            if inic and title:
                validos += 1
                item_data["_es_valido"] = True
            else:
                advertencias += 1
                item_data["_es_valido"] = False

            items.append(item_data)

        stats = {
            "total": len(items),
            "validos": validos,
            "advertencias": advertencias,
            "columnas": list(df.columns),
        }
        return items, stats

    def preparar_metadatos_dspace(self, item_dict):
        """Convierte una fila del CSV al dict estructurado para DSpace 7 PATCH metadata."""
        metadatos = {
            "dc.type": [{"value": "Proyectos"}]
        }

        for col, val in item_dict.items():
            if col.startswith("_") or col.lower() == "id" or col == "dc.type":
                continue
            if val is None:
                continue
            val_str = str(val).strip()
            if not val_str or val_str.lower() == "nan":
                continue

            # Multivaluado
            if col in MULTIVALUE_FIELDS or "||" in val_str or "| |" in val_str:
                val_limpio = val_str.replace("| |", "||")
                subvalores = [v.strip() for v in val_limpio.split("||") if v.strip()]
                if subvalores:
                    metadatos[col] = [{"value": v} for v in subvalores]
            else:
                metadatos[col] = [{"value": val_str}]

        return metadatos

    def iniciar_sesion(self):
        """Autenticación en DSpace 7 REST API."""
        if not self.email or not self.password or not self.dspace_url:
            self.log("❌ Falta URL, usuario o contraseña en la configuración.")
            return False

        self.session = requests.Session()
        login_url = f"{self.dspace_url}/authn/login"

        try:
            # Obtener CSRF inicial
            self.session.post(login_url, timeout=30)
            csrf_cookie = self.session.cookies.get("DSPACE-XSRF-COOKIE")
            headers = {"X-XSRF-TOKEN": csrf_cookie} if csrf_cookie else {}

            resp = self.session.post(
                login_url,
                data={"user": self.email, "password": self.password},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 200:
                self.token = resp.headers.get("Authorization")
                self.csrf_token = (
                    resp.headers.get("DSPACE-XSRF-TOKEN")
                    or self.session.cookies.get("DSPACE-XSRF-COOKIE")
                    or csrf_cookie
                )
                self.log("✅ Autenticación exitosa en DSpace.")
                return True
            else:
                self.log(f"❌ Error de autenticación DSpace: HTTP {resp.status_code}")
                return False
        except Exception as e:
            self.log(f"❌ Excepción conectando a DSpace: {e}")
            return False

    def cargar_un_item(self, item_dict, collection_uuid=None):
        """
        Ingesta un ítem individual a DSpace 7 y lo publica en la colección SIGES.
        Retorna (exito: bool, handle_o_url: str, mensaje: str).
        """
        col_uuid = collection_uuid or self.collection_uuid or DEFAULT_SIGES_COLLECTION_UUID

        if not self.session or not self.token:
            if not self.iniciar_sesion():
                return False, "", "No se pudo iniciar sesión en DSpace."

        api_headers = {
            "Authorization": self.token,
            "X-XSRF-TOKEN": self.csrf_token,
            "Accept": "application/json",
        }

        # 1. Crear WorkspaceItem
        ws_url = f"{self.dspace_url}/submission/workspaceitems?owningCollection={col_uuid}"
        ws_headers = api_headers.copy()
        ws_headers["Content-Type"] = "application/json"

        try:
            resp_ws = self.session.post(ws_url, headers=ws_headers, json={}, timeout=40)
            # Reintento si sesión expiró
            if resp_ws.status_code == 401:
                if not self.iniciar_sesion():
                    return False, "", "Sesión expirada y reautenticación fallida."
                api_headers["Authorization"] = self.token
                api_headers["X-XSRF-TOKEN"] = self.csrf_token
                ws_headers["Authorization"] = self.token
                ws_headers["X-XSRF-TOKEN"] = self.csrf_token
                resp_ws = self.session.post(ws_url, headers=ws_headers, json={}, timeout=40)

            if resp_ws.status_code != 201:
                return False, "", f"Error creando WorkspaceItem: HTTP {resp_ws.status_code}"

            ws_data = resp_ws.json()
            ws_id = ws_data.get("id")
            item_uuid = ws_data.get("_embedded", {}).get("item", {}).get("id")
            if not item_uuid:
                return False, "", "WorkspaceItem creado pero no se encontró UUID del ítem."

            # 2. Aplicar Metadatos via PATCH
            metadatos = self.preparar_metadatos_dspace(item_dict)
            patch_url = f"{self.dspace_url}/core/items/{item_uuid}"
            patch_headers = api_headers.copy()
            patch_headers["Content-Type"] = "application/json"

            patch_ops = []
            for campo, valores in metadatos.items():
                for val_obj in valores:
                    patch_ops.append({
                        "op": "add",
                        "path": f"/metadata/{campo}/-",
                        "value": val_obj
                    })

            if patch_ops:
                resp_patch = self.session.patch(patch_url, headers=patch_headers, json=patch_ops, timeout=40)
                if resp_patch.status_code != 200:
                    err_msg = f"Error aplicando metadatos: HTTP {resp_patch.status_code} - {getattr(resp_patch, 'text', '')[:100]}"
                    self.log(f"  ❌ {err_msg}")
                    return False, "", err_msg

            # 3. Depositar WorkspaceItem para publicación directa
            wf_url = f"{self.dspace_url}/workflow/workflowitems"
            wf_headers = {
                "Authorization": self.token,
                "X-XSRF-TOKEN": self.csrf_token,
                "Content-Type": "text/uri-list",
                "Accept": "application/json",
            }
            body_uri = f"{self.dspace_url}/submission/workspaceitems/{ws_id}"
            resp_wf = self.session.post(wf_url, headers=wf_headers, data=body_uri, timeout=40)

            if resp_wf.status_code not in [200, 201]:
                return False, "", f"Error depositando WorkspaceItem: HTTP {resp_wf.status_code}"

            handle = ""
            try:
                wf_data = resp_wf.json()
                item_obj = wf_data.get("_embedded", {}).get("item", {})
                handle = item_obj.get("handle") or ""
            except Exception:
                pass

            if not handle:
                # Consultar item directamente si no vino en wf_data
                try:
                    resp_item = self.session.get(f"{self.dspace_url}/core/items/{item_uuid}", headers=api_headers, timeout=20)
                    if resp_item.status_code == 200:
                        handle = resp_item.json().get("handle") or ""
                except Exception:
                    pass

            handle_str = f"https://bibliotecadigital.fia.cl/handle/{handle}" if handle else f"Item UUID: {item_uuid}"
            return True, handle_str, "Publicado exitosamente."

        except Exception as e:
            return False, "", f"Excepción durante la ingestión: {e}"
