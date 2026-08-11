import os
import requests
import json
import xml.etree.ElementTree as ET
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
    print(f"❌ ERROR: No existe la carpeta '{base_proyectos}'.")
    exit(1)

carpetas = [d for d in os.listdir(base_proyectos) if os.path.isdir(os.path.join(base_proyectos, d))]
if not carpetas:
    print(f"❌ ERROR: No hay ningún proyecto en la carpeta '{base_proyectos}'.")
    exit(1)

print("=========================================================")
print("      SELECCIÓN DE PROYECTO A IMPORTAR                   ")
print("=========================================================")
for i, d in enumerate(carpetas, 1):
    print(f"[{i}] {d}")

seleccion = input("\nIngresa el número del proyecto que deseas subir a DSpace:\n> ").strip()
try:
    idx = int(seleccion) - 1
    if idx < 0 or idx >= len(carpetas):
        raise ValueError
    NOMBRE_PROYECTO = carpetas[idx]
except ValueError:
    print("❌ Selección inválida. Debes ingresar un número de la lista.")
    exit(1)
    
print(f"\n✅ Proyecto seleccionado: {NOMBRE_PROYECTO}\n")
SAF_DIR = os.path.join("Proyectos", NOMBRE_PROYECTO, "SimpleArchiveFormat")
LOG_FILE = os.path.join("Proyectos", NOMBRE_PROYECTO, "registro_subida.txt")

def iniciar_sesion():
    print(f"Conectando a {DSPACE_URL}...")
    session = requests.Session()
    login_url = f"{DSPACE_URL}/authn/login"
    
    # Obtener token CSRF inicial
    session.post(login_url)
    csrf_token = session.cookies.get("DSPACE-XSRF-COOKIE")
    headers = {"X-XSRF-TOKEN": csrf_token} if csrf_token else {}
    
    # Iniciar sesión
    resp = session.post(login_url, data={"user": DSPACE_EMAIL, "password": DSPACE_PASSWORD}, headers=headers)
    if resp.status_code == 200:
        token = resp.headers.get("Authorization")
        # En DSpace 7 el CSRF token cambia tras el login. Lo tomamos de los headers o cookies.
        nuevo_csrf = resp.headers.get("DSPACE-XSRF-TOKEN") or session.cookies.get("DSPACE-XSRF-COOKIE") or csrf_token
        
        print("✅ Autenticación exitosa.")
        return session, token, nuevo_csrf
    else:
        print(f"❌ Error al iniciar sesión: {resp.status_code}")
        exit(1)

def leer_saf_metadata(item_path):
    """Extrae metadatos de TODOS los archivos .xml del paquete SAF"""
    metadatos = {}
    
    for filename in os.listdir(item_path):
        if not filename.endswith(".xml"):
            continue
            
        xml_file = os.path.join(item_path, filename)
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # Si el archivo tiene schema definido (ej: schema="fia"), lo usamos, si no "dc"
            schema = root.attrib.get("schema", "dc")
            
            for child in root:
                if child.tag == "dcvalue":
                    elemento = child.attrib.get("element", "")
                    calificador = child.attrib.get("qualifier", "none")
                    valor = child.text
                    
                    if valor is None:
                        continue
                        
                    campo = f"{schema}.{elemento}"
                    if calificador and calificador != "none":
                        campo += f".{calificador}"
                    
                    if campo not in metadatos:
                        metadatos[campo] = []
                    metadatos[campo].append({"value": valor})
        except Exception as e:
            print(f"  -> Error leyendo XML {filename}: {e}")
                
    return metadatos

def obtener_archivos_saf(item_path):
    """Obtiene los nombres de archivos listados en el 'contents'"""
    contents_file = os.path.join(item_path, "contents")
    archivos = []
    if os.path.exists(contents_file):
        with open(contents_file, "r", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    archivos.append(linea.strip())
    return archivos

def main():
    print("=========================================================")
    print("      IMPORTADOR API REST A DSPACE 7 (MODO SEGURO)       ")
    print(f"      PROYECTO ACTUAL: {NOMBRE_PROYECTO}")
    print("=========================================================")
    
    if not COLLECTION_UUID:
        print("❌ ERROR: Debes definir 'DSPACE_COLLECTION_UUID' en el archivo .env primero.")
        print("Este UUID indica a qué colección de la biblioteca irán a parar las fotos.")
        exit(1)
        
    if not os.path.exists(SAF_DIR):
        print(f"❌ ERROR: No se encontró la carpeta {SAF_DIR}.")
        print("Debes ejecutar el catalogador_openai.py primero para generar los paquetes.")
        exit(1)

    print("⚠️ ADVERTENCIA: Este script subirá los archivos reales a la biblioteca.")
    confirmacion = input("¿Estás 100% seguro de que deseas iniciar la carga? (escribe 'SI' para continuar): ")
    
    if confirmacion.strip().upper() != "SI":
        print("Operación cancelada por el usuario. No se cargó nada.")
        exit(0)
        
    session, token, csrf_token = iniciar_sesion()
    
    # Headers comunes para API REST
    api_headers = {
        "Authorization": token,
        "X-XSRF-TOKEN": csrf_token,
        "Accept": "application/json"
    }

    print("\nIniciando escaneo de la carpeta SAF...")
    items_procesados = 0
    
    for nombre_carpeta in sorted(os.listdir(SAF_DIR)):
        ruta_item = os.path.join(SAF_DIR, nombre_carpeta)
        if not os.path.isdir(ruta_item) or not nombre_carpeta.startswith("item_"):
            continue
            
        print(f"\nProcesando {nombre_carpeta}...")
        items_procesados += 1
        
        # MODO DE PRUEBA REMOVIDO: Se procesarán todas las carpetas
        metadatos = leer_saf_metadata(ruta_item)
        archivos = obtener_archivos_saf(ruta_item)
        
        # 1. Crear WorkspaceItem (borrador)
        ws_url = f"{DSPACE_URL}/submission/workspaceitems?owningCollection={COLLECTION_UUID}"
        ws_headers = api_headers.copy()
        # Enviar un JSON vacío o nulo para cumplir con el formato esperado
        ws_headers["Content-Type"] = "application/json"
        
        resp_ws = session.post(ws_url, headers=ws_headers, json={})
        
        if resp_ws.status_code != 201:
            print(f"❌ Error al crear borrador en DSpace (Status: {resp_ws.status_code}): {resp_ws.text}")
            continue
            
        ws_data = resp_ws.json()
        ws_id = ws_data.get("id")
        
        # Extraer el UUID del item interno
        try:
            item_uuid = ws_data["_embedded"]["item"]["id"]
            item_url = ws_data["_embedded"]["item"]["_links"]["self"]["href"]
        except KeyError:
            print("❌ No se pudo obtener el UUID del item creado.")
            continue
            
        print(f"  -> Borrador creado exitosamente (Workspace ID: {ws_id}, Item UUID: {item_uuid})")
        
        # Guardar en bitácora para posible rollback
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{item_uuid}\n")
        
        # 2. Aplicar Metadatos mediante PATCH directo al Item (salta las restricciones del formulario)
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
                
        # 3. Subir Archivos (Bitstreams)
        for archivo in archivos:
            ruta_archivo = os.path.join(ruta_item, archivo)
            if os.path.exists(ruta_archivo):
                with open(ruta_archivo, 'rb') as f:
                    # En DSpace 7 los archivos se suben al WorkspaceItem como multipart/form-data
                    bitstream_url = f"{DSPACE_URL}/submission/workspaceitems/{ws_id}"
                    
                    # Preparar los headers quitando Content-Type para que requests arme el multipart boundary solo
                    file_headers = {
                        "Authorization": token,
                        "X-XSRF-TOKEN": csrf_token,
                        "Accept": "application/json"
                    }
                    
                    files = {"file": (archivo, f, "image/jpeg")}
                    
                    resp_file = session.post(bitstream_url, headers=file_headers, files=files)
                    
                    if resp_file.status_code in [200, 201]:
                        print(f"  -> Archivo subido: {archivo}")
                    else:
                        print(f"  -> Error subiendo {archivo} (Status: {resp_file.status_code}): {resp_file.text}")

        # 4. Aceptar licencia y auto-publicar
        # a) Aceptar licencia
        license_patch = [{"op": "add", "path": "/sections/license/granted", "value": "true"}]
        session.patch(f"{DSPACE_URL}/submission/workspaceitems/{ws_id}", headers=patch_headers, json=license_patch)
        
        # b) Enviar al workflow (DESACTIVADO: Queda como borrador para revisión manual)
        # wf_url = f"{DSPACE_URL}/workflow/workflowitems"
        # wf_headers = api_headers.copy()
        # wf_headers["Content-Type"] = "text/uri-list"
        # ws_uri = f"{DSPACE_URL}/submission/workspaceitems/{ws_id}"
        # 
        # resp_wf = session.post(wf_url, headers=wf_headers, data=ws_uri)
        # if resp_wf.status_code in [200, 201, 204]:
        #     print("  -> ✅ Ítem publicado exitosamente en la colección.")
        # else:
        #     print(f"  -> ⚠️ Advertencia: No se pudo auto-publicar el ítem (Status {resp_wf.status_code}): {resp_wf.text}")
            
    print(f"\n✅ Proceso completado. Se intentó cargar {items_procesados} ítems.")

if __name__ == "__main__":
    main()
