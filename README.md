# Catalogador e Importador Automático DSpace 7 con OpenAI 📸🤖

Esta herramienta automatiza la catalogación masiva de colecciones fotográficas utilizando Inteligencia Artificial (**OpenAI GPT-4o-mini**) y la importación directa a repositorios institucionales [DSpace 7+](https://dspace.lyrasis.org/) mediante su API REST.

El flujo de trabajo se divide en dos pasos principales: el análisis visual con IA para generar metadatos, y la subida automática de los archivos y metadatos directo a la bandeja de envíos (Workspace) del repositorio.

---

## Características Principales

- **Análisis Visual con IA**: Generación de títulos alternativos y resúmenes descriptivos estructurados mediante GPT-4o-mini.
- **Importación Directa API REST**: Subida automática de bitstreams y metadatos directo a DSpace 7+, saltándose el antiguo método SAF.
- **Flujo de Trabajo Dinámico**: Los scripts son interactivos. No necesitas editar código ni variables de entorno para cada proyecto nuevo; el sistema te pregunta qué carpeta procesar.
- **Gestión de Licencias Automática**: El script acepta automáticamente la licencia de depósito institucional de DSpace por debajo.
- **Reanudación del Progreso**: Si la catalogación se interrumpe, el script detecta las imágenes ya procesadas y continúa automáticamente.

---

## Requisitos Previos

- **Python 3.8+** (Asegúrate de marcar "Add Python to PATH" durante la instalación).
- **Windows** (el script de instalación `.bat` está optimizado para entornos Windows).

---

## Instalación y Configuración (Primera Vez)

1. **Clona o descarga** este repositorio en tu PC.
2. Ejecuta haciendo doble clic el archivo `instalar_entorno.bat`:
   - Creará el entorno con las dependencias de Python necesarias (`pandas`, `openai`, `python-dotenv`, `requests`).
3. Copia el archivo `.env.example` y renómbralo a `.env`:
   ```bash
   copy .env.example .env
   ```
4. Abre `.env` con un editor de texto y completa tus credenciales fijas:
   ```env
   OPENAI_API_KEY=sk-proj-tu-llave-aqui...
   DSPACE_URL=https://tudspace.cl/server/api
   DSPACE_EMAIL=tu_correo@institucion.cl
   DSPACE_PASSWORD=tu_contraseña
   DSPACE_COLLECTION_UUID=uuid-de-la-coleccion-destino
   ```

---

## 💡 Flujo de Trabajo (Uso Diario)

### Paso 1: Catalogación con IA
Ejecuta el catalogador para descargar las fotos desde la red y generar la metadata.
```bash
python catalogador_openai.py
```
- El script te pedirá que pegues la **ruta de red** de la carpeta del proyecto.
- Copiará automáticamente las fotos y el archivo `.csv` base a tu computador local (en la carpeta `Proyectos/`).
- Analizará las imágenes y generará un archivo `Catalogo_OpenAI_Completo.csv`.

### Paso 2: Subida a DSpace 7 (Borradores)
Una vez que el catalogador termine, sube todo a DSpace.
```bash
python importador_dspace_api.py
```
- El script te mostrará una lista de los proyectos que tienes en tu carpeta local `Proyectos/`.
- Selecciona el número del proyecto que deseas subir.
- El script creará los borradores en la bandeja de **"Sus envíos"** de tu DSpace, aplicará los metadatos, subirá las fotos y aceptará la licencia automáticamente.

*(Nota: Los ítems quedarán como borradores para que puedas revisarlos y aprobarlos manualmente en la página web).*

---

## Estructura del Repositorio

```
CATALOGADO DSPACE/
├── catalogador_openai.py       # Descarga desde red y cataloga con IA
├── importador_dspace_api.py    # Sube borradores a DSpace 7 vía REST API
├── verificar_dspace_api.py     # Script para prueba de autenticación REST
├── instalar_entorno.bat        # Automatizador de entorno local (Python)
├── requirements.txt            # Librerías de Python requeridas
├── .env.example                # Plantilla de variables de entorno fijas
├── .gitignore                  # Exclusión de archivos pesados y sensibles
└── README.md                   # Documentación del proyecto
```

---

## 🔒 Ignorados por Git (`.gitignore`)

Por seguridad y eficiencia, los siguientes elementos **NO** se suben al repositorio en GitHub:
- `.env` (credenciales y llaves de API).
- `Proyectos/` (imágenes locales, CSVs generados y datos de catalogación).
- Archivos generados temporalmente durante las pruebas.
