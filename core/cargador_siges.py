"""
Módulo de ingestión a DSpace 7 para la colección SIGES (Iniciativas / Proyectos).
Maneja carga de CSV, validación, mapeo de metadatos y depósito directo con Handle.
"""
import os
import csv
import time
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

# Normalización de nombres de columnas que en DSpace están registrados sin tilde o con variante
FIELD_ALIASES = {
    "fia.participante-individual-consultoría": "fia.participante-individual-consultoria",
    "fia.participante-individual-consultor\u00eda": "fia.participante-individual-consultoria",
}

TIMEOUT_STANDARD = 90
TIMEOUT_WORKFLOW = 120


def leer_iniciativas_exitosas_de_bitacora(ruta_bitacora):
    """
    Lee una bitácora CSV previa de SIGES y extrae un diccionario
    {iniciativa: handle_o_url} de todos los ítems con estado EXITOSO.
    """
    if not os.path.exists(ruta_bitacora):
        return {}

    exitosos = {}
    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
        try:
            with open(ruta_bitacora, "r", encoding=enc) as f:
                first_line = f.readline()
                delimitador = ";" if ";" in first_line else ","
                f.seek(0)
                reader = csv.reader(f, delimiter=delimitador)
                header = next(reader, None)
                if not header:
                    continue

                header_lower = [h.strip().lower() for h in header]
                idx_inic = -1
                idx_estado = -1
                idx_handle = -1

                for i, h in enumerate(header_lower):
                    if "iniciativa" in h:
                        idx_inic = i
                    elif "estado" in h:
                        idx_estado = i
                    elif "handle" in h or "uuid" in h:
                        idx_handle = i

                if idx_inic == -1 or idx_estado == -1:
                    continue

                for row in reader:
                    if len(row) > max(idx_inic, idx_estado):
                        estado = row[idx_estado].strip().upper()
                        inic = row[idx_inic].strip()
                        handle = row[idx_handle].strip() if idx_handle != -1 and len(row) > idx_handle else ""
                        if estado == "EXITOSO" and inic:
                            exitosos[inic] = handle or "Publicado previamente"
                return exitosos
        except Exception:
            continue

    return exitosos


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
            col_norm = col.lstrip("\ufeff").strip()
            if col_norm.startswith("_") or col_norm.lower() == "id" or col_norm == "dc.type":
                continue
            if val is None:
                continue
            val_str = str(val).strip()
            if not val_str or val_str.lower() == "nan":
                continue

            target_col = FIELD_ALIASES.get(col_norm, col_norm)

            # Multivaluado
            if target_col in MULTIVALUE_FIELDS or col_norm in MULTIVALUE_FIELDS or "||" in val_str or "| |" in val_str:
                val_limpio = val_str.replace("| |", "||")
                subvalores = [v.strip() for v in val_limpio.split("||") if v.strip()]
                if subvalores:
                    metadatos[target_col] = [{"value": v} for v in subvalores]
            else:
                metadatos[target_col] = [{"value": val_str}]

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
            t0 = time.time()
            resp_ws = self.session.post(ws_url, headers=ws_headers, json={}, timeout=TIMEOUT_STANDARD)
            # Reintento si sesión expiró
            if resp_ws.status_code == 401:
                if not self.iniciar_sesion():
                    return False, "", "Sesión expirada y reautenticación fallida."
                api_headers["Authorization"] = self.token
                api_headers["X-XSRF-TOKEN"] = self.csrf_token
                ws_headers["Authorization"] = self.token
                ws_headers["X-XSRF-TOKEN"] = self.csrf_token
                resp_ws = self.session.post(ws_url, headers=ws_headers, json={}, timeout=TIMEOUT_STANDARD)

            if resp_ws.status_code != 201:
                return False, "", f"Error creando WorkspaceItem: HTTP {resp_ws.status_code}"

            ws_data = resp_ws.json()
            ws_id = ws_data.get("id")
            item_uuid = ws_data.get("_embedded", {}).get("item", {}).get("id")
            if not item_uuid:
                return False, "", "WorkspaceItem creado pero no se encontró UUID del ítem."

            t_ws = time.time() - t0
            self.log(f"   [1/4] Borrador creado ({t_ws:.1f}s)")

            # 2. Aplicar Metadatos via PATCH
            t0 = time.time()
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
                resp_patch = self.session.patch(patch_url, headers=patch_headers, json=patch_ops, timeout=TIMEOUT_STANDARD)
                if resp_patch.status_code != 200:
                    err_msg = f"Error aplicando metadatos: HTTP {resp_patch.status_code} - {getattr(resp_patch, 'text', '')[:100]}"
                    self.log(f"  ❌ {err_msg}")
                    return False, "", err_msg

            t_patch = time.time() - t0
            self.log(f"   [2/4] Metadatos aplicados ({t_patch:.1f}s)")

            # 2.5 Conceder licencia de depósito en el WorkspaceItem (requerido por DSpace 7)
            t0 = time.time()
            ws_patch_url = f"{self.dspace_url}/submission/workspaceitems/{ws_id}"
            patch_license = [{"op": "add", "path": "/sections/license/granted", "value": True}]
            try:
                self.session.patch(ws_patch_url, headers=patch_headers, json=patch_license, timeout=TIMEOUT_STANDARD)
            except Exception as e:
                self.log(f"  ⚠️ Advertencia concediendo licencia en WorkspaceItem: {e}")

            t_lic = time.time() - t0
            self.log(f"   [3/4] Licencia validada ({t_lic:.1f}s)")

            # 3. Depositar WorkspaceItem para publicación directa
            t0 = time.time()
            wf_url = f"{self.dspace_url}/workflow/workflowitems"
            wf_headers = {
                "Authorization": self.token,
                "X-XSRF-TOKEN": self.csrf_token,
                "Content-Type": "text/uri-list",
                "Accept": "application/json",
            }
            body_uri = f"{self.dspace_url}/submission/workspaceitems/{ws_id}"

            resp_wf = None
            try:
                resp_wf = self.session.post(wf_url, headers=wf_headers, data=body_uri, timeout=TIMEOUT_WORKFLOW)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
                self.log(f"   ⚠️ Demora de red en publicación ({net_err}). Verificando si DSpace completó en servidor...")
                time.sleep(3)
                try:
                    resp_item_check = self.session.get(f"{self.dspace_url}/core/items/{item_uuid}", headers=api_headers, timeout=30)
                    if resp_item_check.status_code == 200:
                        data_check = resp_item_check.json()
                        handle_check = data_check.get("handle")
                        if handle_check or data_check.get("inArchive"):
                            h_url = f"https://bibliotecadigital.fia.cl/handle/{handle_check}" if handle_check else f"Item UUID: {item_uuid}"
                            t_rec = time.time() - t0
                            self.log(f"   [4/4] Publicado y recuperado ({t_rec:.1f}s)")
                            return True, h_url, "Publicado exitosamente (confirmado tras recuperación)."
                except Exception:
                    pass
                raise net_err

            if resp_wf.status_code not in [200, 201]:
                return False, "", f"Error depositando WorkspaceItem: HTTP {resp_wf.status_code}"

            handle = ""
            try:
                if resp_wf.text and resp_wf.text.strip():
                    wf_data = resp_wf.json()
                    item_obj = wf_data.get("_embedded", {}).get("item", {})
                    handle = item_obj.get("handle") or ""
            except Exception:
                pass

            if not handle:
                # Consultar item directamente si no vino en wf_data
                try:
                    resp_item = self.session.get(f"{self.dspace_url}/core/items/{item_uuid}", headers=api_headers, timeout=30)
                    if resp_item.status_code == 200:
                        handle = resp_item.json().get("handle") or ""
                except Exception:
                    pass

            t_wf = time.time() - t0
            self.log(f"   [4/4] Publicado en Solr ({t_wf:.1f}s)")

            handle_str = f"https://bibliotecadigital.fia.cl/handle/{handle}" if handle else f"Item UUID: {item_uuid}"
            return True, handle_str, "Publicado exitosamente."

        except Exception as e:
            return False, "", f"Excepción durante la ingestión: {e}"

    def cargar_lote(self, items, collection_uuid=None, output_dir=None, omitir_iniciativas=None):
        """
        Carga secuencialmente una lista de ítems a la colección SIGES.
        Registra cada operación en un archivo de bitácora CSV.
        Retorna (exitosos, errores, ruta_bitacora).
        """
        self.reset()
        total = len(items)
        exitosos = 0
        errores = 0
        omitidos = 0
        omitidos_set = set(omitir_iniciativas or [])

        target_dir = output_dir or os.getcwd()
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(target_dir, f"registro_carga_siges_{now_str}.csv")

        with open(log_path, "w", encoding="utf-8-sig", newline="") as f_log:
            writer = csv.writer(f_log, delimiter=";")
            writer.writerow(["Timestamp", "Fila", "Iniciativa", "Titulo", "Handle_o_UUID", "Estado", "Detalle"])

            for idx, item in enumerate(items, 1):
                if self._cancelado:
                    self.log("\n⏹ Carga masiva detenida por el usuario.")
                    break

                fila = item.get("_fila", idx)
                inic = str(item.get("fia.iniciativa") or f"Item-{idx}").strip()
                title = str(item.get("dc.title") or "(Sin título)").strip()

                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Omitir si ya fue subido previamente en esta sesión
                if inic in omitidos_set:
                    omitidos += 1
                    self.log(f"[{idx}/{total}] ⏭️ Omitiendo {inic} (ya subido previamente en esta sesión)")
                    self.progress(idx, total)
                    writer.writerow([timestamp, fila, inic, title, "", "OMITIDO", "Subido previamente en sesión"])
                    f_log.flush()
                    continue

                self.log(f"[{idx}/{total}] Procesando iniciativa: {inic} - {title[:50]}...")
                self.progress(idx, total)

                try:
                    ok, handle_str, msg = self.cargar_un_item(item, collection_uuid=collection_uuid)
                except Exception as e:
                    ok, handle_str, msg = False, "", f"Excepción durante la ingestión: {e}"

                if ok:
                    exitosos += 1
                    self.log(f"  ✅ {inic} publicada -> {handle_str}")
                    writer.writerow([timestamp, fila, inic, title, handle_str, "EXITOSO", msg])
                else:
                    errores += 1
                    self.log(f"  ❌ Error en {inic}: {msg}")
                    writer.writerow([timestamp, fila, inic, title, handle_str or "", "ERROR", msg])

                f_log.flush()

                # Pausa de respiro para que Tomcat y Solr en el servidor procesen sin saturarse
                if idx < total and not self._cancelado:
                    time.sleep(1.0)

        self.log(f"\n{'=' * 55}")
        self.log(f"  RESUMEN SIGES: {exitosos} exitosos, {errores} errores, {omitidos} omitidos de {total} totales.")
        self.log(f"  Bitácora guardada en: {log_path}")
        self.log(f"{'=' * 55}")

        return exitosos, errores, log_path

