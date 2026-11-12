# Especificación de Diseño: Módulo Carga SIGES

- **Fecha:** 2026-11-12
- **Estado:** Validado con el usuario
- **Módulo:** Carga SIGES (`core/cargador_siges.py`, `CargaSigesFrame` en `app_gui.py`)
- **Destino:** Colección DSpace 7 SIGES (`ab25c4c6-e0f6-4505-8623-b23fa0566bf3` / Handle `20.500.11944/226725`)

---

## 1. Resumen Ejecutivo
El sistema actualmente cuenta con módulos para la catalogación y exportación de fotografías patrimoniales con IA y para relacionar fotografías con proyectos.
El nuevo módulo **"Carga SIGES"** permite cargar periódicamente (ej. mensual) un archivo CSV con la estructura de iniciativas FIA (`carga_siges.csv`), inspeccionar y validar visualmente los datos mediante una interfaz interactiva tipo ficha (sin IA ni fotos), y subir los ítems como metadatos puros directamente a la colección privada **SIGES** en DSpace 7, depositándolos de inmediato para generar su Handle institucional.

Incluye adicionalmente una función de **prueba de carga individual** para verificar en vivo un único ítem antes de ejecutar la ingestión masiva.

---

## 2. Arquitectura del Sistema

```
app_gui.py (CatalogadorApp)
 ├── Sidebar Navigation -> [📋  Carga SIGES]
 └── CargaSigesFrame (CustomTkinter ScrollableFrame)
      ├── Tarjeta 1: Carga de CSV & Diagnóstico / Validación
      ├── Tarjeta 2: Inspector / Vista Previa de Ficha de Proyecto
      │    └── Controles: [◀] [N de Total] [▶] | Desplegable de búsqueda
      └── Tarjeta 3: Acciones de Ingestión
           ├── [🧪 Cargar solo este proyecto (Prueba)]
           ├── [🚀 Iniciar Carga Masiva]
           ├── [⏹ Detener]
           └── Barra de progreso e indicadores

core/cargador_siges.py (CargadorSiges)
 ├── Lectura robusta CSV (delimitador automático ; o ,, codificación utf-8/latin1)
 ├── Normalización de metadatos y listas multivaluadas (||)
 ├── Sesión REST DSpace 7 (CSRF, JWT token, auto-relogin)
 ├── Ingestión individual:
 │    1. POST /submission/workspaceitems?owningCollection={uuid}
 │    2. PATCH /core/items/{item_uuid} (metadata batch)
 │    3. POST /workflow/workflowitems (text/uri-list -> publicación directa con Handle)
 └── Registro de bitácora (registro_carga_siges_YYYYMMDD_HHMMSS.csv)
```

---

## 3. Esquema y Mapeo de Metadatos

A partir de la estructura analizada de `carga_siges.csv` (33 columnas), el mapeo hacia DSpace 7 se define de la siguiente manera:

| Columna CSV | Campo DSpace | Tipo | Tratamiento |
|---|---|---|---|
| `Id` | *(Ninguno)* | Ignorado | Identificador interno de fila en CSV |
| `dc.title` | `dc.title` | Texto | Requerido para crear ítem |
| `dc.date.issued` | `dc.date.issued` | Fecha/Año | Año de la iniciativa |
| `dc.description.abstract` | `dc.description.abstract` | Texto largo | Resumen descriptivo de la iniciativa |
| *(Constante)* | `dc.type` | Texto | Se inyecta `"Proyectos"` por defecto |
| `fia.iniciativa` | `fia.iniciativa` | Texto | Código de iniciativa (ej. `COC-2026-0001`) |
| `fia.estado` | `fia.estado` | Texto | Estado de la iniciativa |
| `fia.supervisor` | `fia.supervisor` | Texto | Nombre de supervisor |
| `fia.clasificacionlocal` | `fia.clasificacionlocal` | Texto | Código de clasificación local |
| `fia.proyecto.inicio` | `fia.proyecto.inicio` | Fecha | Fecha inicio (DD-MM-YYYY) |
| `fia.proyecto.fin` | `fia.proyecto.fin` | Fecha | Fecha fin (DD-MM-YYYY) |
| `fia.ejecutor` | `fia.ejecutor` | Texto | Organización ejecutora |
| `fia.region` | `fia.region` | Texto | Región principal |
| `fia.participacion` | `fia.participacion` | Texto | Región de participación |
| `fia.ejecucion` | `fia.ejecucion` | Texto | Región de ejecución |
| `fia.sector` | `fia.sector` | Texto | Sector económico/agrícola |
| `fia.subsector` | `fia.subsector` | Texto | Subsector |
| `fia.rubro` | `fia.rubro` | Texto | Rubro específico |
| `fia.especie` | `fia.especie` | Texto | Especie animal o vegetal |
| `fia.convocatoria` | `fia.convocatoria` | Texto | Nombre de la convocatoria |
| `fia.coordinador-principal` | `fia.coordinador-principal` | Texto | Nombre de persona |
| `fia.coordinador-alterno` | `fia.coordinador-alterno` | Texto | Nombre de persona |
| `fia.asociado` | `fia.asociado` | Texto | Entidades asociadas |
| `fia.objetivo-general` | `fia.objetivo-general` | Texto largo | Objetivo general |
| `fia.objetivo-especifico` | `fia.objetivo-especifico` | Texto largo | Objetivos específicos |
| `fia.equipo-tecnico` | `fia.equipo-tecnico` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.beneficiario-directo` | `fia.beneficiario-directo` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.participante-individual` | `fia.participante-individual` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.consultor` | `fia.consultor` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.ejecutor-tecnico` | `fia.ejecutor-tecnico` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.institucion-visitada` | `fia.institucion-visitada` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.participante-individual-consultoría` | `fia.participante-individual-consultoría` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.expositor` | `fia.expositor` | Multivaluado | Separado por `\|\|` en múltiples valores |
| `fia.tema` | `fia.tema` | Multivaluado | Separado por `\|\|` en múltiples valores |

---

## 4. Componentes y Flujo de Interfaz

### 4.1. Tarjeta 1: Carga y Validación
- Botón **"📂 Seleccionar CSV SIGES"**: Diálogo para abrir `.csv`.
- Indicadores informativos:
  - Nombre del archivo y tamaño.
  - Total de registros leídos.
  - Resumen de integridad: Registros válidos (con `fia.iniciativa` y `dc.title`) vs. registros con advertencias.
  - Información de conexión: Servidor DSpace configurado y UUID de la colección SIGES (`ab25c4c6-e0f6-4505-8623-b23fa0566bf3`).

### 4.2. Tarjeta 2: Inspector / Vista Previa de Ficha
- Barra de navegación:
  - Botones `◀ Anterior` y `Siguiente ▶`.
  - Etiqueta de posición `[ X de N ]`.
  - Desplegable de salto rápido con búsqueda para ir a cualquier iniciativa por código o título.
- Contenedor con estética dark card (`#161626` / `#10101e`):
  - **Cabecera destacada:** Código de Iniciativa (`fia.iniciativa`) en tamaño prominente y color de acento, estado (`fia.estado`), año y tipo.
  - **Bloque Dublin Core:** Título (`dc.title`), Resumen (`dc.description.abstract`).
  - **Bloque Proyecto FIA:** Convocatoria, Supervisor, Ejecutor, Fechas de vigencia, Regiones.
  - **Bloque Objetivos:** Objetivo General y Específico.
  - **Bloque Participantes & Equipos:** Píldoras visuales (`🏷️ Nombre`) para los integrantes de `fia.equipo-tecnico`, consultores y beneficiarios.
  - **Bloque Clasificación Agropecuaria:** Sector, Subsector, Rubro y píldoras para `fia.tema`.

### 4.3. Tarjeta 3: Acciones de Subida
- Botón **`🧪 Cargar solo este proyecto (Prueba)`**:
  - Toma el ítem visible actualmente en la ficha.
  - Llama a `cargador.cargar_un_item(item)`.
  - Si es exitoso, abre un diálogo de información con el Handle generado (ej. `https://bibliotecadigital.fia.cl/handle/20.500.11944/XXXXXX`) y botón para copiarlo o abrirlo en el navegador.
- Botón **`🚀 Iniciar Carga Masiva`**:
  - Diálogo de confirmación con el total de iniciativas a ingresar.
  - Barra de progreso `[X / N] procesados (Z%)`.
  - Registro de mensajes en la consola de log común del sistema.
- Botón **`⏹ Detener`**:
  - Cancela limpiamente el hilo de ejecución sin corromper el estado.

---

## 5. Módulo de Red y Protocolo DSpace 7 (`CargadorSiges`)

### 5.1. Autenticación y Sesión
- Endpoint de inicio de sesión: `POST /authn/login` (recupera cookie `DSPACE-XSRF-COOKIE` y token en cabecera `Authorization`).
- Detección de token expirado con reintento automático.

### 5.2. Ciclo de Vida de Ingestión por Ítem
1. **Crear WorkspaceItem:**
   `POST /submission/workspaceitems?owningCollection=ab25c4c6-e0f6-4505-8623-b23fa0566bf3`
   Retorna `ws_id` y `item_uuid`.
2. **Aplicar Metadatos:**
   `PATCH /core/items/{item_uuid}`
   Operaciones JSON Patch:
   ```json
   [
     {"op": "add", "path": "/metadata/dc.title/-", "value": {"value": "..."}},
     {"op": "add", "path": "/metadata/dc.type/-", "value": {"value": "Proyectos"}},
     {"op": "add", "path": "/metadata/fia.iniciativa/-", "value": {"value": "COC-2026-0001"}},
     ...
   ]
   ```
3. **Depositar y Publicar Ítem:**
   `POST /workflow/workflowitems`
   Headers:
   - `Content-Type: text/uri-list`
   - `Authorization: Bearer <token>`
   - `X-XSRF-TOKEN: <csrf_token>`
   Body:
   `https://bibliotecadigital.fia.cl/server/api/submission/workspaceitems/{ws_id}`
   Retorna el objeto publicado con su `handle` definitivo.

### 5.3. Bitácora de Auditoría
Se escribe en disco un archivo CSV con nombre:
`registro_carga_siges_YYYYMMDD_HHMMSS.csv`
Columnas:
`Timestamp, Fila_CSV, Iniciativa, Titulo, Item_UUID, Handle, Estado, Detalle`

---

## 6. Pruebas y Criterios de Aceptación
1. **Lectura de CSV:** Cargar `carga_siges.csv` (431 filas) en menos de 1 segundo sin errores de delimitador o codificación.
2. **Ficha Interactiva:** Navegar entre registros observando la correcta división de píldoras multivaluadas (`||`).
3. **Prueba de Ítem Individual:** Presionar `🧪 Cargar solo este proyecto (Prueba)` y verificar que DSpace devuelve HTTP 201/200 con un Handle accesible.
4. **Carga Masiva:** Iniciar carga, detener a voluntad con `⏹ Detener`, y revisar que la bitácora contiene los UUIDs y Handles de los ítems creados.
5. **No Regresión:** Los módulos existentes de *Proyecto*, *Catalogar*, *Exportar* y *Relaciones* continúan funcionando intactos.
