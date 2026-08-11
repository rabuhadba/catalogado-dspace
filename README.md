# Catalogador e Importador DSpace 7 con OpenAI

Herramienta para catalogar colecciones fotográficas con IA (OpenAI GPT-4o-mini) y subirlas automáticamente a DSpace 7 mediante API REST.

---

## Instalación (solo la primera vez)

1. Clonar este repositorio o descargar la carpeta.
2. Crear un archivo `.env` basándose en `.env.example` y completar los datos.
3. Abrir una terminal en la carpeta del proyecto y ejecutar:

```
instalar_entorno.bat
```

Esto instalará las dependencias de Python necesarias.

---

## Requisitos previos para cada carga

Antes de empezar, asegúrate de tener:

- **Carpeta en el fileserver** con las fotos del proyecto.
- **CSV preprocesado** dentro de esa misma carpeta.
- **Datos del `.env` correctos** (API Key de OpenAI, credenciales DSpace, UUID de la colección).

---

## Paso a paso

### 1. Abrir terminal

Abrir Visual Studio Code desde la carpeta donde están los scripts. Presionar `Ctrl + Ñ` para abrir la terminal.

### 2. Ejecutar el catalogador

```
python .\catalogador_openai.py
```

El script te pedirá la **ruta de red** donde están las fotos con el CSV. Ejemplo:

```
\\10.10.20.212\nuevo-todo\Proyectos_originales\FIA-GI-V-1998-1-A-142\...
```

Copia y pega la ruta. El script:
- Copiará la carpeta completa a tu disco local (dentro de `Proyectos/`).
- Analizará cada foto con OpenAI y generará los metadatos.
- Guardará el resultado en `Catalogo_OpenAI_Completo.csv`.

> **Nota:** Si se interrumpe, puedes volver a ejecutarlo. Retoma desde donde quedó sin volver a procesar las fotos ya catalogadas.

### 3. Revisar resultado

En la carpeta `Proyectos/<nombre-proyecto>/` quedarán:
- El **CSV original** preprocesado (el que venía del fileserver).
- El **`Catalogo_OpenAI_Completo.csv`** con todas las columnas originales + las nuevas generadas por la IA (título, descripción, resumen).

Revisa que los datos generados tengan sentido antes de continuar.

### 4. Ejecutar el importador

```
python .\importador_dspace_api.py
```

El script:
- Te mostrará los proyectos disponibles para subir.
- Creará un borrador en DSpace por cada foto.
- Subirá la foto y aplicará los metadatos.
- Los ítems quedan como **borradores** en "Sus envíos" para revisión manual.

### 5. Limpieza

Al terminar la importación, el script te preguntará si deseas borrar las fotos locales y archivos temporales para liberar espacio. Solo se conservará el `Catalogo_OpenAI_Completo.csv`.

### 6. Publicar en DSpace

Entra a la interfaz web de DSpace, revisa los borradores en "Sus envíos" y publícalos.

---

## Estructura del `.env`

```
OPENAI_API_KEY=tu_llave_openai_aqui
DSPACE_URL=https://tudspace.cl/server/api
DSPACE_EMAIL=tu_usuario@institucion.cl
DSPACE_PASSWORD=tu_contrasena_aqui
DSPACE_COLLECTION_UUID=uuid-de-la-coleccion
```

---

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `catalogador_openai.py` | Copia fotos desde la red, las analiza con IA y genera el CSV de metadatos. |
| `importador_dspace_api.py` | Lee el CSV y sube fotos + metadatos a DSpace como borradores. |
| `borrar_lote_dspace.py` | Utilidad para eliminar borradores masivamente (usa `registro_subida.txt`). |
| `instalar_entorno.bat` | Instala las dependencias de Python. |
| `.env` | Configuración local (no se sube a Git). |
