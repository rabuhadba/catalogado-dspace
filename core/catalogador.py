"""
Módulo de catalogación con OpenAI.
Refactorización de catalogador_openai.py como clase reutilizable con callbacks.
"""
import os
import pandas as pd
import base64
import json
import shutil
from openai import OpenAI
from PIL import Image


PROMPT_SISTEMA_DEFAULT = """Eres un documentalista experto de la Fundación para la Innovación Agraria (FIA), catalogando un archivo fotográfico patrimonial y de desarrollo agropecuario en Chile.
Genera los metadatos en formato JSON.

REGLAS ESTRICTAS:
1. Lenguaje: Español formal, técnico y bibliográfico. CERO INGLÉS.
2. Cero muletillas: No uses "La imagen muestra", "Se observa", "Fotografía de". Inicia directo con la acción o sujeto.
3. Precisión: Describe con rigor técnico las labores productivas (manejo agrícola/enológico/forestal, faenas, etc.), maquinaria, especies, instalaciones, herramientas y entorno.
4. Cero ambigüedades o especulaciones: No uses palabras de duda o suposición como "posiblemente", "quizás", "probablemente", "al parecer", etc. Escribe afirmaciones objetivas y categóricas sobre lo que es visible.
5. Puntuación en títulos: NUNCA coloques punto final (.) al terminar "dc.title" ni "dc.title.alternative". Las descripciones sí deben terminar con punto final.
6. Armonización entre Visión y Contexto del Proyecto:
   - Categorías distintas: Si los elementos visibles difieren claramente de la temática del proyecto (ej. otra clase o familia animal, maquinaria, personas, infraestructura general), la visión manda con prioridad absoluta: cataloga exclusivamente lo visible sin forzar los temas del proyecto.
   - Misma categoría / Especie precisa: Si la categoría general visible coincide con la temática del proyecto (ej. se observan animales, cultivos, variedades o labores afines al proyecto), DEBES adoptar la especie y terminología oficial definida por el contexto del proyecto. No especules con especies o variedades semejantes ni alternes con nombres científicos en latín (ej. si el proyecto trata sobre guanacos, los camélidos visibles deben catalogarse consistentemente como guanacos, no como llamas o alpacas).
   - Nomenclatura consistente: Utiliza de forma uniforme el nombre común en español establecido por el contexto del proyecto.

Debes devolver ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
    "dc.title": "Título descriptivo directo y corto",
    "dc.title.alternative": "Título alternativo o variante que detalle la acción",
    "dc.description": "Descripción objetiva y técnica de la escena, herramientas y labor.",
    "dc.description.abstract": "Resumen conciso del valor del proceso o contexto mostrado en la imagen."
}
"""

PROMPT_FILE = "prompt_sistema.txt"


def _get_app_dir():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cargar_prompt_sistema(base_dir=None):
    """Carga el prompt personalizado desde prompt_sistema.txt si existe, o retorna el default."""
    if not base_dir:
        base_dir = _get_app_dir()
    path = os.path.join(base_dir, PROMPT_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return PROMPT_SISTEMA_DEFAULT.strip()


def guardar_prompt_sistema(prompt_texto, base_dir=None):
    """Guarda el prompt personalizado en prompt_sistema.txt."""
    if not base_dir:
        base_dir = _get_app_dir()
    path = os.path.join(base_dir, PROMPT_FILE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(prompt_texto.strip())


class Catalogador:
    """Motor de catalogación con OpenAI. Separa la lógica del UI."""

    def __init__(self, api_key, modelo="gpt-4o-mini", reasoning_effort=None, image_detail="low", temperatura=0.2, prompt_sistema=None, log=None, progress=None):
        """
        Args:
            api_key:          Clave de API de OpenAI.
            modelo:           Modelo a usar (default gpt-4o-mini).
            reasoning_effort: Nivel de esfuerzo de razonamiento (none, low, medium, high, xhigh) si aplica.
            image_detail:     Nivel de detalle de imagen para OpenAI (low, high, auto).
            temperatura:      Temperatura para modelos tradicionales (default 0.2).
            prompt_sistema:   Instrucciones del sistema para OpenAI.
            log:              Callback log(mensaje: str).
            progress:         Callback progress(actual: int, total: int).
        """
        self.client = OpenAI(api_key=api_key)
        self.modelo = modelo or "gpt-4o-mini"
        self.reasoning_effort = reasoning_effort
        self.image_detail = image_detail or "low"
        self.temperatura = temperatura if temperatura is not None else 0.2
        self.prompt_sistema = prompt_sistema or PROMPT_SISTEMA_DEFAULT.strip()
        self.log = log or (lambda msg: None)
        self.progress = progress or (lambda cur, tot: None)
        self._cancelado = False
        self.total_tokens = 0

    def cancelar(self):
        """Solicita cancelar el proceso actual."""
        self._cancelado = True

    def reset(self):
        """Reinicia estado de cancelación y contadores."""
        self._cancelado = False
        self.total_tokens = 0

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def codificar_imagen(ruta):
        """Codifica una imagen a base64 (si es BMP, la normaliza en memoria a JPEG)."""
        if ruta.lower().endswith('.bmp'):
            from io import BytesIO
            try:
                with Image.open(ruta) as img:
                    buf = BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=95)
                    return base64.b64encode(buf.getvalue()).decode("utf-8")
            except Exception:
                pass
        with open(ruta, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def obtener_stats(proyecto_dir):
        """Retorna estadísticas del proyecto: total, catalogados, pendientes, csv."""
        csv_salida = os.path.join(proyecto_dir, "Catalogo_OpenAI_Completo.csv")
        csv_base_files = [
            f for f in os.listdir(proyecto_dir)
            if f.lower().endswith('.csv') and not f.startswith('Catalogo_OpenAI')
        ]

        if os.path.exists(csv_salida):
            ruta_csv = csv_salida
        elif csv_base_files:
            ruta_csv = os.path.join(proyecto_dir, csv_base_files[0])
        else:
            return {"total": 0, "catalogados": 0, "pendientes": 0, "csv": None}

        df = None
        for enc in ['utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(ruta_csv, dtype=str, encoding=enc, sep=None, engine='python')
                break
            except Exception:
                continue
                
        if df is None:
            # Fallback en caso extremo
            try:
                df = pd.read_csv(ruta_csv, dtype=str, sep=';', encoding='latin1')
            except Exception:
                return {"total": 0, "catalogados": 0, "pendientes": 0, "csv": os.path.basename(ruta_csv) + " (Error de lectura)"}

        try:
            total = len(df)
            catalogados = 0
            
            # Buscar la columna dc.title incluso si tiene espacios extras
            col_title = next((c for c in df.columns if c.strip() == 'dc.title'), None)
            
            if col_title:
                catalogados = int((df[col_title].fillna('').str.strip() != '').sum())
                
            return {
                "total": total,
                "catalogados": catalogados,
                "pendientes": total - catalogados,
                "csv": os.path.basename(ruta_csv),
            }
        except Exception as e:
            return {"total": 0, "catalogados": 0, "pendientes": 0, "csv": os.path.basename(ruta_csv) + " (Error de formato)"}

    @staticmethod
    def obtener_nota_general(proyecto_dir):
        """Busca el primer valor no vacío de fia.notageneral en los CSVs del proyecto."""
        if not proyecto_dir or not os.path.exists(proyecto_dir):
            return ""
        csv_files = [
            f for f in os.listdir(proyecto_dir)
            if f.lower().endswith('.csv')
        ]
        # Priorizar CSV original base si existe
        csv_files.sort(key=lambda f: 1 if f.startswith('Catalogo_OpenAI') else 0)
        for fname in csv_files:
            csv_path = os.path.join(proyecto_dir, fname)
            for enc in ['utf-8', 'latin1', 'cp1252']:
                try:
                    df = pd.read_csv(csv_path, dtype=str, encoding=enc, sep=None, engine='python')
                    col = next((c for c in df.columns if c.strip().lower() == 'fia.notageneral'), None)
                    if col:
                        vals = df[col].dropna().tolist()
                        for v in vals:
                            v_str = str(v).strip()
                            if v_str and v_str.lower() != 'nan':
                                return v_str
                    break
                except Exception:
                    continue
        return ""

    @staticmethod
    def contar_fotos(proyecto_dir):
        """Cuenta las imágenes disponibles en la carpeta del proyecto."""
        carpeta_fotos = os.path.join(proyecto_dir, "Fotos")
        if not os.path.exists(carpeta_fotos):
            carpeta_fotos = proyecto_dir

        exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff')
        return sum(
            1 for f in os.listdir(carpeta_fotos)
            if f.lower().endswith(exts)
        )

    # ------------------------------------------------------------------
    # Copia de proyecto desde red
    # ------------------------------------------------------------------

    def copiar_proyecto_desde_red(self, carpeta_red, proyecto_dir):
        """Copia la carpeta de red a local si no existe ya."""
        if os.path.exists(proyecto_dir):
            self.log(f"✅ La carpeta local '{proyecto_dir}' ya existe. Se usarán los archivos locales.")
            return True
        self.log(f"Copiando proyecto desde la red a '{proyecto_dir}'...")
        try:
            shutil.copytree(carpeta_red, proyecto_dir)
            self.log("¡Copia completada con éxito!")
            return True
        except Exception as e:
            self.log(f"❌ Error al copiar la carpeta de red: {e}")
            return False

    # ------------------------------------------------------------------
    # Procesamiento de una imagen con OpenAI
    # ------------------------------------------------------------------

    def _procesar_una_imagen(self, ruta_completa, nota_general, contexto_extra=""):
        """Envía una imagen a OpenAI y retorna (metadatos_dict, tokens_usados)."""
        if not os.path.exists(ruta_completa):
            return None, 0
        try:
            img_b64 = self.codificar_imagen(ruta_completa)
            
            contexto_completo = nota_general.strip() if nota_general else ""
            if contexto_extra and contexto_extra.strip():
                if contexto_completo:
                    contexto_completo += f"\nNotas adicionales: {contexto_extra.strip()}"
                else:
                    contexto_completo = contexto_extra.strip()

            texto_usuario = (
                "Metodología de catalogación obligatoria:\n"
                "1. Examina primero la imagen adjunta para identificar la escena real visible.\n"
                f"2. Contexto oficial del proyecto: \"{contexto_completo}\".\n"
                "   - Si la categoría general visible coincide con la temática del proyecto (ej. observas animales, cultivos o labores afines), ADOPTA la especie y terminología oficial del proyecto (no especules con especies o variedades afines ni alternes con nombres científicos en latín).\n"
                "   - Si la imagen muestra elementos no relacionados con el proyecto (otra clase o familia animal, maquinaria, paisaje, personas), cataloga estrictamente lo visible sin forzar la temática del proyecto.\n\n"
                "Genera el JSON correspondiente cumpliendo todas las reglas del sistema."
                if contexto_completo else
                "Examina la imagen adjunta y genera el JSON correspondiente cumpliendo las reglas del sistema."
            )

            params = {
                "model": self.modelo,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": self.prompt_sistema},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_b64}",
                                    "detail": self.image_detail,
                                },
                            },
                            {
                                "type": "text",
                                "text": texto_usuario,
                            },
                        ],
                    },
                ],
            }

            # Configuración para modelos de razonamiento (familia gpt-6, o1, o3, etc.)
            mod_low = self.modelo.lower()
            es_modelo_razonamiento = any(mod_low.startswith(p) for p in ['gpt-6', 'o1', 'o3'])
            if es_modelo_razonamiento:
                if self.reasoning_effort and str(self.reasoning_effort).lower() != 'none':
                    params["reasoning_effort"] = str(self.reasoning_effort).lower()
                # Los modelos de razonamiento como GPT-6 y O1 no permiten temperature != 1
            else:
                try:
                    t = float(str(self.temperatura).replace(',', '.'))
                    params["temperature"] = round(max(0.0, min(2.0, t)), 2)
                except (ValueError, TypeError):
                    params["temperature"] = 0.2

            try:
                response = self.client.chat.completions.create(**params)
            except Exception as api_err:
                err_str = str(api_err).lower()
                # Reintento defensivo: si rechaza temperature, removerla y reintentar
                if "temperature" in err_str and "temperature" in params:
                    del params["temperature"]
                    response = self.client.chat.completions.create(**params)
                # Reintento defensivo: si rechaza reasoning_effort, removerlo y reintentar
                elif "reasoning_effort" in err_str and "reasoning_effort" in params:
                    del params["reasoning_effort"]
                    response = self.client.chat.completions.create(**params)
                else:
                    raise api_err

            datos = json.loads(response.choices[0].message.content)
            tokens = response.usage.total_tokens if response.usage else 0
            return datos, tokens
        except Exception as e:
            self.log(f"  → Error con la IA: {e}")
            return None, 0

    # ------------------------------------------------------------------
    # Proceso principal
    # ------------------------------------------------------------------

    def catalogar(self, proyecto_dir, forzar_recatalogar=False, contexto_extra=""):
        """
        Proceso principal de catalogación.
        Retorna True si terminó correctamente, False si hubo error o se canceló.
        """
        self.reset()

        # Buscar CSV
        csv_salida = os.path.join(proyecto_dir, "Catalogo_OpenAI_Completo.csv")
        csv_base_files = [
            f for f in os.listdir(proyecto_dir)
            if f.lower().endswith('.csv') and not f.startswith('Catalogo_OpenAI')
        ]

        if os.path.exists(csv_salida) and not forzar_recatalogar:
            ruta_csv = csv_salida
            self.log(f"Retomando progreso desde {os.path.basename(csv_salida)}...")
        elif csv_base_files:
            ruta_csv = os.path.join(proyecto_dir, csv_base_files[0])
            self.log(f"Usando CSV base: {csv_base_files[0]}")
        else:
            self.log("❌ No se encontró ningún archivo CSV en la carpeta del proyecto.")
            return False

        # Carpeta de fotos
        carpeta_fotos = os.path.join(proyecto_dir, "Fotos")
        if not os.path.exists(carpeta_fotos):
            carpeta_fotos = proyecto_dir

        # Leer CSV con múltiples encodings de respaldo
        df = None
        for enc in ['utf-8', 'latin1', 'cp1252']:
            try:
                if os.path.exists(csv_salida) and not forzar_recatalogar:
                    df = pd.read_csv(csv_salida, sep=',', encoding=enc, dtype=str)
                else:
                    df = pd.read_csv(ruta_csv, dtype=str, encoding=enc, sep=None, engine='python')
                break
            except Exception:
                continue

        if df is None:
            self.log(f"❌ Error: No se pudo leer el archivo CSV {os.path.basename(ruta_csv)}")
            return False

        df.columns = [c.strip() for c in df.columns]
        col_archivo = next(
            (c for c in df.columns if c.lower() in ['nombre archivo', 'filename', 'nombre_archivo', 'archivo', 'nombre']),
            'nombre archivo'
        )

        # Asegurar columnas destino
        columnas_destino = [
            'dc.title', 'dc.title.alternative', 'dc.description',
            'dc.description.abstract', 'dc.format.extent', 'dc.format.medium',
        ]
        for col in columnas_destino:
            if col not in df.columns:
                df[col] = ''
            df[col] = df[col].astype('object')

        total = len(df)
        self.log(f"Iniciando catalogación. Total: {total} registros.\n")

        def _buscar_foto(fname):
            p1 = os.path.join(proyecto_dir, fname)
            if os.path.exists(p1):
                return p1
            p2 = os.path.join(proyecto_dir, "Fotos", fname)
            if os.path.exists(p2):
                return p2
            # Si se busca .bmp pero existe .jpg
            base_no_ext, ext = os.path.splitext(fname)
            if ext.lower() == '.bmp':
                jpg_name = base_no_ext + '.jpg'
                if os.path.exists(os.path.join(proyecto_dir, jpg_name)):
                    return os.path.join(proyecto_dir, jpg_name)
                if os.path.exists(os.path.join(proyecto_dir, "Fotos", jpg_name)):
                    return os.path.join(proyecto_dir, "Fotos", jpg_name)
            # Probar variantes de extensión / nombres con dobles puntos (ej: loncom..jpg)
            for d in [proyecto_dir, os.path.join(proyecto_dir, "Fotos")]:
                if not os.path.exists(d):
                    continue
                for f in os.listdir(d):
                    if f.lower() == fname.lower() or f.lower().replace('..', '.') == fname.lower().replace('..', '.'):
                        return os.path.join(d, f)
                    if ext.lower() == '.bmp' and f.lower() == (base_no_ext + '.jpg').lower():
                        return os.path.join(d, f)
            return None

        for index, row in df.iterrows():
            if self._cancelado:
                self.log("\n⏹ Catalogación cancelada por el usuario.")
                df.to_csv(csv_salida, sep=',', index=False, encoding='utf-8')
                return False

            nombre_archivo = str(row.get(col_archivo, '')).strip()
            if not nombre_archivo or nombre_archivo == 'nan':
                continue

            ruta_completa = _buscar_foto(nombre_archivo)

            # Calcular resolución y peso (siempre, es gratis)
            if os.path.exists(ruta_completa):
                try:
                    size_mb = os.path.getsize(ruta_completa) / (1024 * 1024)
                    df.at[index, 'dc.format.medium'] = f"{size_mb:.2f} MB".replace('.', ',')
                    with Image.open(ruta_completa) as img:
                        df.at[index, 'dc.format.extent'] = f"{img.size[0]} x {img.size[1]} píxeles"
                except Exception as e:
                    self.log(f"Error leyendo info de {nombre_archivo}: {e}")

            # Comprobar si ya está catalogado
            if not forzar_recatalogar:
                title_val = row.get('dc.title')
                if pd.notna(title_val) and str(title_val).strip() != '':
                    self.log(f"[{index + 1}/{total}] Saltando (ya catalogado): {nombre_archivo}")
                    self.progress(index + 1, total)
                    df.to_csv(csv_salida, sep=',', index=False, encoding='utf-8')
                    continue

            nota_general = str(row.get('fia.notageneral', ''))
            metadatos, tokens = self._procesar_una_imagen(ruta_completa, nota_general, contexto_extra=contexto_extra)
            self.total_tokens += tokens

            self.log(
                f"[{index + 1}/{total}] Catalogando: {nombre_archivo} "
                f"| Tokens: {tokens} | Acumulado: {self.total_tokens}"
            )
            self.progress(index + 1, total)

            if metadatos:
                def _limpiar_titulo(t):
                    if not t:
                        return ""
                    return str(t).strip().rstrip('.').strip()

                df.at[index, 'dc.title'] = _limpiar_titulo(metadatos.get('dc.title', ''))
                df.at[index, 'dc.title.alternative'] = _limpiar_titulo(metadatos.get('dc.title.alternative', ''))
                df.at[index, 'dc.description'] = str(metadatos.get('dc.description', '')).strip()
                df.at[index, 'dc.description.abstract'] = str(metadatos.get('dc.description.abstract', '')).strip()
                # Guardado incremental
                df.to_csv(csv_salida, sep=',', index=False, encoding='utf-8')

        self.log(f"\n✅ ¡Catalogación terminada! Guardado como {os.path.basename(csv_salida)}")
        return True
