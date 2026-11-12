# Carga SIGES Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the "Carga SIGES" module to validate and ingest initiative metadata from CSV files directly into the private SIGES collection in DSpace 7 with immediate publication (Handle generation) and single-item test capability.

**Architecture:** A modular architecture separating the backend REST ingest engine (`core/cargador_siges.py`) from the user interface (`CargaSigesFrame` in `app_gui.py`). The engine handles CSV parsing with automatic delimiter detection, metadata normalization (multivalued `||` expansion), DSpace 7 authentication, item creation, metadata patching, and workflow item deposit. The UI provides CSV loading, integrity validation, a detailed project preview card with multivalued pills, a single-item test button, and batch ingest with real-time progress and cancellation.

**Tech Stack:** Python 3.14, CustomTkinter, Pandas, Requests, Python unittest.

**Spec:** [docs/superpowers/specs/2026-11-12-carga-siges-design.md](file:///d:/repos/CATALOGADO%20DSPACE%20FINAL/docs/superpowers/specs/2026-11-12-carga-siges-design.md)

## Global Constraints

- Target DSpace Collection UUID: `ab25c4c6-e0f6-4505-8623-b23fa0566bf3` (SIGES collection, handle `20.500.11944/226725`).
- Constant type metadata: `dc.type` must be set to `"Proyectos"`.
- Authentication: Reuses `DSPACE_URL`, `DSPACE_EMAIL`, `DSPACE_PASSWORD` from `.env`.
- Multivalued fields: Values containing `||` or `| |` must be trimmed and split into distinct array entries in DSpace metadata.
- Item state: Items must be deposited to `/api/workflow/workflowitems` to be archived with a minted Handle.
- Non-regression: No modifications that disrupt existing photo cataloging (`core/catalogador.py`), photo export (`core/importador.py`), or relationships (`core/relacionador.py`).

---

### Task 1: Engine Core — CSV Parsing, Metadata Normalization & Single Item Ingestion

**Files:**
- Create: `core/cargador_siges.py`
- Create: `tests/test_cargador_siges.py`

**Interfaces:**
- Consumes: `DSPACE_URL`, `DSPACE_EMAIL`, `DSPACE_PASSWORD`, `DSPACE_SIGES_COLLECTION_UUID` from configuration or parameters.
- Produces: `CargadorSiges` class with:
  - `leer_csv(ruta_csv)` -> `tuple[list[dict], dict]` (items list and stats dict)
  - `iniciar_sesion()` -> `bool`
  - `cargar_un_item(item_data, collection_uuid=None)` -> `tuple[bool, str, str]` (`(ok, handle, error_msg)`)

- [ ] **Step 1: Write unit tests for CSV parsing and metadata normalization**

```python
# tests/test_cargador_siges.py
import unittest
import os
import tempfile
from core.cargador_siges import CargadorSiges

class TestCargadorSigesParsing(unittest.TestCase):
    def setUp(self):
        self.cargador = CargadorSiges("https://fake-dspace.org/server/api", "test@user.cl", "pass123")

    def test_leer_csv_semicolon_and_multivalue(self):
        csv_content = (
            "Id;fia.iniciativa;dc.title;dc.date.issued;fia.equipo-tecnico;fia.tema\n"
            "1;COC-2026-0001;Proyecto Apicola;2026;Persona Uno||Persona Dos;Sanidad||Apicultura\n"
            "2;COC-2026-0002;Proyecto Riego;2026;Persona Tres;Riego\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            items, stats = self.cargador.leer_csv(temp_path)
            self.assertEqual(len(items), 2)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["validos"], 2)
            self.assertEqual(items[0]["fia.iniciativa"], "COC-2026-0001")
            self.assertEqual(items[0]["dc.title"], "Proyecto Apicola")
            
            # Check normalized metadata structure for DSpace
            metadata = self.cargador.preparar_metadatos_dspace(items[0])
            self.assertEqual(metadata["dc.type"], [{"value": "Proyectos"}])
            self.assertEqual(len(metadata["fia.equipo-tecnico"]), 2)
            self.assertEqual(metadata["fia.equipo-tecnico"][0]["value"], "Persona Uno")
            self.assertEqual(metadata["fia.equipo-tecnico"][1]["value"], "Persona Dos")
            self.assertEqual(len(metadata["fia.tema"]), 2)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_cargador_siges.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.cargador_siges'`

- [ ] **Step 3: Implement `core/cargador_siges.py` with parsing, normalization and single-item ingestion**

```python
# core/cargador_siges.py
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
        self._cancelado = True

    def reset(self):
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
                    if len(candidate.columns) >= 3 and any("fia" in c or "dc" in c for c in candidate.columns):
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

            item_data["_fila"] = idx + 2  # Fila en Excel/CSV
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
            if col.startswith("_") or col.lower() == "id":
                continue
            if not val:
                continue

            # Multivaluado
            if col in MULTIVALUE_FIELDS or "||" in val or "| |" in val:
                val_limpio = val.replace("| |", "||")
                subvalores = [v.strip() for v in val_limpio.split("||") if v.strip()]
                if subvalores:
                    metadatos[col] = [{"value": v} for v in subvalores]
            else:
                metadatos[col] = [{"value": val}]

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
            self.session.post(login_url)
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
        col_uuid = collection_uuid or self.collection_uuid

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
                self.iniciar_sesion()
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

            resp_patch = self.session.patch(patch_url, headers=patch_headers, json=patch_ops, timeout=40)
            if resp_patch.status_code != 200:
                self.log(f"  ⚠️ Advertencia: Algunos metadatos no fueron aceptados: HTTP {resp_patch.status_code}")

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

            handle = ""
            if resp_wf.status_code in [200, 201]:
                wf_data = resp_wf.json()
                # Verificar handle en item indexable
                item_obj = wf_data.get("_embedded", {}).get("item", {})
                handle = item_obj.get("handle") or ""
                if not handle:
                    # Consultar item directamente
                    resp_item = self.session.get(f"{self.dspace_url}/core/items/{item_uuid}", headers=api_headers, timeout=20)
                    if resp_item.status_code == 200:
                        handle = resp_item.json().get("handle") or ""

            handle_str = f"https://bibliotecadigital.fia.cl/handle/{handle}" if handle else f"Item UUID: {item_uuid}"
            return True, handle_str, "Publicado exitosamente."

        except Exception as e:
            return False, "", f"Excepción durante la ingestión: {e}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_cargador_siges.py`
Expected: Ran 1 test in X.XXs - OK

- [ ] **Step 5: Commit**

```bash
git add core/cargador_siges.py tests/test_cargador_siges.py
git commit -m "feat(siges): add CargadorSiges parsing, metadata normalization and single item ingest"
```

---

### Task 2: Batch Upload Engine & Audit Log

**Files:**
- Modify: `core/cargador_siges.py`
- Modify: `tests/test_cargador_siges.py`

**Interfaces:**
- Consumes: `CargadorSiges.cargar_un_item()`
- Produces: `CargadorSiges.cargar_lote(items, collection_uuid=None, output_dir=None)` -> `tuple[int, int, str]` (`(exitosos, errores, ruta_bitacora)`)

- [ ] **Step 1: Write unit test for batch ingest flow and log file generation**

```python
# Add to tests/test_cargador_siges.py
    def test_cargar_lote_mock(self):
        items = [
            {"_fila": 2, "fia.iniciativa": "COC-2026-0001", "dc.title": "Proyecto 1"},
            {"_fila": 3, "fia.iniciativa": "COC-2026-0002", "dc.title": "Proyecto 2"}
        ]
        # Mock cargar_un_item
        call_count = [0]
        def fake_cargar_un_item(item, col_uuid=None):
            call_count[0] += 1
            return True, f"https://bibliotecadigital.fia.cl/handle/20.500.11944/{call_count[0]}", "OK"

        self.cargador.cargar_un_item = fake_cargar_un_item
        with tempfile.TemporaryDirectory() as tmpdir:
            ok, err, log_path = self.cargador.cargar_lote(items, output_dir=tmpdir)
            self.assertEqual(ok, 2)
            self.assertEqual(err, 0)
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("COC-2026-0001", content)
                self.assertIn("COC-2026-0002", content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_cargador_siges.py`
Expected: FAIL with `AttributeError: 'CargadorSiges' object has no attribute 'cargar_lote'`

- [ ] **Step 3: Implement `cargar_lote` in `core/cargador_siges.py`**

```python
    def cargar_lote(self, items, collection_uuid=None, output_dir=None):
        """
        Carga secuencialmente una lista de ítems a la colección SIGES.
        Registra cada operación en un archivo de bitácora CSV.
        Retorna (exitosos, errores, ruta_bitacora).
        """
        self.reset()
        total = len(items)
        exitosos = 0
        errores = 0

        now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = output_dir or os.getcwd()
        log_path = os.path.join(target_dir, f"registro_carga_siges_{now_str}.csv")

        # Iniciar sesión al inicio
        if not self.iniciar_sesion():
            self.log("❌ No se pudo conectar con DSpace 7. Abortando carga por lotes.")
            return 0, total, ""

        with open(log_path, "w", encoding="utf-8", newline="") as f_log:
            writer = csv.writer(f_log, delimiter=";")
            writer.writerow(["Timestamp", "Fila", "Iniciativa", "Titulo", "Handle_o_UUID", "Estado", "Detalle"])

            for idx, item in enumerate(items, 1):
                if self._cancelado:
                    self.log("\n⏹ Carga masiva detenida por el usuario.")
                    break

                fila = item.get("_fila", idx)
                inic = item.get("fia.iniciativa", f"Item-{idx}")
                title = item.get("dc.title", "(Sin título)")

                self.log(f"[{idx}/{total}] Procesando iniciativa: {inic} - {title[:50]}...")
                self.progress(idx, total)

                ok, handle_str, msg = self.cargar_un_item(item, collection_uuid=collection_uuid)

                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if ok:
                    exitosos += 1
                    self.log(f"  ✅ {inic} publicada -> {handle_str}")
                    writer.writerow([timestamp, fila, inic, title, handle_str, "EXITOSO", msg])
                else:
                    errores += 1
                    self.log(f"  ❌ Error en {inic}: {msg}")
                    writer.writerow([timestamp, fila, inic, title, handle_str, "ERROR", msg])

                f_log.flush()

        self.log(f"\n{'=' * 55}")
        self.log(f"  RESUMEN SIGES: {exitosos} exitosos, {errores} errores de {total} totales.")
        self.log(f"  Bitácora guardada en: {log_path}")
        self.log(f"{'=' * 55}")

        return exitosos, errores, log_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_cargador_siges.py`
Expected: Ran 2 tests in X.XXs - OK

- [ ] **Step 5: Commit**

```bash
git add core/cargador_siges.py tests/test_cargador_siges.py
git commit -m "feat(siges): add batch upload and audit logging to CargadorSiges"
```

---

### Task 3: User Interface — `CargaSigesFrame` and Sidebar Navigation

**Files:**
- Modify: `app_gui.py`
- Modify: `.env`

**Interfaces:**
- Consumes: `core.cargador_siges.CargadorSiges`, `DSPACE_SIGES_COLLECTION_UUID`
- Produces: `CargaSigesFrame(ctk.CTkScrollableFrame)` integrated into `CatalogadorApp.frames["siges"]` and navigation button.

- [ ] **Step 1: Add default `DSPACE_SIGES_COLLECTION_UUID` to `.env`**

Ensure `.env` contains:
```ini
DSPACE_SIGES_COLLECTION_UUID='ab25c4c6-e0f6-4505-8623-b23fa0566bf3'
```

- [ ] **Step 2: Implement `CargaSigesFrame` in `app_gui.py`**

Define `CargaSigesFrame` with:
1. Header and CSV selector card with live validation counts (`Total: N`, `Válidas: V`, `Advertencias: A`).
2. Interactive preview card with `◀ [X de N] ▶`, jump selector by initiative, Dublin Core block, FIA project metadata block, objectives, and multivalued pill containers.
3. Bottom action card with:
   - `🧪 Cargar solo este proyecto (Prueba)` button (executes in worker thread, opens info popup with handle).
   - `🚀 Iniciar Carga Masiva` button (confirms, runs worker thread with progress bar update).
   - `⏹ Detener` button (cancels thread).

```python
# In app_gui.py:
from core.cargador_siges import CargadorSiges, DEFAULT_SIGES_COLLECTION_UUID

class CargaSigesFrame(ctk.CTkScrollableFrame):
    """Módulo para carga, validación e ingestión masiva de iniciativas SIGES a DSpace 7."""
    def __init__(self, parent, log_fn, get_config, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.get_config = get_config
        self.cargador = None
        self._running = False
        self._items = []
        self._idx_preview = 0
        self._csv_path = None
        
        self._crear_ui()
```

- [ ] **Step 3: Register `siges` navigation in `CatalogadorApp`**

In `CatalogadorApp.__init__`:
- Add `btn_siges = self._crear_nav_button("📋  Carga SIGES", "siges")`
- Instantiate `self.frames["siges"] = CargaSigesFrame(self.content_area, log_fn=self.log, get_config=self._get_config)`
- In `_cambiar_seccion("siges")`: call `self.frames["siges"].actualizar_estado()`

- [ ] **Step 4: Verify Python syntax compilation**

Run: `python -m py_compile app_gui.py core/cargador_siges.py`
Expected: Exit code 0 (no syntax errors).

- [ ] **Step 5: Commit**

```bash
git add app_gui.py .env
git commit -m "feat(siges): add CargaSigesFrame UI and navigation button"
```

---

### Task 4: Integration Verification, Specification Sync & Build

**Files:**
- Modify: `Catalogador_DSpace.spec`
- Test: `tests/test_cargador_siges.py`

- [ ] **Step 1: Write integration test loading real `carga_siges.csv` file**

```python
# Add to tests/test_cargador_siges.py
    def test_leer_carga_siges_real_si_existe(self):
        real_csv = "carga_siges.csv"
        if os.path.exists(real_csv):
            items, stats = self.cargador.leer_csv(real_csv)
            self.assertGreater(stats["total"], 400)
            self.assertGreater(stats["validos"], 400)
            self.assertEqual(items[0]["fia.iniciativa"], "COC-2026-0001")
```

- [ ] **Step 2: Run all unit and integration tests**

Run: `python -m unittest tests/test_cargador_siges.py`
Expected: All tests pass cleanly.

- [ ] **Step 3: Verify spec file includes `cargador_siges.py` in distribution**

Ensure `Catalogador_DSpace.spec` packages `core` directory (already includes `('core', 'core')`), and copy updated code to `dist/Catalogador_DSpace/_internal/core/cargador_siges.py`.

- [ ] **Step 4: Run manual dry run command to verify DSpace connectivity and collection metadata**

Run: `python -c "from core.cargador_siges import CargadorSiges; from dotenv import load_dotenv; import os; load_dotenv(); c = CargadorSiges(os.getenv('DSPACE_URL'), os.getenv('DSPACE_EMAIL'), os.getenv('DSPACE_PASSWORD')); print('Auth OK:', c.iniciar_sesion())"`
Expected: `Auth OK: True`

- [ ] **Step 5: Commit**

```bash
git add Catalogador_DSpace.spec tests/test_cargador_siges.py
git commit -m "chore(siges): verify integration and sync distribution spec"
```

