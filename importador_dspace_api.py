import os
import pandas as pd
import requests
from dotenv import load_dotenv

# ==========================================
# CONFIGURACIÓN
# ==========================================
load_dotenv()

DSPACE_URL = os.getenv("DSPACE_URL", "").rstrip('/')
DSPACE_EMAIL = os.getenv("DSPACE_EMAIL")
DSPACE_PASSWORD = os.getenv("DSPACE_PASSWORD")
COLLECTION_UUID = os.getenv("DSPACE_COLLECTION_UUID")

# Elegir proyecto dinámicamente desde las carpetas existentes
base_proyectos = "Proyectos"
if not os.path.exists(base_proyectos):
    print(f"No existe la carpeta '{base_proyectos}'.")
    exit(1)

carpetas = [d for d in os.listdir(base_proyectos) if os.path.isdir(os.path.join(base_proyectos, d))]
if not carpetas:
    print(f"No hay ningun proyecto en la carpeta '{base_proyectos}'.")
    exit(1)

print("=========================================================")
print("      SELECCION DE PROYECTO A IMPORTAR                   ")
print("=========================================================")
for i, d in enumerate(carpetas, 1):
    print(f"[{i}] {d}")

seleccion = input("\nIngresa el numero del proyecto que deseas subir a DSpace:\n> ").strip()
try:
    idx = int(seleccion) - 1
    if idx < 0 or idx >= len(carpetas):
        raise ValueError
    NOMBRE_PROYECTO = carpetas[idx]
except ValueError:
    print("Seleccion invalida. Debes ingresar un numero de la lista.")
    exit(1)

print(f"\nProyecto seleccionado: {NOMBRE_PROYECTO}\n")
PROYECTO_DIR = os.path.join("Proyectos", NOMBRE_PROYECTO)
LOG_FILE = os.path.join(PROYECTO_DIR, "registro_subida.txt")

# ==========================================
# LECTURA DIRECTA DEL CSV (SIN SAF)
# ==========================================

def buscar_csv_catalogo(proyecto_dir):
    """Busca el CSV de catalogo OpenAI en la carpeta del proyecto"""
    csv_completo = os.path.join(proyecto_dir, "Catalogo_OpenAI_Completo.csv")
    if os.path.exists(csv_completo):
        return csv_completo
    print(f"ERROR: No se encontro {csv_completo}")
    print("Debes ejecutar catalogador_openai.py primero.")
    exit(1)

def buscar_foto(nombre_archivo, proyecto_dir):
    """Busca la foto en la carpeta del proyecto (suelta o en subcarpeta Fotos)"""
    # Primero buscar suelta en la raiz del proyecto
    ruta = os.path.join(proyecto_dir, nombre_archivo)
    if os.path.exists(ruta):
        return ruta
    # Luego en subcarpeta Fotos
    ruta = os.path.join(proyecto_dir, "Fotos", nombre_archivo)
    if os.path.exists(ruta):
        return ruta
    return None

def leer_metadatos_csv(csv_path):
    """Lee el CSV y devuelve una lista de diccionarios con metadatos y nombre de archivo por fila"""
    df = pd.read_csv(csv_path, dtype=str)
    items = []
    
    # Identificar la columna del nombre de archivo
    col_archivo = None
    for posible in ['nombre archivo', 'filename', 'Nombre Archivo']:
        if posible in df.columns:
            col_archivo = posible
            break
    
    if not col_archivo:
        print(f"ERROR: No se encontro columna de nombre de archivo en el CSV.")
        print(f"Columnas disponibles: {list(df.columns)}")
        exit(1)
    
    # Columnas que son metadatos DSpace (empiezan con dc. o fia. o similares)
    columnas_metadatos = [c for c in df.columns if '.' in c and c != col_archivo]
    
    for _, row in df.iterrows():
        nombre_archivo = str(row[col_archivo]).strip()
        if not nombre_archivo or nombre_archivo == 'nan':
            continue
            
        metadatos = {}
        for col in columnas_metadatos:
            valor = str(row.get(col, '')).strip()
            if valor and valor != 'nan':
                if col not in metadatos:
                    metadatos[col] = []
                metadatos[col].append({"value": valor})
        
        items.append({
            "nombre_archivo": nombre_archivo,
            "metadatos": metadatos
        })
    
    return items

# ==========================================
# CONEXIÓN A DSPACE
# ==========================================

def iniciar_sesion():
    print(f"Conectando a {DSPACE_URL}...")
    session = requests.Session()
    login_url = f"{DSPACE_URL}/authn/login"
    
    # Obtener token CSRF inicial
    session.post(login_url)
    csrf_token = session.cookies.get("DSPACE-XSRF-COOKIE")
    headers = {"X-XSRF-TOKEN": csrf_token} if csrf_token else {}
    
    # Iniciar sesion
    resp = session.post(login_url, data={"user": DSPACE_EMAIL, "password": DSPACE_PASSWORD}, headers=headers)
    if resp.status_code == 200:
        token = resp.headers.get("Authorization")
        nuevo_csrf = resp.headers.get("DSPACE-XSRF-TOKEN") or session.cookies.get("DSPACE-XSRF-COOKIE") or csrf_token
        
        print("Autenticacion exitosa.\n")
        return session, token, nuevo_csrf
    else:
        print(f"Error al iniciar sesion: {resp.status_code}")
        exit(1)

# ==========================================
# FUNCIÓN PRINCIPAL
# ==========================================

def main():
    print("=========================================================")
    print("      IMPORTADOR API REST A DSPACE 7                     ")
    print(f"      PROYECTO: {NOMBRE_PROYECTO}")
    print("=========================================================")
    
    if not COLLECTION_UUID:
        print("ERROR: Debes definir 'DSPACE_COLLECTION_UUID' en el archivo .env primero.")
        exit(1)
    
    # Leer metadatos directamente del CSV
    csv_path = buscar_csv_catalogo(PROYECTO_DIR)
    items = leer_metadatos_csv(csv_path)
    total = len(items)
    
    print(f"Se encontraron {total} items para importar desde el CSV.")
    print("ADVERTENCIA: Este script subira los archivos reales a la biblioteca.")
    confirmacion = input("Deseas iniciar la carga? (escribe 'SI' para continuar): ")
    
    if confirmacion.strip().upper() != "SI":
        print("Operacion cancelada por el usuario.")
        exit(0)
    
    session, token, csrf_token = iniciar_sesion()
    
    # Headers comunes para API REST
    api_headers = {
        "Authorization": token,
        "X-XSRF-TOKEN": csrf_token,
        "Accept": "application/json"
    }
    
    items_ok = 0
    items_error = 0
    
    for i, item in enumerate(items, 1):
        nombre_archivo = item["nombre_archivo"]
        metadatos = item["metadatos"]
        
        print(f"\n[{i}/{total}] Procesando: {nombre_archivo}")
        
        # 1. Crear WorkspaceItem (borrador)
        ws_url = f"{DSPACE_URL}/submission/workspaceitems?owningCollection={COLLECTION_UUID}"
        ws_headers = api_headers.copy()
        ws_headers["Content-Type"] = "application/json"
        
        resp_ws = session.post(ws_url, headers=ws_headers, json={})
        
        if resp_ws.status_code != 201:
            print(f"  -> Error al crear borrador (Status: {resp_ws.status_code})")
            items_error += 1
            continue
        
        ws_data = resp_ws.json()
        ws_id = ws_data.get("id")
        
        try:
            item_uuid = ws_data["_embedded"]["item"]["id"]
        except KeyError:
            print("  -> No se pudo obtener el UUID del item creado.")
            items_error += 1
            continue
        
        print(f"  -> Borrador creado (WS: {ws_id}, UUID: {item_uuid})")
        
        # Guardar en bitacora para posible rollback
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{item_uuid}\n")
        
        # 2. Aplicar Metadatos mediante PATCH directo al Item
        patch_ops = []
        for campo, valores in metadatos.items():
            for valor_dict in valores:
                patch_ops.append({
                    "op": "add",
                    "path": f"/metadata/{campo}",
                    "value": valor_dict
                })
        
        if patch_ops:
            patch_headers = api_headers.copy()
            patch_headers["Content-Type"] = "application/json"
            patch_url = f"{DSPACE_URL}/core/items/{item_uuid}"
            
            resp_patch = session.patch(patch_url, headers=patch_headers, json=patch_ops)
            if resp_patch.status_code == 200:
                print("  -> Metadatos aplicados correctamente.")
            else:
                print(f"  -> Error aplicando metadatos: {resp_patch.text}")
        
        # 3. Subir Foto (Bitstream)
        ruta_foto = buscar_foto(nombre_archivo, PROYECTO_DIR)
        if ruta_foto:
            with open(ruta_foto, 'rb') as f:
                bitstream_url = f"{DSPACE_URL}/submission/workspaceitems/{ws_id}"
                
                file_headers = {
                    "Authorization": token,
                    "X-XSRF-TOKEN": csrf_token,
                    "Accept": "application/json"
                }
                
                files = {"file": (nombre_archivo, f, "image/jpeg")}
                resp_file = session.post(bitstream_url, headers=file_headers, files=files)
                
                if resp_file.status_code in [200, 201]:
                    print(f"  -> Foto subida: {nombre_archivo}")
                else:
                    print(f"  -> Error subiendo foto (Status: {resp_file.status_code})")
        else:
            print(f"  -> ADVERTENCIA: No se encontro la foto {nombre_archivo} en disco.")
        
        # 4. Aceptar licencia
        license_patch = [{"op": "add", "path": "/sections/license/granted", "value": "true"}]
        patch_headers = api_headers.copy()
        patch_headers["Content-Type"] = "application/json"
        session.patch(f"{DSPACE_URL}/submission/workspaceitems/{ws_id}", headers=patch_headers, json=license_patch)
        
        items_ok += 1
    
    print(f"\n=========================================================")
    print(f"  RESULTADO: {items_ok} exitosos, {items_error} con error")
    print(f"=========================================================")
    
    # ---------------------------------------------------------
    # LIMPIEZA FINAL DE ARCHIVOS PESADOS
    # ---------------------------------------------------------
    if items_ok > 0:
        print("\n=========================================================")
        print("      LIMPIEZA DE ESPACIO LOCAL                          ")
        print("=========================================================")
        print("Los borradores ya estan seguros en la nube de DSpace.")
        limpiar = input("Deseas borrar las fotos locales para liberar espacio? (Solo se conservara el CSV) [S/N]: ").strip().upper()
        
        if limpiar == 'S':
            import shutil
            
            # Borrar carpeta Fotos si existe
            carpeta_fotos = os.path.join(PROYECTO_DIR, "Fotos")
            if os.path.exists(carpeta_fotos):
                try:
                    shutil.rmtree(carpeta_fotos)
                    print(f"  Carpeta '{carpeta_fotos}' eliminada.")
                except Exception as e:
                    print(f"  Error al borrar Fotos: {e}")
            else:
                # Borrar fotos sueltas
                exts_imagen = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tif', '.tiff')
                try:
                    for arch in os.listdir(PROYECTO_DIR):
                        if arch.lower().endswith(exts_imagen):
                            os.remove(os.path.join(PROYECTO_DIR, arch))
                    print(f"  Imagenes sueltas eliminadas de '{PROYECTO_DIR}'.")
                except Exception as e:
                    print(f"  Error al borrar imagenes: {e}")
            
            # Borrar carpeta SAF residual si existe (de ejecuciones anteriores)
            saf_dir = os.path.join(PROYECTO_DIR, "SimpleArchiveFormat")
            if os.path.exists(saf_dir):
                try:
                    shutil.rmtree(saf_dir)
                    print(f"  Carpeta SAF residual eliminada.")
                except Exception as e:
                    print(f"  Error al borrar SAF: {e}")
            
            # Borrar todos los CSV excepto Catalogo_OpenAI_Completo.csv
            try:
                for arch in os.listdir(PROYECTO_DIR):
                    if arch.lower().endswith('.csv') and arch != "Catalogo_OpenAI_Completo.csv":
                        os.remove(os.path.join(PROYECTO_DIR, arch))
                        print(f"  Archivo temporal '{arch}' eliminado.")
            except Exception as e:
                print(f"  Error al borrar CSVs temporales: {e}")
            
            print("Limpieza terminada. Solo quedo Catalogo_OpenAI_Completo.csv")
        else:
            print("Conservando los archivos locales intactos.")

if __name__ == "__main__":
    main()
