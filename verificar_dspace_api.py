import os
import requests
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Lee las credenciales del .env
DSPACE_URL = os.getenv("DSPACE_URL", "https://tudspace.cl/server/api")
DSPACE_EMAIL = os.getenv("DSPACE_EMAIL")
DSPACE_PASSWORD = os.getenv("DSPACE_PASSWORD")

if not DSPACE_EMAIL or not DSPACE_PASSWORD:
    print("Por favor, agrega DSPACE_EMAIL y DSPACE_PASSWORD en tu archivo .env")
    exit(1)

print(f"Probando conexión a la API de DSpace en: {DSPACE_URL}")
print("=========================================================")

# 1. Intentar Login (solo lectura, no modifica nada)
login_url = f"{DSPACE_URL.rstrip('/')}/authn/login"
print(f"Intentando login con el usuario: {DSPACE_EMAIL}...")

try:
    session = requests.Session()
    # Paso A: Obtener el token CSRF inicial (necesario en DSpace 7+)
    session.post(login_url)
    csrf_token = session.cookies.get("DSPACE-XSRF-COOKIE")
    
    headers = {}
    if csrf_token:
        headers["X-XSRF-TOKEN"] = csrf_token
        
    # Paso B: Enviar las credenciales incluyendo el header CSRF
    response_login = session.post(login_url, data={"user": DSPACE_EMAIL, "password": DSPACE_PASSWORD}, headers=headers)
    
    if response_login.status_code == 200:
        print("✅ Autenticación exitosa.")
        # DSpace 7 devuelve el token en los headers de la respuesta
        token = response_login.headers.get("Authorization")
        
        if not token:
            print("⚠️ Autenticación correcta pero no se recibió el token de Autorización.")
            exit(1)
            
        print("✅ Token recibido correctamente.")
        
        # 2. Verificar estado y permisos del usuario autenticado (solo lectura)
        status_url = f"{DSPACE_URL.rstrip('/')}/authn/status"
        headers["Authorization"] = token
        
        print("\nVerificando información y permisos del usuario...")
        response_status = session.get(status_url, headers=headers)
        
        if response_status.status_code == 200:
            datos_usuario = response_status.json()
            if datos_usuario.get("authenticated", False):
                print("✅ El usuario está activo y autenticado en el sistema.")
                # Extraer nombre si está disponible en la respuesta del status
                eperson = datos_usuario.get("_embedded", {}).get("eperson", {})
                nombre = eperson.get("name", "Desconocido")
                print(f"✅ Identidad confirmada: {nombre}")
                print("\nTodo se ve perfecto. Tienes acceso a la API REST de DSpace.")
            else:
                print("❌ El sistema dice que no estás autenticado a pesar del token.")
        else:
            print(f"❌ Error al consultar el status. Código HTTP: {response_status.status_code}")
            
    elif response_login.status_code == 401:
        print("❌ Credenciales incorrectas. (Error 401: Authentication failed)")
    elif response_login.status_code == 403:
        print(f"❌ Acceso denegado (Error 403). Mensaje del servidor: {response_login.text}")
    else:
        print(f"❌ Falló la conexión. Código HTTP: {response_login.status_code}")
        print("Asegúrate de que la URL de la API es correcta.")
        
except requests.exceptions.RequestException as e:
    print(f"❌ Error de conexión de red: {e}")
    print("Verifica si estás conectado a la VPN (si aplica) o si la URL está escrita correctamente.")
