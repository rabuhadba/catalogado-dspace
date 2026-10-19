"""
Módulo de importación a DSpace 7 vía API REST.
Refactorización de importador_dspace_api.py como clase reutilizable con callbacks.
"""
import os
import shutil
import pandas as pd
import requests


class ImportadorDSpace:
    """Motor de importación directa a DSpace 7 mediante API REST."""

    def __init__(self, dspace_url, email, password, collection_uuid,
                 log=None, progress=None):
        """
        Args:
            dspace_url:       URL base de la API REST de DSpace (ej: https://…/server/api).
            email:            Email de autenticación.
            password:         Contraseña.
            collection_uuid:  UUID de la colección destino.
            log:              Callback log(mensaje: str).
            progress:         Callback progress(actual: int, total: int).
        """
        self.dspace_url = dspace_url.rstrip('/')
        self.email = email
        self.password = password
        self.collection_uuid = collection_uuid
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

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    @staticmethod
    def _buscar_foto(nombre_archivo, proyecto_dir):
        """Busca la foto suelta en la raíz o en subcarpeta Fotos."""
        ruta = os.path.join(proyecto_dir, nombre_archivo)
        if os.path.exists(ruta):
            return ruta
        ruta = os.path.join(proyecto_dir, "Fotos", nombre_archivo)
        if os.path.exists(ruta):
            return ruta
        # Si se busca .bmp pero existe .jpg
        base_no_ext, ext = os.path.splitext(nombre_archivo)
        if ext.lower() == '.bmp':
            jpg_name = base_no_ext + '.jpg'
            p_root = os.path.join(proyecto_dir, jpg_name)
            if os.path.exists(p_root):
                return p_root
            p_fotos = os.path.join(proyecto_dir, "Fotos", jpg_name)
            if os.path.exists(p_fotos):
                return p_fotos
        return None

    def _leer_metadatos_csv(self, csv_path):
        """Lee el CSV y devuelve lista de dicts con metadatos y nombre de archivo."""
        df = pd.read_csv(csv_path, dtype=str)
        items = []

        # Identificar columna del nombre de archivo
        col_archivo = None
        for posible in ['nombre archivo', 'filename', 'Nombre Archivo']:
            if posible in df.columns:
                col_archivo = posible
                break
        if not col_archivo:
            self.log(f"❌ No se encontró columna de nombre de archivo en el CSV.")
            self.log(f"Columnas disponibles: {list(df.columns)}")
            return []

        df.columns = [c.strip() for c in df.columns]
        col_archivo = col_archivo.strip()

        columnas_excluir = {col_archivo}
        columnas_metadatos = [
            c for c in df.columns if '.' in c and c not in columnas_excluir
        ]

        for _, row in df.iterrows():
            nombre_archivo = str(row[col_archivo]).strip()
            if not nombre_archivo or nombre_archivo == 'nan':
                continue

            metadatos = {}
            for col in columnas_metadatos:
                valor = str(row.get(col, '')).strip()
                if valor and valor != 'nan':
                    if '||' in valor or '| |' in valor:
                        val_limpio = valor.replace('| |', '||')
                        metadatos[col] = [
                            {"value": v.strip()} for v in val_limpio.split('||') if v.strip()
                        ]
                    else:
                        metadatos[col] = [{"value": valor}]

            items.append({
                "nombre_archivo": nombre_archivo,
                "metadatos": metadatos,
            })

        return items

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def iniciar_sesion(self):
        """Inicia sesión en DSpace y almacena tokens. Retorna True si OK."""
        self.log(f"Conectando a {self.dspace_url}...")
        self.session = requests.Session()
        login_url = f"{self.dspace_url}/authn/login"

        # Obtener CSRF inicial
        self.session.post(login_url)
        csrf_token = self.session.cookies.get("DSPACE-XSRF-COOKIE")
        headers = {"X-XSRF-TOKEN": csrf_token} if csrf_token else {}

        resp = self.session.post(
            login_url,
            data={"user": self.email, "password": self.password},
            headers=headers,
        )
        if resp.status_code == 200:
            self.token = resp.headers.get("Authorization")
            self.csrf_token = (
                resp.headers.get("DSPACE-XSRF-TOKEN")
                or self.session.cookies.get("DSPACE-XSRF-COOKIE")
                or csrf_token
            )
            self.log("✅ Autenticación exitosa.\n")
            return True
        else:
            self.log(f"❌ Error al iniciar sesión: {resp.status_code}")
            return False

    # ------------------------------------------------------------------
    # Proceso principal
    # ------------------------------------------------------------------

    def importar(self, proyecto_dir, limpiar_al_terminar=False):
        """
        Importa ítems a DSpace desde el CSV catalogado.
        Retorna tupla (items_ok, items_error).
        """
        self.reset()

        csv_path = os.path.join(proyecto_dir, "Catalogo_OpenAI_Completo.csv")
        if not os.path.exists(csv_path):
            self.log("❌ No se encontró Catalogo_OpenAI_Completo.csv. Ejecuta la catalogación primero.")
            return 0, 0

        items = self._leer_metadatos_csv(csv_path)
        total = len(items)
        self.log(f"Se encontraron {total} ítems para importar desde el CSV.")

        if not self.iniciar_sesion():
            return 0, 0

        api_headers = {
            "Authorization": self.token,
            "X-XSRF-TOKEN": self.csrf_token,
            "Accept": "application/json",
        }

        log_file = os.path.join(proyecto_dir, "registro_subida.txt")
        items_ok = 0
        items_error = 0

        for i, item in enumerate(items, 1):
            if self._cancelado:
                self.log("\n⏹ Importación cancelada por el usuario.")
                break

            nombre_archivo = item["nombre_archivo"]
            metadatos = item["metadatos"]

            self.log(f"\n[{i}/{total}] Procesando: {nombre_archivo}")
            self.progress(i, total)

            # 1. Crear WorkspaceItem (borrador)
            ws_url = (
                f"{self.dspace_url}/submission/workspaceitems"
                f"?owningCollection={self.collection_uuid}"
            )
            ws_headers = api_headers.copy()
            ws_headers["Content-Type"] = "application/json"

            resp_ws = self.session.post(ws_url, headers=ws_headers, json={})
            if resp_ws.status_code != 201:
                self.log(f"  → Error al crear borrador (Status: {resp_ws.status_code})")
                items_error += 1
                continue

            ws_data = resp_ws.json()
            ws_id = ws_data.get("id")
            try:
                item_uuid = ws_data["_embedded"]["item"]["id"]
            except KeyError:
                self.log("  → No se pudo obtener el UUID del ítem creado.")
                items_error += 1
                continue

            self.log(f"  → Borrador creado (WS: {ws_id}, UUID: {item_uuid})")

            # Guardar en bitácora
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{item_uuid}\n")

            # 2. Aplicar metadatos campo por campo
            if metadatos:
                patch_headers = api_headers.copy()
                patch_headers["Content-Type"] = "application/json"
                patch_url = f"{self.dspace_url}/core/items/{item_uuid}"

                campos_ok = 0
                campos_err = 0
                for campo, valores in metadatos.items():
                    # Para DSpace 7 REST API: cada valor multivaluado se envía como
                    # una operación 'add' al sub-path '/-' para que DSpace agregue cada entrada.
                    patch_op = [
                        {"op": "add", "path": f"/metadata/{campo}/-", "value": val}
                        for val in valores
                    ]
                    resp_patch = self.session.patch(patch_url, headers=patch_headers, json=patch_op)
                    if resp_patch.status_code == 200:
                        campos_ok += 1
                    else:
                        campos_err += 1

                if campos_err > 0:
                    self.log(f"  → Metadatos: {campos_ok} OK, {campos_err} rechazados por DSpace.")
                else:
                    self.log(f"  → Metadatos aplicados correctamente ({campos_ok} campos).")


            # 3. Subir foto (bitstream)
            ruta_foto = self._buscar_foto(nombre_archivo, proyecto_dir)
            if ruta_foto:
                with open(ruta_foto, 'rb') as f:
                    bitstream_url = f"{self.dspace_url}/submission/workspaceitems/{ws_id}"
                    file_headers = {
                        "Authorization": self.token,
                        "X-XSRF-TOKEN": self.csrf_token,
                        "Accept": "application/json",
                    }
                    files = {"file": (nombre_archivo, f, "image/jpeg")}
                    resp_file = self.session.post(
                        bitstream_url, headers=file_headers, files=files
                    )
                    if resp_file.status_code in [200, 201]:
                        self.log(f"  → Foto subida: {nombre_archivo}")
                    else:
                        self.log(f"  → Error subiendo foto (Status: {resp_file.status_code})")
            else:
                self.log(f"  → ⚠️ No se encontró la foto {nombre_archivo}")

            items_ok += 1

        self.log(f"\n{'=' * 55}")
        self.log(f"  RESULTADO: {items_ok} exitosos, {items_error} con error")
        self.log(f"{'=' * 55}")

        if limpiar_al_terminar and items_ok > 0:
            self._limpiar(proyecto_dir)

        return items_ok, items_error

    # ------------------------------------------------------------------
    # Limpieza
    # ------------------------------------------------------------------

    def _limpiar(self, proyecto_dir):
        """Elimina fotos locales y CSVs temporales tras la subida."""
        self.log("\nLimpiando archivos locales...")

        carpeta_fotos = os.path.join(proyecto_dir, "Fotos")
        if os.path.exists(carpeta_fotos):
            try:
                shutil.rmtree(carpeta_fotos)
                self.log(f"  Carpeta 'Fotos' eliminada.")
            except Exception as e:
                self.log(f"  Error al borrar Fotos: {e}")
        else:
            exts_imagen = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff')
            try:
                for arch in os.listdir(proyecto_dir):
                    if arch.lower().endswith(exts_imagen):
                        os.remove(os.path.join(proyecto_dir, arch))
                self.log("  Imágenes sueltas eliminadas.")
            except Exception as e:
                self.log(f"  Error al borrar imágenes: {e}")

        try:
            for arch in os.listdir(proyecto_dir):
                if arch.lower().endswith('.csv') and arch != "Catalogo_OpenAI_Completo.csv":
                    os.remove(os.path.join(proyecto_dir, arch))
                    self.log(f"  Archivo temporal '{arch}' eliminado.")
        except Exception as e:
            self.log(f"  Error al borrar CSVs temporales: {e}")

        self.log("✅ Limpieza terminada.")
