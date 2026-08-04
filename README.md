# Catalogador Automático DSpace con OpenAI 📸🤖

Esta herramienta automatiza la catalogación masiva de colecciones fotográficas utilizando inteligencia artificial (OpenAI GPT-4o-mini) y empaqueta los resultados en el formato **Simple Archive Format (SAF)** oficial, dejándolos listos para ser importados a repositorios institucionales [DSpace](https://dspace.lyrasis.org/).

El script procesa lotes de imágenes, analiza su contenido visual y contexto, y genera metadatos estructurados en formato CSV. Luego, utiliza una versión nativa de `SAFBuilder` (incluida) para transformar ese CSV y las imágenes en los directorios listos para DSpace.

---

## 📦 Requisitos Previos

Solo necesitas tener instalado:
- **Python 3.8+** (Asegúrate de agregar Python a tu variable PATH al instalarlo).
- No necesitas instalar Java globalmente (el instalador se encargará de esto).

---

## 🚀 Instalación y Configuración (Solo la primera vez)

1. **Clona o descarga** este repositorio en tu PC.
2. Haz doble clic en el archivo `instalar_entorno.bat` (solo disponible para Windows). Este script mágico se encargará de:
   - Instalar las dependencias necesarias de Python (pandas, openai, dotenv).
   - Descargar de forma transparente e instalar un entorno de **Java Portable** localmente para ejecutar SAFBuilder sin modificar la configuración de tu PC.
3. Copia el archivo `.env.example` y renómbralo a `.env`.
4. Abre `.env` e inserta tu llave de API de OpenAI:
   ```env
   OPENAI_API_KEY=sk-proj-tu-llave-aqui...
   ```

---

## 🛠 Uso de la Herramienta

### 1. Preparar las Entradas
El script buscará automáticamente la metadata base o las referencias de imágenes.
Si estás usando una ruta de red corporativa (definida en la variable `CARPETA_RED` dentro de `catalogador_openai.py`), el script copiará inteligentemente las fotos a una carpeta local `Fotos/` para trabajar de forma más rápida.

### 2. Ejecutar la Catalogación
Desde una terminal (Powershell o CMD), ejecuta:

```bash
python catalogador_openai.py
```

### 3. ¿Qué ocurre internamente?
1. **Reanudar Progreso:** Si el script se detiene, al volver a iniciarlo detectará los registros ya catalogados y continuará donde lo dejó.
2. **Análisis OpenAI:** La IA analizará la imagen visualmente basándose en un prompt estricto y generará el título alternativo y resúmenes sin ambigüedades.
3. **Formateo SAFBuilder:** El CSV generado es transformado por código al esquema de columnas que exige la herramienta oficial de SAFBuilder.
4. **Empaquetado:** El script invocará automáticamente al ejecutable de SAFBuilder (construido en Java) para crear los paquetes finales.

---

## 📂 Salida Esperada

Una vez que el proceso finaliza, se creará una carpeta llamada **`SimpleArchiveFormat/`** al nivel de tu directorio principal. 

Esta carpeta contiene subdirectorios numerados (`item_000`, `item_001`, etc.), los cuales albergan:
- Los archivos `.jpg` de las fotografías.
- El archivo `dublin_core.xml` con los metadatos analizados.
- El archivo `contents` con la declaración del material digital.

**¡La carpeta `SimpleArchiveFormat/` está lista para ser importada directamente a tu repositorio DSpace vía línea de comandos o interfaz web!**

---

## 🔒 Privacidad y Seguridad
- **NO** subas el archivo `.env` a repositorios públicos. Este proyecto incluye un `.gitignore` preparado para evitar que subas credenciales, la carpeta pesada del JDK de Java o grandes lotes de imágenes, manteniendo tu entorno limpio.
