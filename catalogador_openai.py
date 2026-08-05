import os
import pandas as pd
import base64
import json
import time
import shutil
from openai import OpenAI
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "tu_llave_aqui":
    print("Error: No se ha configurado la API Key de OpenAI en el archivo .env")
    exit(1)

# Inicializar cliente de OpenAI
client = OpenAI(api_key=api_key)

# Archivos de entrada y salida
CSV_ENTRADA = "Fotos_COC-2016-0429.csv" 
CSV_SALIDA = "Catalogo_OpenAI_Completo.csv"
CARPETA_RED = r"\\10.10.20.212\nuevo-todo\Proyectos_originales\COC-2016-0429\Fotos"
CARPETA_FOTOS = "Fotos"

# Copiar fotos a local si no existen
if not os.path.exists(CARPETA_FOTOS):
    print(f"Copiando fotos desde {CARPETA_RED} a la carpeta local '{CARPETA_FOTOS}'...")
    try:
        shutil.copytree(CARPETA_RED, CARPETA_FOTOS)
        print("¡Copia completada con éxito!\n")
    except Exception as e:
        print(f"Error al copiar la carpeta de red: {e}")
        exit()

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
        df = pd.read_csv(CSV_ENTRADA, sep=',', encoding='utf-8')
        print(f"Iniciando nuevo proceso desde {CSV_ENTRADA}...")
except Exception as e:
    print(f"Error al leer el CSV: {e}")
    exit()

total = len(df)
print(f"Iniciando catalogación con OpenAI. Total: {total} registros.\n")

total_tokens_acumulados = 0

for index, row in df.iterrows():
    nombre_archivo = str(row['nombre archivo']).strip()
    
    # Comprobar si ya está procesado
    if 'dc.title' in df.columns and pd.notna(row.get('dc.title')) and str(row.get('dc.title')).strip() != '':
        print(f"[{index + 1}/{total}] Saltando (ya catalogado): {nombre_archivo}")
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
if 'Colección' in df_saf.columns:
    renombres['Colección'] = 'collections'

if renombres:
    df_saf.rename(columns=renombres, inplace=True)

# 3. Añadir el prefijo 'Fotos/' a las rutas de los archivos
# Asegurarnos de que no lo hemos añadido ya en una ejecución anterior
df_saf['filename'] = df_saf['filename'].apply(
    lambda x: f"Fotos/{str(x).strip()}" if pd.notnull(x) and str(x) != 'nan' and not str(x).startswith("Fotos/") else str(x)
)

# 4. Guardar un nuevo CSV exclusivo para SAFBuilder
CSV_SAF = "Catalogo_SAFBuilder.csv"
df_saf.to_csv(CSV_SAF, index=False, encoding='utf-8')
print(f"CSV para SAFBuilder generado: {CSV_SAF}")

# 4.5. Guardar un CSV solo con las nuevas columnas generadas por OpenAI
columnas_nuevas = ['filename', 'dc.title', 'dc.title.alternative', 'dc.description', 'dc.description.abstract']
columnas_existentes = [col for col in columnas_nuevas if col in df_saf.columns]
if columnas_existentes:
    df_nuevas = df_saf[columnas_existentes].copy()
    CSV_NUEVAS = "Catalogo_OpenAI_NuevasColumnas.csv"
    df_nuevas.to_csv(CSV_NUEVAS, index=False, encoding='utf-8')
    print(f"CSV solo con columnas nuevas generado: {CSV_NUEVAS}")

# 5. Ejecutar SAFBuilder con Java descargado localmente
print("\nIniciando SAFBuilder (esto puede tomar unos segundos)...")
env = os.environ.copy()

saf_dir = os.path.dirname(os.path.abspath(__file__))
csv_absoluto = os.path.abspath(CSV_SAF)

try:
    # Llamada directa al JAR usando Java local, evitando problemas con los .bat de Windows
    java_exe = os.path.join(saf_dir, 'jdk', 'jdk-21.0.3+9', 'bin', 'java.exe')
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