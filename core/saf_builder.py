"""
Módulo generador de paquetes SAF para DSpace.
Refactorización de creador_saf.py como clase reutilizable con callbacks.
"""
import os
import shutil
import pandas as pd


class SAFBuilder:
    """Generador de paquetes Simple Archive Format (SAF) para importación a DSpace."""

    def __init__(self, log=None, progress=None):
        """
        Args:
            log:      Callback log(mensaje: str).
            progress: Callback progress(actual: int, total: int).
        """
        self.log = log or (lambda msg: None)
        self.progress = progress or (lambda cur, tot: None)
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True

    def reset(self):
        self._cancelado = False

    # ------------------------------------------------------------------
    # Proceso principal
    # ------------------------------------------------------------------

    def generar_saf(self, proyecto_dir, coleccion_handle=""):
        """
        Genera la estructura SAF a partir del CSV del proyecto.
        Retorna True si terminó correctamente.
        """
        self.reset()

        # Buscar CSV (prioriza el catalogado)
        csv_salida = os.path.join(proyecto_dir, "Catalogo_OpenAI_Completo.csv")
        csv_base_files = [
            f for f in os.listdir(proyecto_dir)
            if f.lower().endswith('.csv') and not f.startswith('Catalogo_OpenAI')
        ]

        if os.path.exists(csv_salida):
            ruta_csv = csv_salida
            self.log(f"Usando CSV catalogado: {os.path.basename(csv_salida)}")
        elif csv_base_files:
            ruta_csv = os.path.join(proyecto_dir, csv_base_files[0])
            self.log(f"Usando CSV base: {csv_base_files[0]}")
        else:
            self.log("❌ No se encontró ningún CSV en la carpeta del proyecto.")
            return False

        # Carpeta de fotos
        carpeta_fotos = os.path.join(proyecto_dir, "Fotos")
        if not os.path.exists(carpeta_fotos):
            carpeta_fotos = proyecto_dir

        # Crear directorio SAF
        saf_dir = os.path.join(proyecto_dir, "SAF")
        if os.path.exists(saf_dir):
            self.log(f"⚠️ La carpeta SAF ya existe. Se sobrescribirán archivos que coincidan.")
        os.makedirs(saf_dir, exist_ok=True)

        self.log("Generando estructura SAF...\n")

        # Leer CSV
        try:
            df = pd.read_csv(ruta_csv, dtype=str)
        except Exception as e:
            self.log(f"❌ Error al leer el CSV: {e}")
            return False

        df = df.fillna("")
        total = len(df)

        for index, row in df.iterrows():
            if self._cancelado:
                self.log("\n⏹ Generación SAF cancelada por el usuario.")
                return False

            item_dir = os.path.join(saf_dir, f"item_{index:04d}")
            os.makedirs(item_dir, exist_ok=True)

            # ----------------------------------------------------------
            # Generar archivos XML por schema
            # ----------------------------------------------------------
            schemas = {}
            for col in df.columns:
                if '.' in col:
                    parts = col.split('.')
                    schema = parts[0]
                    element = parts[1]
                    qualifier = parts[2] if len(parts) > 2 else "none"

                    value = str(row[col]).strip()
                    if not value:
                        continue

                    if schema not in schemas:
                        schemas[schema] = []

                    val_limpio = value.replace('| |', '||')
                    values = [v.strip() for v in val_limpio.split('||') if v.strip()]
                    for v in values:
                        schemas[schema].append({
                            'element': element,
                            'qualifier': qualifier,
                            'value': v,
                        })

            for schema, tags in schemas.items():
                filename = "dublin_core.xml" if schema == "dc" else f"metadata_{schema}.xml"
                filepath = os.path.join(item_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write('<?xml version="1.0" encoding="utf-8" standalone="no"?>\n')
                    f.write(f'<dublin_core schema="{schema}">\n')
                    for tag in tags:
                        val = (
                            tag['value']
                            .replace('&', '&amp;')
                            .replace('<', '&lt;')
                            .replace('>', '&gt;')
                            .replace('"', '&quot;')
                            .replace("'", '&apos;')
                        )
                        f.write(
                            f'  <dcvalue element="{tag["element"]}" '
                            f'qualifier="{tag["qualifier"]}">{val}</dcvalue>\n'
                        )
                    f.write('</dublin_core>\n')

            # ----------------------------------------------------------
            # Archivo contents + collections + copiar foto
            # ----------------------------------------------------------
            nombre_archivo = str(row.get('nombre archivo', '')).strip()
            if nombre_archivo:
                contents_path = os.path.join(item_dir, "contents")
                with open(contents_path, "w", encoding="utf-8") as f:
                    f.write(f"{nombre_archivo}\n")

                if coleccion_handle:
                    collections_path = os.path.join(item_dir, "collections")
                    with open(collections_path, "w", encoding="utf-8") as f:
                        f.write(f"{coleccion_handle}\n")

                ruta_foto = os.path.join(carpeta_fotos, nombre_archivo)
                if os.path.exists(ruta_foto):
                    shutil.copy2(ruta_foto, os.path.join(item_dir, nombre_archivo))
                else:
                    self.log(
                        f"⚠️ No se encontró la imagen '{nombre_archivo}' "
                        f"para ítem {index:04d}"
                    )

            self.log(f"[{index + 1}/{total}] SAF creado: {nombre_archivo} → item_{index:04d}")
            self.progress(index + 1, total)

        self.log(f"\n✅ ¡Generación SAF terminada! Paquetes en: {saf_dir}")
        return True
