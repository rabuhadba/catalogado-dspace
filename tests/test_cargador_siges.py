import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import requests
from core.cargador_siges import (
    CargadorSiges,
    DEFAULT_SIGES_COLLECTION_UUID,
    MULTIVALUE_FIELDS,
    leer_iniciativas_exitosas_de_bitacora,
)


class TestCargadorSigesParsing(unittest.TestCase):
    def setUp(self):
        self.cargador = CargadorSiges(
            "https://fake-dspace.org/server/api",
            "test@user.cl",
            "pass123",
            collection_uuid=DEFAULT_SIGES_COLLECTION_UUID
        )

    def test_leer_csv_semicolon_and_multivalue(self):
        csv_content = (
            "Id;fia.iniciativa;dc.title;dc.date.issued;fia.equipo-tecnico;fia.tema\n"
            "1;COC-2026-0001;Proyecto Apicola;2026;Persona Uno||Persona Dos;Sanidad||Apicultura\n"
            "2;COC-2026-0002;Proyecto Riego;2026;Persona Tres;Riego\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            items, stats = self.cargador.leer_csv(temp_path)
            self.assertEqual(len(items), 2)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["validos"], 2)
            self.assertEqual(stats["advertencias"], 0)
            self.assertEqual(items[0]["fia.iniciativa"], "COC-2026-0001")
            self.assertEqual(items[0]["dc.title"], "Proyecto Apicola")
            self.assertEqual(items[0]["_fila"], 2)
            self.assertTrue(items[0]["_es_valido"])
            self.assertEqual(items[1]["_fila"], 3)
            self.assertTrue(items[1]["_es_valido"])

            # Check normalized metadata structure for DSpace
            metadata = self.cargador.preparar_metadatos_dspace(items[0])
            self.assertEqual(metadata["dc.type"], [{"value": "Proyectos"}])
            self.assertNotIn("Id", metadata)
            self.assertNotIn("id", metadata)
            self.assertNotIn("_fila", metadata)
            self.assertNotIn("_es_valido", metadata)
            self.assertEqual(len(metadata["fia.equipo-tecnico"]), 2)
            self.assertEqual(metadata["fia.equipo-tecnico"][0]["value"], "Persona Uno")
            self.assertEqual(metadata["fia.equipo-tecnico"][1]["value"], "Persona Dos")
            self.assertEqual(len(metadata["fia.tema"]), 2)
            self.assertEqual(metadata["fia.tema"][0]["value"], "Sanidad")
            self.assertEqual(metadata["fia.tema"][1]["value"], "Apicultura")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_leer_csv_invalid_row(self):
        csv_content = (
            "Id;fia.iniciativa;dc.title;dc.date.issued\n"
            "1;;Titulo sin iniciativa;2026\n"
            "2;COC-2026-0003;;2026\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8") as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            items, stats = self.cargador.leer_csv(temp_path)
            self.assertEqual(stats["total"], 2)
            self.assertEqual(stats["validos"], 0)
            self.assertEqual(stats["advertencias"], 2)
            self.assertFalse(items[0]["_es_valido"])
            self.assertFalse(items[1]["_es_valido"])
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_preparar_metadatos_multivalue_pipe_space_pipe(self):
        item = {
            "_fila": 2,
            "_es_valido": True,
            "id": "100",
            "dc.title": "Proyecto con pipes espaciados",
            "fia.consultor": "Consultor A | | Consultor B || Consultor C",
            "fia.beneficiario-directo": "Beneficiario 1||Beneficiario 2"
        }
        meta = self.cargador.preparar_metadatos_dspace(item)
        self.assertEqual(meta["dc.type"], [{"value": "Proyectos"}])
        self.assertEqual(meta["dc.title"], [{"value": "Proyecto con pipes espaciados"}])
        self.assertEqual(
            meta["fia.consultor"],
            [{"value": "Consultor A"}, {"value": "Consultor B"}, {"value": "Consultor C"}]
        )
        self.assertEqual(
            meta["fia.beneficiario-directo"],
            [{"value": "Beneficiario 1"}, {"value": "Beneficiario 2"}]
        )

    def test_preparar_metadatos_field_alias_normalization(self):
        item = {
            "dc.title": "Proyecto con columna con tilde",
            "fia.participante-individual-consultoría": "Juan Pérez || María Soto",
            "\ufeffId": "500",
        }
        meta = self.cargador.preparar_metadatos_dspace(item)
        # Debe haberse mapeado a 'fia.participante-individual-consultoria' (sin tilde)
        self.assertNotIn("fia.participante-individual-consultoría", meta)
        self.assertIn("fia.participante-individual-consultoria", meta)
        self.assertEqual(
            meta["fia.participante-individual-consultoria"],
            [{"value": "Juan Pérez"}, {"value": "María Soto"}]
        )
        self.assertNotIn("\ufeffId", meta)
        self.assertNotIn("Id", meta)

    def test_iniciar_sesion_success(self):
        mock_session = MagicMock()
        mock_login_resp = MagicMock(status_code=200)
        mock_login_resp.headers = {
            "Authorization": "Bearer mock-token-123",
            "DSPACE-XSRF-TOKEN": "csrf-token-abc"
        }
        mock_session.post.return_value = mock_login_resp
        mock_session.cookies.get.return_value = "csrf-cookie-xyz"

        with patch("requests.Session", return_value=mock_session):
            ok = self.cargador.iniciar_sesion()
            self.assertTrue(ok)
            self.assertEqual(self.cargador.token, "Bearer mock-token-123")
            self.assertEqual(self.cargador.csrf_token, "csrf-token-abc")

    def test_cargar_un_item_success(self):
        self.cargador.token = "Bearer test-token"
        self.cargador.csrf_token = "csrf-test"
        mock_session = MagicMock()
        self.cargador.session = mock_session

        # 1. ws item post response
        resp_ws = MagicMock(status_code=201)
        resp_ws.json.return_value = {
            "id": 999,
            "_embedded": {"item": {"id": "item-uuid-1234"}}
        }

        # 2. patch response
        resp_patch = MagicMock(status_code=200)

        # 3. workflow item response
        resp_wf = MagicMock(status_code=201)
        resp_wf.json.return_value = {
            "_embedded": {"item": {"id": "item-uuid-1234", "handle": "20.500.11944/9999"}}
        }

        mock_session.post.side_effect = [resp_ws, resp_wf]
        mock_session.patch.return_value = resp_patch

        item = {
            "_fila": 2,
            "_es_valido": True,
            "fia.iniciativa": "COC-2026-0001",
            "dc.title": "Proyecto Test Ingest"
        }

        ok, handle_url, msg = self.cargador.cargar_un_item(item)
        self.assertTrue(ok)
        self.assertEqual(handle_url, "https://bibliotecadigital.fia.cl/handle/20.500.11944/9999")
        self.assertIn("Publicado exitosamente", msg)

    def test_preparar_metadatos_non_string_resiliency(self):
        item = {
            "dc.title": "Proyecto con tipos no string",
            "dc.date.issued": 2026,
            "fia.clasificacionlocal": None,
            "fia.equipo-tecnico": 12345,
            "_fila": 2
        }
        meta = self.cargador.preparar_metadatos_dspace(item)
        self.assertEqual(meta["dc.date.issued"], [{"value": "2026"}])
        self.assertEqual(meta["fia.equipo-tecnico"], [{"value": "12345"}])
        self.assertNotIn("fia.clasificacionlocal", meta)

    def test_cargar_un_item_patch_metadata_failure_aborts_deposit(self):
        self.cargador.token = "Bearer test-token"
        self.cargador.csrf_token = "csrf-test"
        mock_session = MagicMock()
        self.cargador.session = mock_session

        # 1. ws item post response
        resp_ws = MagicMock(status_code=201)
        resp_ws.json.return_value = {
            "id": 999,
            "_embedded": {"item": {"id": "item-uuid-1234"}}
        }

        # 2. patch failure response (e.g. 422 Unprocessable Entity)
        resp_patch = MagicMock(status_code=422)
        resp_patch.text = "Metadata schema validation failed"

        mock_session.post.return_value = resp_ws
        mock_session.patch.return_value = resp_patch

        item = {
            "_fila": 2,
            "_es_valido": True,
            "fia.iniciativa": "COC-2026-0001",
            "dc.title": "Proyecto Test Ingest"
        }

        ok, handle_url, msg = self.cargador.cargar_un_item(item)
        self.assertFalse(ok)
        self.assertEqual(handle_url, "")
        self.assertIn("Error aplicando metadatos: HTTP 422", msg)
        # Verify workflow deposit was NOT called (mock_session.post called only once for ws)
        self.assertEqual(mock_session.post.call_count, 1)

    def test_cargar_lote_mock(self):
        items = [
            {"_fila": 2, "fia.iniciativa": "COC-2026-0001", "dc.title": "Proyecto 1"},
            {"_fila": 3, "fia.iniciativa": "COC-2026-0002", "dc.title": "Proyecto 2 (Falla)"},
            {"_fila": 4, "fia.iniciativa": "COC-2026-0003", "dc.title": "Proyecto 3"}
        ]
        progress_calls = []
        self.cargador.progress = lambda cur, tot: progress_calls.append((cur, tot))

        def fake_cargar_un_item(item, collection_uuid=None):
            if item["fia.iniciativa"] == "COC-2026-0002":
                return False, "", "Error de metadatos"
            return True, f"https://bibliotecadigital.fia.cl/handle/20.500.11944/{item['_fila']}", "Publicado exitosamente."

        self.cargador.cargar_un_item = fake_cargar_un_item

        with tempfile.TemporaryDirectory() as tmpdir:
            ok, err, log_path = self.cargador.cargar_lote(items, output_dir=tmpdir)
            self.assertEqual(ok, 2)
            self.assertEqual(err, 1)
            self.assertTrue(os.path.exists(log_path))
            self.assertEqual(progress_calls, [(1, 3), (2, 3), (3, 3)])

            with open(log_path, "r", encoding="utf-8-sig") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            # Header verification
            self.assertEqual(
                lines[0],
                "Timestamp;Fila;Iniciativa;Titulo;Handle_o_UUID;Estado;Detalle"
            )
            self.assertEqual(len(lines), 4)

            # Item 1 verification
            self.assertIn(";2;COC-2026-0001;Proyecto 1;https://bibliotecadigital.fia.cl/handle/20.500.11944/2;EXITOSO;Publicado exitosamente.", lines[1])
            # Item 2 verification
            self.assertIn(";3;COC-2026-0002;Proyecto 2 (Falla);;ERROR;Error de metadatos", lines[2])
            # Item 3 verification
            self.assertIn(";4;COC-2026-0003;Proyecto 3;https://bibliotecadigital.fia.cl/handle/20.500.11944/4;EXITOSO;Publicado exitosamente.", lines[3])

    def test_cargar_lote_cancellation(self):
        items = [
            {"_fila": 2, "fia.iniciativa": "COC-2026-0001", "dc.title": "Proyecto 1"},
            {"_fila": 3, "fia.iniciativa": "COC-2026-0002", "dc.title": "Proyecto 2"},
            {"_fila": 4, "fia.iniciativa": "COC-2026-0003", "dc.title": "Proyecto 3"}
        ]

        def fake_cargar_un_item(item, collection_uuid=None):
            # Cancel immediately after first item finishes
            if item["fia.iniciativa"] == "COC-2026-0001":
                self.cargador.cancelar()
            return True, f"https://bibliotecadigital.fia.cl/handle/20.500.11944/{item['_fila']}", "Publicado exitosamente."

        self.cargador.cargar_un_item = fake_cargar_un_item

        with tempfile.TemporaryDirectory() as tmpdir:
            ok, err, log_path = self.cargador.cargar_lote(items, output_dir=tmpdir)
            # Only the first item should have been processed
            self.assertEqual(ok, 1)
            self.assertEqual(err, 0)
            self.assertTrue(os.path.exists(log_path))

            with open(log_path, "r", encoding="utf-8-sig") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]

            # Header + 1 item row = 2 lines
            self.assertEqual(len(lines), 2)
            self.assertIn(";2;COC-2026-0001;Proyecto 1;", lines[1])
            self.assertNotIn("COC-2026-0002", "\n".join(lines))

    def test_cargar_lote_omitir_iniciativas(self):
        items = [
            {"_fila": 2, "fia.iniciativa": "COC-2026-0001", "dc.title": "Proyecto 1 (Omitido)"},
            {"_fila": 3, "fia.iniciativa": "COC-2026-0002", "dc.title": "Proyecto 2 (Cargado)"},
        ]
        cargar_calls = []

        def fake_cargar_un_item(item, collection_uuid=None):
            cargar_calls.append(item["fia.iniciativa"])
            return True, "https://bibliotecadigital.fia.cl/handle/20.500.11944/test", "Publicado."

        self.cargador.cargar_un_item = fake_cargar_un_item

        with tempfile.TemporaryDirectory() as tmpdir:
            ok, err, log_path = self.cargador.cargar_lote(
                items, output_dir=tmpdir, omitir_iniciativas={"COC-2026-0001"}
            )
            # Solo el ítem 2 debió ser cargado; el 1 debió ser omitido
            self.assertEqual(ok, 1)
            self.assertEqual(err, 0)
            self.assertEqual(cargar_calls, ["COC-2026-0002"])

            with open(log_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.assertIn(";2;COC-2026-0001;Proyecto 1 (Omitido);;OMITIDO;Subido previamente en sesión", content)
            self.assertIn(";3;COC-2026-0002;Proyecto 2 (Cargado);https://bibliotecadigital.fia.cl/handle/20.500.11944/test;EXITOSO;Publicado.", content)

    def test_leer_carga_siges_real_si_existe(self):
        csv_path = "carga_siges.csv"
        if not os.path.exists(csv_path):
            self.skipTest(f"{csv_path} no encontrado en la raíz del repositorio")
        items, stats = self.cargador.leer_csv(csv_path)
        self.assertGreater(len(items), 400)
        self.assertGreater(stats["validos"], 400)
        self.assertEqual(items[0]["fia.iniciativa"], "COC-2026-0001")

    def test_leer_iniciativas_exitosas_de_bitacora(self):
        log_content = (
            "Timestamp;Fila;Iniciativa;Titulo;Handle_o_UUID;Estado;Detalle\n"
            "2026-11-12 15:12:51;2;COC-2026-0001;Proyecto 1;https://bibliotecadigital.fia.cl/handle/20.500.11944/241065;EXITOSO;Publicado exitosamente.\n"
            "2026-11-12 15:13:32;3;COC-2026-0002;Proyecto 2;;ERROR;Read timed out\n"
            "2026-11-12 15:13:49;4;COC-2026-0003;Proyecto 3;https://bibliotecadigital.fia.cl/handle/20.500.11944/241067;EXITOSO;Publicado exitosamente.\n"
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv", encoding="utf-8-sig") as f:
            f.write(log_content)
            temp_path = f.name

        try:
            exitosos = leer_iniciativas_exitosas_de_bitacora(temp_path)
            self.assertEqual(len(exitosos), 2)
            self.assertIn("COC-2026-0001", exitosos)
            self.assertIn("COC-2026-0003", exitosos)
            self.assertNotIn("COC-2026-0002", exitosos)
            self.assertEqual(exitosos["COC-2026-0001"], "https://bibliotecadigital.fia.cl/handle/20.500.11944/241065")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)



if __name__ == "__main__":
    unittest.main()
