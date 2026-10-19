# Catalogador y Gestor de Importación DSpace 7

Aplicación integral con interfaz gráfica (GUI) para la catalogación automatizada de proyectos y colecciones fotográficas con Inteligencia Artificial (OpenAI), estructuración de paquetes de archivo SAF y subida directa mediante API REST a DSpace 7.

---

## Características Principales

* **Interfaz Gráfica Intuitiva (`app_gui.py`)**: Gestión visual completa de proyectos, configuración y monitoreo del proceso en tiempo real.
* **Catalogación Inteligente con IA**: Análisis multimodal de imágenes y metadatos usando OpenAI (GPT-4o / GPT-4o-mini) con soporte de prompts personalizables (`prompt_sistema.txt`).
* **Soporte de Relaciones y SAF Builder**: Creación y validación de relaciones complejas entre ítems y generación de paquetes estándar Simple Archive Format (SAF).
* **Integración API REST DSpace 7**: Creación de borradores, asignación de metadatos calificados y carga de bitstreams directamente al repositorio.
* **Resumible y Tolerante a Fallos**: Retoma proyectos incompletos sin reprocesar ítems ya catalogados.

---

## Estructura del Proyecto

```text
├── app_gui.py                  # Interfaz gráfica principal (CustomTkinter / Tkinter)
├── Catalogador_DSpace.spec     # Especificación para empaquetado con PyInstaller
├── prompt_sistema.txt          # Prompt base para el análisis con IA
├── requirements.txt            # Dependencias de Python
├── Manual_Relaciones.docx      # Documentación y lineamientos de relaciones
├── core/
│   ├── catalogador.py          # Lógica de procesamiento y catalogación con OpenAI
│   ├── importador.py           # Cliente API REST DSpace 7
│   ├── relacionador.py         # Mapeo y validación de relaciones
│   └── saf_builder.py          # Generador de estructura SAF (dublin_core.xml, contents, etc.)
├── .env.example                # Plantilla de variables de entorno requeridas
└── .gitignore                  # Reglas de exclusión de Git
```

---

## Instalación y Configuración

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/rabuhadba/catalogado-dspace.git
   cd catalogado-dspace
   ```

2. **Crear entorno virtual e instalar dependencias**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configurar variables de entorno**:
   Copiar `.env.example` como `.env` y configurar las credenciales:
   ```bash
   copy .env.example .env
   ```
   Configura tus credenciales de DSpace y OpenAI:
   - `OPENAI_API_KEY`: Tu clave de API de OpenAI.
   - `DSPACE_URL`: URL base del API de DSpace (ej. `https://tudspace.cl/server/api`).
   - `DSPACE_EMAIL` y `DSPACE_PASSWORD`: Credenciales del usuario en DSpace con permisos de envío.
   - `DSPACE_COLLECTION_UUID`: UUID de la colección destino.

---

## Uso

Para iniciar la aplicación gráfica:

```bash
python app_gui.py
```

### Empaquetado a Ejecutable (.exe)
Si deseas compilar la aplicación para distribuirla sin requerir Python instalado:

```bash
pyinstaller Catalogador_DSpace.spec
```

El ejecutable generado se ubicará en la carpeta `dist/`.
