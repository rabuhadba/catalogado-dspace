import os
import pandas as pd
import base64
import json
import time
import shutil
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image

# Cargar variables de entorno desde el archivo .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "tu_llave_aqui":
    print("Error: No se ha configurado la API Key de OpenAI en el archivo .env")
    exit(1)

# Inicializar cliente de OpenAI
client = OpenAI(api_key=api_key)

# Pedir al usuario la ruta de red del proyecto
print("=========================================================")
print("      CONFIGURACIÓN DEL PROYECTO (SIN .ENV)              ")
print("=========================================================")
CARPETA_RED = input("Pega aquí la ruta de red de la carpeta del proyecto\n(ej: \\\\10.10.20.212\\...\\FIA-GI-V-1998-1-A-142):\n> ").strip()

if not CARPETA_RED or not os.path.exists(CARPETA_RED):
    print(f"❌ Error: La ruta '{CARPETA_RED}' no existe o está vacía.")
    exit(1)

# Extraer el nombre del proyecto desde la ruta de red (último segmento)
NOMBRE_PROYECTO = os.path.basename(CARPETA_RED.rstrip('\\/'))
if not NOMBRE_PROYECTO:
    print("❌ Error: No se pudo deducir el nombre del proyecto desde la ruta.")
    exit(1)

print("=========================================================")
print(f"      INICIANDO CATALOGADOR - PROYECTO: {NOMBRE_PROYECTO} ")
print("=========================================================")

PROYECTO_DIR = os.path.join("Proyectos", NOMBRE_PROYECTO)
# La carpeta de red ahora es el proyecto completo (Fotos + CSV)
# Si la copiamos completa, la llamaremos simplemente PROYECTO_DIR
if not os.path.exists(PROYECTO_DIR):
    print(f"\nCopiando proyecto completo desde la red a '{PROYECTO_DIR}'...")
    try:
        shutil.copytree(CARPETA_RED, PROYECTO_DIR)
        print("¡Copia completada con éxito!\n")
    except Exception as e:
        print(f"❌ Error al copiar la carpeta de red: {e}")
        exit(1)
else:
    print(f"\n✅ La carpeta local '{PROYECTO_DIR}' ya existe. Se usarán los archivos locales.")

# Buscar automáticamente el archivo CSV dentro de la carpeta copiada
csv_files = [f for f in os.listdir(PROYECTO_DIR) if f.lower().endswith('.csv') and not f.startswith('Catalogo_OpenAI')]
if not csv_files:
    print(f"❌ Error: No se encontró ningún archivo .csv en la carpeta del proyecto ({PROYECTO_DIR}).")
    exit(1)
if len(csv_files) > 1:
    print(f"⚠️ Advertencia: Se encontraron múltiples archivos CSV. Se usará el primero: {csv_files[0]}")
CSV_ENTRADA = csv_files[0]
ruta_csv = os.path.join(PROYECTO_DIR, CSV_ENTRADA)

# Asumimos que las fotos pueden estar sueltas en el proyecto o dentro de una subcarpeta "Fotos"
CARPETA_FOTOS = os.path.join(PROYECTO_DIR, "Fotos")
if not os.path.exists(CARPETA_FOTOS):
    # Si no existe la subcarpeta "Fotos", asumimos que las fotos están sueltas en la raíz del proyecto
    CARPETA_FOTOS = PROYECTO_DIR

CSV_SALIDA = os.path.join(PROYECTO_DIR, "Catalogo_OpenAI_Completo.csv")
print(f"-> CSV a procesar: {CSV_ENTRADA}")
print(f"-> Carpeta de fotos: {CARPETA_FOTOS}")
print("=========================================================\n")

def codificar_imagen(ruta_imagen):
    with open(ruta_imagen, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

prompt_sistema = """
Eres un documentalista experto catalogando un archivo fotográfico sobre un proyecto de rescate de textilería con lana de oveja y artesanas en Chile.
Genera los metadatos en formato JSON.
REGLAS ESTRICTAS:
1. Lenguaje: Español formal, técnico y bibliográfico. CERO INGLÉS.
2. Cero muletillas: No uses "La imagen muestra", "Se observa", "Fotografía de". Inicia directo con la acción o sujeto.
3. Precisión: Describe el proceso productivo (teñido a fuego, hilado, telar, etc.), herramientas y entorno.
4. Cero ambigüedades o especulaciones: No uses palabras de duda o suposición como "posiblemente", "quizás", "probablemente", "al parecer", etc. Escribe afirmaciones objetivas y categóricas sobre lo que es visible.

Debes devolver ÚNICAMENTE un objeto JSON con esta estructura exacta:
{
    "dc.title": "Título descriptivo directo y corto (máx 10 palabras).",
    "dc.title.alternative": "Título alternativo o variante que detalle la acción.",
    "dc.description": "Descripción objetiva y técnica de la escena, herramientas y labor.",
    "dc.description.abstract": "Resumen conciso del valor del proceso o contexto mostrado en la imagen."
}
"""

def procesar_imagen_openai(nombre_archivo, nota_general):
    ruta_completa = os.path.join(CARPETA_FOTOS, nombre_archivo)
    if not os.path.exists(ruta_completa):
        print(f"  -> Error: No se encontró {ruta_completa}")
        return None, 0
    
    try:
        imagen_base64 = codificar_imagen(ruta_completa)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[
                {
                    "role": "system",
                    "content": prompt_sistema
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Contexto oficial del proyecto: {nota_general}\n\nAnaliza esta fotografía apoyándote en el contexto entregado y devuelve el JSON correspondiente."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_base64}", "detail": "low"}}
                    ]
                }
            ],
            temperature=0.2 # Temperatura baja para que sea analítico y no invente
        )
        
        resultado_texto = response.choices[0].message.content
        datos_json = json.loads(resultado_texto)
        tokens_usados = response.usage.total_tokens if response.usage else 0
        return datos_json, tokens_usados
        
    except Exception as e:
        print(f"  -> Error con la IA: {e}")
        return None, 0

# Leer el CSV
try:
    if os.path.exists(CSV_SALIDA):
        df = pd.read_csv(CSV_SALIDA, sep=',', encoding='utf-8')
        print(f"Retomando progreso desde {CSV_SALIDA}...")
    else:
        print(f"Leyendo CSV base: {ruta_csv}")
        df = pd.read_csv(ruta_csv, dtype=str)
        print(f"Iniciando nuevo proceso desde {CSV_ENTRADA}...")
except Exception as e:
    print(f"Error al leer el CSV: {e}")
    exit()

# Asegurar que las columnas de destino existan y sean de tipo texto (object) 
# para evitar errores de pandas "Invalid value for dtype float64"
columnas_destino = ['dc.title', 'dc.title.alternative', 'dc.description', 'dc.description.abstract', 'dc.format.extent', 'dc.format.medium']
for col in columnas_destino:
    if col not in df.columns:
        df[col] = ''
    df[col] = df[col].astype('object')

total = len(df)
print(f"Iniciando catalogación con OpenAI. Total: {total} registros.\n")

total_tokens_acumulados = 0

for index, row in df.iterrows():
    nombre_archivo = str(row['nombre archivo']).strip()
    ruta_completa = os.path.join(CARPETA_FOTOS, nombre_archivo)
    
    # 1. Calcular SIEMPRE resolución y peso (es gratis y rápido)
    if os.path.exists(ruta_completa):
        try:
            size_mb = os.path.getsize(ruta_completa) / (1024 * 1024)
            df.at[index, 'dc.format.medium'] = f"{size_mb:.2f} MB".replace('.', ',')
            
            with Image.open(ruta_completa) as img:
                df.at[index, 'dc.format.extent'] = f"{img.size[0]} x {img.size[1]} píxeles"
        except Exception as e:
            print(f"Error leyendo info de {nombre_archivo}: {e}")
            
    # 2. Comprobar si ya está procesado por OpenAI para saltar
    if 'dc.title' in df.columns and pd.notna(row.get('dc.title')) and str(row.get('dc.title')).strip() != '':
        print(f"[{index + 1}/{total}] Saltando OpenAI (ya catalogado): {nombre_archivo}")
        # Guardar en caso de que solo hayamos actualizado peso/resolución
        df.to_csv(CSV_SALIDA, sep=',', index=False, encoding='utf-8')
        continue
        
    nota_general = str(row.get('fia.notageneral', ''))
    metadatos, tokens = procesar_imagen_openai(nombre_archivo, nota_general)
    total_tokens_acumulados += tokens
    
    print(f"[{index + 1}/{total}] Catalogando: {nombre_archivo} | Tokens: {tokens} | Total Acumulado: {total_tokens_acumulados}")
    
    if metadatos:
        df.at[index, 'dc.title'] = metadatos.get('dc.title', '')
        df.at[index, 'dc.title.alternative'] = metadatos.get('dc.title.alternative', '')
        df.at[index, 'dc.description'] = metadatos.get('dc.description', '')
        df.at[index, 'dc.description.abstract'] = metadatos.get('dc.description.abstract', '')
        
        # Guardado incremental
        df.to_csv(CSV_SALIDA, sep=',', index=False, encoding='utf-8')

print(f"\n¡Proceso de catalogación terminado! Archivo guardado como {CSV_SALIDA}")

# ==========================================
# GENERACIÓN DE SAF MEDIANTE SAFBUILDER
# ==========================================
import subprocess
import os

print("\nPreparando el CSV para SAFBuilder oficial...")

# 1. Leer el CSV final
df_saf = pd.read_csv(CSV_SALIDA)

# 2. Renombrar columnas clave para SAFBuilder
renombres = {}
if 'nombre archivo' in df_saf.columns:
    renombres['nombre archivo'] = 'filename'

if renombres:
    df_saf.rename(columns=renombres, inplace=True)

# Asignar la colección directamente desde el .env para todas las filas
collection_uuid = os.getenv("DSPACE_COLLECTION_UUID", "").strip()
if collection_uuid:
    df_saf['collections'] = collection_uuid
else:
    print("⚠️ ADVERTENCIA: DSPACE_COLLECTION_UUID está vacío en el .env. La columna collections quedará vacía.")

# 3. Añadir el prefijo 'Fotos/' a las rutas de los archivos
# Asegurarnos de que no lo hemos añadido ya en una ejecución anterior
df_saf['filename'] = df_saf['filename'].apply(
    lambda x: f"Fotos/{str(x).strip()}" if pd.notnull(x) and str(x) != 'nan' and not str(x).startswith("Fotos/") else str(x)
)

# 4. Guardar un nuevo CSV exclusivo para SAFBuilder
CSV_SAF = os.path.join(PROYECTO_DIR, "Catalogo_SAFBuilder.csv")
df_saf.to_csv(CSV_SAF, index=False, encoding='utf-8')
print(f"CSV para SAFBuilder generado: {CSV_SAF}")

# 4.5. Guardar un CSV solo con las nuevas columnas generadas por OpenAI
columnas_nuevas = ['filename', 'dc.title', 'dc.title.alternative', 'dc.description', 'dc.description.abstract']
columnas_existentes = [col for col in columnas_nuevas if col in df_saf.columns]
if columnas_existentes:
    df_nuevas = df_saf[columnas_existentes].copy()
    CSV_NUEVAS = os.path.join(PROYECTO_DIR, "Catalogo_OpenAI_NuevasColumnas.csv")
    df_nuevas.to_csv(CSV_NUEVAS, index=False, encoding='utf-8')
    print(f"CSV solo con columnas nuevas generado: {CSV_NUEVAS}")

# 5. Ejecutar SAFBuilder con Java descargado localmente
print("\nIniciando SAFBuilder (esto puede tomar unos segundos)...")
env = os.environ.copy()

saf_dir = os.path.dirname(os.path.abspath(__file__))
csv_absoluto = os.path.abspath(CSV_SAF)

try:
    # Llamada directa al JAR usando Java local de forma dinámica
    import glob
    java_exe_paths = glob.glob(os.path.join(saf_dir, 'jdk', '**', 'bin', 'java.exe'), recursive=True)
    if not java_exe_paths:
        print("❌ Error: No se encontró java.exe en la carpeta 'jdk'.")
        print("Asegúrate de haber ejecutado instalar_entorno.bat en este computador.")
        exit(1)
    
    java_exe = java_exe_paths[0]
    jar_file = os.path.join(saf_dir, 'lib', 'safbuilder.jar')
    comando = f'"{java_exe}" -jar "{jar_file}" -c "{csv_absoluto}"'
    
    resultado = subprocess.run(comando, cwd=saf_dir, env=env, text=True, capture_output=True, shell=True)
    if resultado.returncode == 0:
        print("¡Paquete SAF generado exitosamente por SAFBuilder Oficial!")
        print("El resultado se encuentra en un subdirectorio 'SimpleArchiveFormat' creado al lado de tu CSV.")
    else:
        print("Ocurrió un error al ejecutar SAFBuilder:")
        print(resultado.stderr)
        print(resultado.stdout)
except Exception as e:
    print(f"Excepción al ejecutar SAFBuilder: {e}")