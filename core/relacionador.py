"""
Módulo de relaciones entre ítems en DSpace 7.
Consulta la API REST para listar tipos, colecciones e ítems,
y crea relaciones entre ellos.
"""
import requests


class RelacionadorDSpace:
    """Motor de relaciones entre ítems publicados en DSpace 7."""

    def __init__(self, dspace_url, email=None, password=None,
                 log=None, progress=None):
        self.dspace_url = dspace_url.rstrip('/')
        self.email = email
        self.password = password
        self.log = log or (lambda msg: None)
        self.progress = progress or (lambda cur, tot: None)
        self._cancelado = False
        self.session = requests.Session()
        self.token = None
        self.csrf_token = None
        self._entity_cache = {}  # id -> label

    def cancelar(self):
        self._cancelado = True

    def reset(self):
        self._cancelado = False

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    def iniciar_sesion(self):
        """Inicia sesión en DSpace. Retorna True si OK."""
        self.log(f"Conectando a {self.dspace_url}...")
        login_url = f"{self.dspace_url}/authn/login"

        self.session.post(login_url)
        csrf = self.session.cookies.get("DSPACE-XSRF-COOKIE")
        headers = {"X-XSRF-TOKEN": csrf} if csrf else {}

        resp = self.session.post(
            login_url,
            data={"user": self.email, "password": self.password},
            headers=headers,
        )
        if resp.status_code == 200:
            self.token = resp.headers.get("Authorization")
            self.csrf_token = (
                resp.headers.get("DSPACE-XSRF-TOKEN")
                or self.session.cookies.get("DSPACE-XSRF-COOKIE")
                or csrf
            )
            self.log("✅ Autenticación exitosa.")
            return True
        else:
            self.log(f"❌ Error de autenticación: {resp.status_code}")
            return False

    # ------------------------------------------------------------------
    # Lectura: Entity Types
    # ------------------------------------------------------------------

    def obtener_entity_types(self):
        """GET /api/core/entitytypes → dict {id: label}."""
        if self._entity_cache:
            return self._entity_cache
        try:
            resp = self.session.get(
                f"{self.dspace_url}/core/entitytypes",
                params={"size": 100},
            )
            data = resp.json()
            for et in data.get("_embedded", {}).get("entitytypes", []):
                self._entity_cache[et["id"]] = et["label"]
            return self._entity_cache
        except Exception as e:
            self.log(f"Error obteniendo entity types: {e}")
            return {}

    # ------------------------------------------------------------------
    # Lectura: Relationship Types
    # ------------------------------------------------------------------

    def obtener_relationship_types(self):
        """GET /api/core/relationshiptypes con nombres de entidad resueltos.
        Retorna lista de dicts con display humano.
        """
        entity_types = self.obtener_entity_types()
        try:
            resp = self.session.get(
                f"{self.dspace_url}/core/relationshiptypes",
                params={"size": 100},
            )
            data = resp.json()
            result = []
            for rt in data.get("_embedded", {}).get("relationshiptypes", []):
                left_url = rt["_links"]["leftType"]["href"]
                right_url = rt["_links"]["rightType"]["href"]
                left_id = int(left_url.rstrip('/').split('/')[-1])
                right_id = int(right_url.rstrip('/').split('/')[-1])

                left_label = entity_types.get(left_id, f"ID:{left_id}")
                right_label = entity_types.get(right_id, f"ID:{right_id}")

                # Omitir relaciones con entity type 'none'
                if left_label == "none" or right_label == "none":
                    continue

                result.append({
                    'id': rt['id'],
                    'left_type_id': left_id,
                    'right_type_id': right_id,
                    'left_label': left_label,
                    'right_label': right_label,
                    'leftward_type': rt['leftwardType'],
                    'rightward_type': rt['rightwardType'],
                    'display': f"{left_label} → {right_label}",
                })
            return result
        except Exception as e:
            self.log(f"Error obteniendo relationship types: {e}")
            return []

    # ------------------------------------------------------------------
    # Lectura: Colecciones
    # ------------------------------------------------------------------

    def obtener_colecciones(self):
        """GET /api/core/collections → lista de {uuid, name}."""
        try:
            resp = self.session.get(
                f"{self.dspace_url}/core/collections",
                params={"size": 100},
            )
            data = resp.json()
            result = []
            for col in data.get("_embedded", {}).get("collections", []):
                result.append({
                    'uuid': col['uuid'],
                    'name': col.get('name', 'Sin nombre'),
                })
            return sorted(result, key=lambda x: x['name'])
        except Exception as e:
            self.log(f"Error obteniendo colecciones: {e}")
            return []

    # ------------------------------------------------------------------
    # Lectura: Ítems de una colección (paginado)
    # ------------------------------------------------------------------

    def obtener_items_coleccion(self, collection_uuid, page=0, size=20, query=None):
        """GET /api/discover/search/objects con scope de colección.
        Retorna (items_list, total_elements, total_pages).
        """
        try:
            params = {
                "scope": collection_uuid,
                "dsoType": "ITEM",
                "page": page,
                "size": size,
            }
            if query:
                params["query"] = query

            resp = self.session.get(
                f"{self.dspace_url}/discover/search/objects",
                params=params,
            )
            data = resp.json()
            search_result = data.get("_embedded", {}).get("searchResult", {})
            objects = search_result.get("_embedded", {}).get("objects", [])
            page_info = search_result.get("page", {})

            items = []
            for obj in objects:
                indexable = obj.get("_embedded", {}).get("indexableObject", {})
                metadata = indexable.get("metadata", {})

                title_list = metadata.get("dc.title", [])
                title = title_list[0]["value"] if title_list else "Sin título"

                entity_list = metadata.get("dspace.entity.type", [])
                entity_type = entity_list[0]["value"] if entity_list else ""

                items.append({
                    'uuid': indexable.get('uuid', indexable.get('id', '')),
                    'title': title,
                    'entity_type': entity_type,
                })

            total_elements = page_info.get("totalElements", 0)
            total_pages = page_info.get("totalPages", 0)
            return items, total_elements, total_pages

        except Exception as e:
            self.log(f"Error obteniendo ítems: {e}")
            return [], 0, 0

    def obtener_uuids_busqueda(self, collection_uuid, query=None):
        """Obtiene TODOS los UUIDs de una búsqueda iterando las páginas.
        Útil para seleccionar todo masivamente sin parsear metadatos.
        """
        uuids = []
        page = 0
        try:
            while True:
                params = {
                    "scope": collection_uuid,
                    "dsoType": "ITEM",
                    "page": page,
                    "size": 100,
                }
                if query:
                    params["query"] = query

                resp = self.session.get(
                    f"{self.dspace_url}/discover/search/objects",
                    params=params,
                )
                data = resp.json()
                search_result = data.get("_embedded", {}).get("searchResult", {})
                objects = search_result.get("_embedded", {}).get("objects", [])

                if not objects:
                    break

                for obj in objects:
                    indexable = obj.get("_embedded", {}).get("indexableObject", {})
                    uuid = indexable.get('uuid', indexable.get('id'))
                    if uuid:
                        uuids.append(uuid)

                page_info = search_result.get("page", {})
                if page >= page_info.get("totalPages", 1) - 1:
                    break
                page += 1
        except Exception as e:
            self.log(f"Error obteniendo todos los UUIDs: {e}")
        return uuids

    # ------------------------------------------------------------------
    # Lectura: Relaciones existentes del destino
    # ------------------------------------------------------------------

    def obtener_items_ya_relacionados(self, destino_uuid, rel_type_id):
        """Retorna set de UUIDs ya relacionados con el destino
        para el tipo de relación dado.
        """
        ya_relacionados = set()
        try:
            page = 0
            while True:
                resp = self.session.get(
                    f"{self.dspace_url}/core/items/{destino_uuid}/relationships",
                    params={"size": 100, "page": page},
                )
                if resp.status_code != 200:
                    break

                data = resp.json()
                rels = data.get("_embedded", {}).get("relationships", [])
                if not rels:
                    break

                for rel in rels:
                    rt_url = rel.get("_links", {}).get(
                        "relationshipType", {}
                    ).get("href", "")
                    if not rt_url.endswith(f"/{rel_type_id}"):
                        continue

                    left_url = rel["_links"]["leftItem"]["href"]
                    right_url = rel["_links"]["rightItem"]["href"]
                    left_uuid = left_url.rstrip('/').split('/')[-1]
                    right_uuid = right_url.rstrip('/').split('/')[-1]

                    if left_uuid == destino_uuid:
                        ya_relacionados.add(right_uuid)
                    else:
                        ya_relacionados.add(left_uuid)

                p = data.get("page", {})
                if page >= p.get("totalPages", 1) - 1:
                    break
                page += 1

        except Exception as e:
            self.log(f"Error verificando relaciones existentes: {e}")

        return ya_relacionados

    # ------------------------------------------------------------------
    # Escritura: Crear relaciones
    # ------------------------------------------------------------------

    def crear_relaciones(self, items_origen_uuids, destino_uuid, rel_type_id):
        """POST /api/core/relationships para cada ítem origen.
        Retorna (ok_count, error_count).
        """
        self.reset()

        if not self.token:
            if not self.iniciar_sesion():
                return 0, 0

        total = len(items_origen_uuids)
        ok = 0
        errors = 0

        for i, uuid in enumerate(items_origen_uuids, 1):
            if self._cancelado:
                self.log("\n⏹ Creación de relaciones cancelada.")
                break

            self.progress(i, total)

            # left = origen, right = destino (según la definición del relType)
            body = (
                f"{self.dspace_url}/core/items/{uuid}\n"
                f"{self.dspace_url}/core/items/{destino_uuid}"
            )

            headers = {
                "Authorization": self.token,
                "X-XSRF-TOKEN": self.csrf_token,
                "Content-Type": "text/uri-list",
            }

            try:
                resp = self.session.post(
                    f"{self.dspace_url}/core/relationships",
                    params={"relationshipType": rel_type_id},
                    headers=headers,
                    data=body,
                )
                if resp.status_code in [200, 201]:
                    self.log(f"[{i}/{total}] ✅ Vinculado")
                    ok += 1
                else:
                    self.log(
                        f"[{i}/{total}] ❌ Error ({resp.status_code})"
                    )
                    errors += 1
            except Exception as e:
                self.log(f"[{i}/{total}] ❌ {e}")
                errors += 1

        self.log(f"\n{'=' * 55}")
        self.log(f"  RESULTADO: {ok} exitosos, {errors} con error")
        self.log(f"{'=' * 55}")

        return ok, errors
