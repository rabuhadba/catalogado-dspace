# Catalogador Automático DSpace con OpenAI 

Esta herramienta automatiza la catalogación masiva de colecciones fotográficas utilizando Inteligencia Artificial (**OpenAI GPT-4o-mini**) y empaqueta los resultados en el formato **Simple Archive Format (SAF)** oficial, listos para ser importados a repositorios institucionales [DSpace](https://dspace.lyrasis.org/).

El script procesa lotes de imágenes, analiza su contenido visual y contexto, y genera metadatos estructurados. Luego, utiliza `SAFBuilder` (incluido) para transformar la información y las imágenes en paquetes de directorios listos para DSpace.

---

## 🛠 Características Principales

- **Análisis Visual con IA**: Generación de títulos alternativos y resúmenes descriptivos estructurados mediante GPT-4o-mini.
- **Empaquetado Automático SAF**: Invocación transparente a SAFBuilder (Java) para construir la estructura de items con `dublin_core.xml` y `contents`.
- **Reanudación del Progreso**: Si la ejecución se interrumpe, el script detecta las imágenes ya procesadas y continúa automáticamente.
- **Verificador de API DSpace**: Script secundario incluido para probar credenciales y conectividad con la API REST de DSpace 7+.

---

## Requisitos Previos

- **Python 3.8+** (Asegúrate de marcar "Add Python to PATH" durante la instalación).
- **Windows** (el script de instalación `.bat` está optimizado para entornos Windows).
- *Nota*: No requiere instalación previa de Java global en tu sistema.

---

## Instalación y Configuración (Primera Vez)

1. **Clona o descarga** este repositorio en tu PC.
2. Ejecuta haciendo doble clic el archivo `instalar_entorno.bat`:
   - Creará / actualizará el entorno con las dependencias de Python (`pandas`, `openai`, `python-dotenv`, `requests`).
   - Descargará un entorno **Java Portable (JDK)** local necesario para SAFBuilder sin alterar tu sistema.
3. Copia el archivo `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```
4. Abre `.env` con un editor de texto y completa tus credenciales:
   ```env
   OPENAI_API_KEY=sk-proj-tu-llave-aqui...
   DSPACE_URL=https://tudspace.cl/server/api
   DSPACE_EMAIL=tu_correo@institucion.cl
   DSPACE_PASSWORD=tu_contraseña
   ```

---

## Uso del Proyecto

### 1. Verificar Conexión a DSpace (Opcional)
Para comprobar que la URL y credenciales de DSpace respondan correctamente:
```bash
python verificar_dspace_api.py
```

### 2. Catalogación y Empaquetado SAF
Para iniciar el proceso de lectura de imágenes, generación de metadata con OpenAI y creación del paquete SAF:
```bash
python catalogador_openai.py
```

### 3. Salida Generada
El proceso genera localmente:
- **`SimpleArchiveFormat/`**: Carpeta principal con los subdirectorios numerados (`item_000`, `item_001`, ...) que contienen las imágenes, `dublin_core.xml` y `contents`.
- Archivos `.csv` con la metadata procesada.

---

##  Estructura del Repositorio

```
CATALOGADO DSPACE/
├── catalogador_openai.py       # Script principal de catalogación e integración SAF
├── verificar_dspace_api.py     # Script para prueba de autenticación REST en DSpace 7
├── instalar_entorno.bat        # Automatizador de entorno local (Python + JDK Portable)
├── requirements.txt            # Librerías de Python requeridas
├── .env.example                # Plantilla de variables de entorno
├── .gitignore                  # Exclusión de archivos pesados y sensibles
├── lib/                        # Ejecutable SAFBuilder JAR
└── README.md                   # Documentación del proyecto
```
