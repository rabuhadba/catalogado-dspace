"""
Catalogador DSpace — Interfaz Gráfica Unificada
Combina catalogador_openai.py, importador_dspace_api.py y creador_saf.py
en una sola ventana con CustomTkinter.
"""
import os
import sys
import re
import threading
import datetime
import customtkinter as ctk
import pandas as pd
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv, set_key

# Agregar carpeta raíz al path para importar core/ y manejar ejecutable congelado
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from core.catalogador import (
    Catalogador,
    cargar_prompt_sistema,
    guardar_prompt_sistema,
    PROMPT_SISTEMA_DEFAULT,
)
from core.importador import ImportadorDSpace
from core.saf_builder import SAFBuilder
from core.relacionador import RelacionadorDSpace

# ══════════════════════════════════════════════════════════════
# Constantes de diseño
# ══════════════════════════════════════════════════════════════
ENV_PATH = os.path.join(ROOT_DIR, ".env")

SIDEBAR_COLOR = "#1a1a2e"
SIDEBAR_HOVER = "#16213e"
SIDEBAR_ACTIVE = "#0f3460"
ACCENT = "#00d4aa"
ACCENT_HOVER = "#00b894"
ACCENT_RED = "#e94560"
CARD_BG = "#2a2a3e"
FONT_FAMILY = "Segoe UI"

# ══════════════════════════════════════════════════════════════
# Widget auxiliar: Consola de Log
# ══════════════════════════════════════════════════════════════

class LogConsole(ctk.CTkFrame):
    """Panel inferior con consola de log en tiempo real, colapsable y con redimensionamiento por arrastre (drag-to-resize)."""

    def __init__(self, parent, height=160, **kwargs):
        super().__init__(parent, fg_color="#0d0d1a", corner_radius=8, height=height, **kwargs)
        self._current_height = height
        self._is_collapsed = False
        self._drag_start_y = 0
        self._drag_start_h = height
        self.pack_propagate(False)

        # ── Barra superior de arrastre (Grip / Splitter) ──
        self.drag_bar = ctk.CTkFrame(self, fg_color="#18182a", height=8, corner_radius=4, cursor="size_ns")
        self.drag_bar.pack(fill="x", padx=15, pady=(2, 0))

        # Indicador visual central de agarre
        self.grip_indicator = ctk.CTkLabel(
            self.drag_bar, text="━━━━━", font=(FONT_FAMILY, 7), text_color="#555",
            cursor="size_ns", height=8,
        )
        self.grip_indicator.pack(anchor="center")

        # Efecto hover en la barra de agarre
        def _on_enter(e):
            self.drag_bar.configure(fg_color="#2a2a44")
            self.grip_indicator.configure(text_color=ACCENT)

        def _on_leave(e):
            self.drag_bar.configure(fg_color="#18182a")
            self.grip_indicator.configure(text_color="#555")

        for w in [self.drag_bar, self.grip_indicator]:
            w.bind("<Enter>", _on_enter)
            w.bind("<Leave>", _on_leave)
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)

        # ── Cabecera de la consola ──
        self.header = ctk.CTkFrame(self, fg_color="transparent", height=28, cursor="size_ns")
        self.header.pack(fill="x", padx=8, pady=(2, 2))
        self.header.bind("<ButtonPress-1>", self._on_drag_start)
        self.header.bind("<B1-Motion>", self._on_drag_motion)

        # Botón Minimizar / Expandir a la izquierda
        self.btn_toggle = ctk.CTkButton(
            self.header, text="🔽 Minimizar", width=85, height=24,
            font=(FONT_FAMILY, 11, "bold"), fg_color="#222235", hover_color="#333348",
            command=self.toggle_collapse,
        )
        self.btn_toggle.pack(side="left", padx=(0, 8))

        self.lbl_title = ctk.CTkLabel(
            self.header, text="📋  Consola de Log",
            font=(FONT_FAMILY, 12, "bold"), text_color="#888",
            cursor="size_ns",
        )
        self.lbl_title.pack(side="left")
        self.lbl_title.bind("<ButtonPress-1>", self._on_drag_start)
        self.lbl_title.bind("<B1-Motion>", self._on_drag_motion)

        self.lbl_hint = ctk.CTkLabel(
            self.header, text="(arrastra el borde para ajustar altura)",
            font=(FONT_FAMILY, 9), text_color="#444",
            cursor="size_ns",
        )
        self.lbl_hint.pack(side="left", padx=(6, 0))
        self.lbl_hint.bind("<ButtonPress-1>", self._on_drag_start)
        self.lbl_hint.bind("<B1-Motion>", self._on_drag_motion)

        # Botón Limpiar a la derecha
        self.btn_limpiar = ctk.CTkButton(
            self.header, text="Limpiar", width=60, height=24,
            font=(FONT_FAMILY, 11), fg_color="#333",
            hover_color="#444", command=self.limpiar,
        )
        self.btn_limpiar.pack(side="right")

        # ── Cuadro de texto del log ──
        self.textbox = ctk.CTkTextbox(
            self, font=("Consolas", 11), fg_color="#0d0d1a",
            text_color="#c0c0c0", corner_radius=0, wrap="word",
            activate_scrollbars=True,
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(2, 6))
        self.textbox.configure(state="disabled")

    def _on_drag_start(self, event):
        self._drag_start_y = event.y_root
        self._drag_start_h = self.winfo_height() if not self._is_collapsed else self._current_height

    def _on_drag_motion(self, event):
        delta = self._drag_start_y - event.y_root
        new_h = max(55, min(550, self._drag_start_h + delta))
        if self._is_collapsed and new_h > 65:
            self._uncollapse(restore_h=new_h)
            return
        self._current_height = new_h
        self.configure(height=new_h)

    def _uncollapse(self, restore_h=None):
        h = restore_h or self._current_height
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(2, 6))
        self.configure(height=h)
        self.btn_toggle.configure(text="🔽 Minimizar", fg_color="#222235", text_color="#fff")
        self._is_collapsed = False

    def toggle_collapse(self):
        if not self._is_collapsed:
            # Minimizar consola
            self.textbox.pack_forget()
            self.configure(height=38)
            self.btn_toggle.configure(text="🔼 Expandir", fg_color=ACCENT, text_color="#000")
            self._is_collapsed = True
        else:
            # Restaurar consola
            self._uncollapse()

    def escribir(self, mensaje):
        """Agrega un mensaje a la consola (thread-safe)."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"[{timestamp}] {mensaje}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def limpiar(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")


# ══════════════════════════════════════════════════════════════
# Configuración y Tarifas de Modelos OpenAI
# ══════════════════════════════════════════════════════════════

MODEL_PRICING = {
    # Nuevos modelos GPT-6 (Astra, Sol, Luna)
    "gpt-6-astra": (10.00, 50.00),
    "gpt-6-sol": (2.00, 10.00),
    "gpt-6-luna": (0.10, 0.50),
    # Familia GPT-4o
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # Modelos de razonamiento O1
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
}

def format_model_choice(mid):
    mid_clean = str(mid).strip()
    if mid_clean in MODEL_PRICING:
        inp, out = MODEL_PRICING[mid_clean]
        return f"{mid_clean} — ${inp:.2f} in / ${out:.2f} out"
    return mid_clean

def parse_model_choice(text):
    if " — " in text:
        return text.split(" — ")[0].strip()
    return text.strip()


# ══════════════════════════════════════════════════════════════
# Frame: Ajustes
# ══════════════════════════════════════════════════════════════

class AjustesFrame(ctk.CTkScrollableFrame):
    """Sección de configuración (.env)."""

    def __init__(self, parent, log_fn, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.campos = {}
        self._crear_ui()
        self._cargar_env()

    def _crear_ui(self):
        # Título
        ctk.CTkLabel(
            self, text="⚙️  Ajustes de Configuración",
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            self, text="Configura tus credenciales y conexiones. Se guardan en el archivo .env",
            font=(FONT_FAMILY, 13), text_color="#888",
        ).pack(anchor="w", padx=20, pady=(0, 20))

        # ── OpenAI ──
        self._seccion("🔑  OpenAI")
        self._campo("OPENAI_API_KEY", "API Key de OpenAI", show="•")

        # Modelo de IA
        row_mod = ctk.CTkFrame(self._current_section_frame, fg_color="transparent")
        row_mod.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            row_mod, text="Modelo de IA", font=(FONT_FAMILY, 12), text_color="#aaa", width=180, anchor="w",
        ).pack(side="left")

        modelos_iniciales = [
            format_model_choice("gpt-6-astra"),
            format_model_choice("gpt-6-sol"),
            format_model_choice("gpt-6-luna"),
            format_model_choice("gpt-4o-mini"),
            format_model_choice("gpt-4o"),
            format_model_choice("o1"),
        ]
        self.combo_modelo = ctk.CTkComboBox(
            row_mod, font=(FONT_FAMILY, 12), height=36,
            values=modelos_iniciales, state="normal"
        )
        self.combo_modelo.set(format_model_choice("gpt-4o-mini"))
        self.combo_modelo.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.campos["OPENAI_MODEL"] = self.combo_modelo

        self.btn_refresh_models = ctk.CTkButton(
            row_mod, text="🔄 Actualizar", width=110, height=36,
            font=(FONT_FAMILY, 11), fg_color="#2b2b3d", hover_color="#3a3a50",
            command=self._refrescar_modelos_api,
        )
        self.btn_refresh_models.pack(side="left", padx=(8, 0))

        # Esfuerzo de Razonamiento
        row_reas = ctk.CTkFrame(self._current_section_frame, fg_color="transparent")
        row_reas.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            row_reas, text="Esfuerzo de Razonamiento", font=(FONT_FAMILY, 12), text_color="#aaa", width=180, anchor="w",
        ).pack(side="left")

        self.combo_reasoning = ctk.CTkOptionMenu(
            row_reas, font=(FONT_FAMILY, 12), height=36,
            values=["none", "low", "medium", "high", "xhigh"],
            fg_color="#333", button_color="#444", button_hover_color="#555",
        )
        self.combo_reasoning.set("none")
        self.combo_reasoning.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.campos["OPENAI_REASONING_EFFORT"] = self.combo_reasoning

        # Detalle Visual de Imagen
        row_det = ctk.CTkFrame(self._current_section_frame, fg_color="transparent")
        row_det.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            row_det, text="Detalle Visual de Imagen", font=(FONT_FAMILY, 12), text_color="#aaa", width=180, anchor="w",
        ).pack(side="left")

        self.combo_detail = ctk.CTkOptionMenu(
            row_det, font=(FONT_FAMILY, 12), height=36,
            values=["low", "high", "auto"],
            fg_color="#333", button_color="#444", button_hover_color="#555",
        )
        self.combo_detail.set("low")
        self.combo_detail.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.campos["OPENAI_IMAGE_DETAIL"] = self.combo_detail

        # Temperatura (modelos estándar sin razonamiento)
        row_temp = ctk.CTkFrame(self._current_section_frame, fg_color="transparent")
        row_temp.pack(fill="x", padx=15, pady=(0, 6))

        ctk.CTkLabel(
            row_temp, text="Temperatura (Modelos estándar)", font=(FONT_FAMILY, 12), text_color="#aaa", width=180, anchor="w",
        ).pack(side="left")

        self.combo_temp = ctk.CTkComboBox(
            row_temp, font=(FONT_FAMILY, 12), height=36,
            values=["0.0", "0.1", "0.2", "0.3", "0.5", "0.7", "1.0"],
            state="normal",
        )
        self.combo_temp.set("0.2")
        self.combo_temp.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.campos["OPENAI_TEMPERATURE"] = self.combo_temp

        # Notas explicativas
        ctk.CTkLabel(
            self._current_section_frame,
            text="💡 Precios por 1 millón de tokens (in = entrada / out = salida). Modelos más nuevos al principio de la lista.",
            font=(FONT_FAMILY, 11), text_color="#777",
        ).pack(anchor="w", padx=15, pady=(2, 2))
        ctk.CTkLabel(
            self._current_section_frame,
            text="💡 Razonamiento (reasoning_effort): Aplica a modelos de razonamiento (GPT-6 Astra/Sol/Luna, O1, O3).",
            font=(FONT_FAMILY, 11), text_color="#777",
        ).pack(anchor="w", padx=15, pady=(0, 2))
        ctk.CTkLabel(
            self._current_section_frame,
            text="💡 Temperatura: Aplica a modelos estándar (como gpt-4o o gpt-4o-mini). Valores bajos (0.0 - 0.2) aseguran rigor y cero alucinaciones. Los modelos GPT-6 y O-series no la permiten.",
            font=(FONT_FAMILY, 11), text_color="#777",
        ).pack(anchor="w", padx=15, pady=(0, 2))
        ctk.CTkLabel(
            self._current_section_frame,
            text="💡 Detalle visual (detail): 'low' analiza a 512px (rápido y económico). 'high' analiza en cuadrículas de alta resolución para detalles finos o textos lejanos. 'auto' deja que el modelo decida.",
            font=(FONT_FAMILY, 11), text_color="#777",
        ).pack(anchor="w", padx=15, pady=(0, 12))

        # ── DSpace ──
        self._seccion("🌐  Conexión DSpace (Importación API REST)")
        self._campo("DSPACE_URL", "URL del Servidor API", placeholder="https://tu-dspace.cl/server/api")
        self._campo("DSPACE_EMAIL", "Email", placeholder="usuario@institucion.cl")
        self._campo("DSPACE_PASSWORD", "Contraseña", show="•")

        # ── Botón guardar ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(30, 20))

        ctk.CTkButton(
            btn_frame, text="💾  Guardar Configuración", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#111",
            command=self._guardar_env,
        ).pack(side="left")

        self.label_status = ctk.CTkLabel(
            btn_frame, text="", font=(FONT_FAMILY, 12), text_color=ACCENT,
        )
        self.label_status.pack(side="left", padx=15)

    def _seccion(self, titulo):
        frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        frame.pack(fill="x", padx=20, pady=(15, 0))
        ctk.CTkLabel(
            frame, text=titulo, font=(FONT_FAMILY, 15, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 8))
        # Guardar referencia al frame contenedor actual
        self._current_section_frame = frame

    def _campo(self, key, label, show=None, placeholder=""):
        frame = self._current_section_frame

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(
            row, text=label, font=(FONT_FAMILY, 12), text_color="#aaa", width=180, anchor="w",
        ).pack(side="left")

        entry = ctk.CTkEntry(
            row, font=(FONT_FAMILY, 12), height=36,
            placeholder_text=placeholder,
            show=show if show else "",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(5, 0))

        if show:
            btn_show = ctk.CTkButton(
                row, text="👁️", width=36, height=36,
                fg_color="#333", hover_color="#444",
                command=lambda e=entry, s=show: self._toggle_show(e, s),
            )
            btn_show.pack(side="left", padx=(5, 0))

        self.campos[key] = entry

    def _toggle_show(self, entry, char):
        if entry.cget("show") == char:
            entry.configure(show="")
        else:
            entry.configure(show=char)

    def _refrescar_modelos_api(self):
        api_key = self.obtener_valor("OPENAI_API_KEY")
        if not api_key or api_key == "tu_llave_aqui":
            messagebox.showwarning("Aviso", "Ingresa primero tu API Key de OpenAI para consultar los modelos disponibles.")
            return

        self.btn_refresh_models.configure(state="disabled", text="Consultando...")
        self.label_status.configure(text="Consultando modelos en OpenAI...")

        def _fetch():
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                m_list = client.models.list()

                candidatos = []
                for m in m_list.data:
                    mid = m.id.lower()
                    if (mid.startswith(('gpt-', 'o1', 'o3')) and 
                        not any(x in mid for x in ['audio', 'realtime', 'transcribe', 'tts', 'embedding', 'moderation', 'search', 'edit'])):
                        candidatos.append((m.id, getattr(m, 'created', 0)))

                # Ordenar por fecha created descendente (los más nuevos primero)
                candidatos.sort(key=lambda x: x[1], reverse=True)
                ids_ordenados = [x[0] for x in candidatos]

                # Asegurar modelos prioritarios destacados al principio
                prioritarios = ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-4o-mini", "gpt-4o", "o1"]
                for p in reversed(prioritarios):
                    if p in ids_ordenados:
                        ids_ordenados.remove(p)
                    ids_ordenados.insert(0, p)

                opciones_formateadas = [format_model_choice(mid) for mid in ids_ordenados]

                def _update_ui():
                    self.btn_refresh_models.configure(state="normal", text="🔄 Actualizar")
                    self.combo_modelo.configure(values=opciones_formateadas)
                    self.label_status.configure(text=f"✅ {len(opciones_formateadas)} modelos actualizados")
                    self.after(3000, lambda: self.label_status.configure(text=""))

                self.after(0, _update_ui)
            except Exception as e:
                def _error_ui(err=str(e)):
                    self.btn_refresh_models.configure(state="normal", text="🔄 Actualizar")
                    self.label_status.configure(text="")
                    messagebox.showerror("Error", f"No se pudo consultar los modelos de OpenAI:\n{err}")
                self.after(0, _error_ui)

        threading.Thread(target=_fetch, daemon=True).start()

    def _cargar_env(self):
        if os.path.exists(ENV_PATH):
            load_dotenv(ENV_PATH, override=True)
        for key, widget in self.campos.items():
            val = os.getenv(key, "")
            if val:
                if key == "OPENAI_MODEL":
                    encontrado = False
                    for opt in widget.cget("values"):
                        if parse_model_choice(opt) == val:
                            widget.set(opt)
                            encontrado = True
                            break
                    if not encontrado:
                        widget.set(format_model_choice(val))
                elif isinstance(widget, (ctk.CTkComboBox, ctk.CTkOptionMenu)):
                    widget.set(val)
                elif isinstance(widget, ctk.CTkEntry):
                    widget.delete(0, "end")
                    widget.insert(0, val)

    def _guardar_env(self):
        # Crear archivo .env si no existe
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write("# Configuración Catalogador DSpace\n")

        for key, widget in self.campos.items():
            if key == "OPENAI_MODEL":
                valor = parse_model_choice(widget.get().strip())
            else:
                valor = widget.get().strip()
            set_key(ENV_PATH, key, valor)

        self.label_status.configure(text="✅ Guardado correctamente")
        self.log_fn("Configuración guardada en .env")
        # Limpiar mensaje después de 3 segundos
        self.after(3000, lambda: self.label_status.configure(text=""))

    def obtener_valor(self, key):
        """Retorna el valor actual de un campo."""
        widget = self.campos.get(key)
        if not widget:
            return ""
        val = widget.get().strip()
        if key == "OPENAI_MODEL":
            return parse_model_choice(val)
        return val

# ══════════════════════════════════════════════════════════════
# Frame: Proyecto
# ══════════════════════════════════════════════════════════════

class ProyectoFrame(ctk.CTkScrollableFrame):
    """Sección de selección de proyecto — un solo campo de ruta."""

    def __init__(self, parent, log_fn, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.proyecto_dir = None
        self.nombre_proyecto = None
        self._crear_ui()

    def _crear_ui(self):
        # Título
        ctk.CTkLabel(
            self, text="📂  Selección de Proyecto",
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            self, text="Selecciona la carpeta del proyecto que contiene las fotos y el CSV",
            font=(FONT_FAMILY, 13), text_color="#888",
        ).pack(anchor="w", padx=20, pady=(0, 6))
        ctk.CTkLabel(
            self,
            text="📷 Extensiones permitidas: .jpg, .jpeg, .png, .gif, .bmp, .webp, .tif, .tiff  (y .csv para metadatos)",
            font=(FONT_FAMILY, 11), text_color="#00d4aa",
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # ── Selector de carpeta ──
        card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            card, text="📁  Carpeta de origen del proyecto",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(0, 10))

        self.entry_ruta = ctk.CTkEntry(
            row, font=(FONT_FAMILY, 12), height=38,
            placeholder_text=r"Ej: \\10.20.20.212\...\PYT-2015-0504\FOTOS  o  D:\Proyectos\...",
        )
        self.entry_ruta.pack(side="left", fill="x", expand=True)
        self.entry_ruta.bind("<KeyRelease>", self._on_ruta_change)
        self.entry_ruta.bind("<FocusOut>", self._on_ruta_change)

        ctk.CTkButton(
            row, text="📁 Examinar", width=110, height=38,
            font=(FONT_FAMILY, 12), fg_color="#333", hover_color="#444",
            command=self._examinar,
        ).pack(side="left", padx=(8, 0))

        # ── Campo: Nombre o Código del Proyecto (Editable y Autodetectado) ──
        ctk.CTkLabel(
            card, text="🏷️  Nombre o Código del Proyecto (detectado automáticamente, puedes editarlo):",
            font=(FONT_FAMILY, 12, "bold"), text_color="#ccc",
        ).pack(anchor="w", padx=15, pady=(4, 4))

        row_nom = ctk.CTkFrame(card, fg_color="transparent")
        row_nom.pack(fill="x", padx=15, pady=(0, 8))

        self.entry_nombre = ctk.CTkEntry(
            row_nom, font=(FONT_FAMILY, 13, "bold"), height=36,
            placeholder_text="Ej: PYT-2015-0504, IMA-2019-0123, FIA-GI-V-1998-1-A-142...",
            text_color=ACCENT,
        )
        self.entry_nombre.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            row_nom, text="🔄 Auto-detectar", width=120, height=36,
            font=(FONT_FAMILY, 11), fg_color="#2b2b3d", hover_color="#3a3a50",
            command=self._forzar_autodetectar_nombre,
        ).pack(side="left", padx=(8, 0))

        # Nota
        ctk.CTkLabel(
            card,
            text="💡 El sistema creará una carpeta en tu PC con este código para organizar fotos y metadatos sin mezclar proyectos.",
            font=(FONT_FAMILY, 11), text_color="#777",
        ).pack(anchor="w", padx=15, pady=(0, 12))

        # ── Botón cargar ──
        self.btn_cargar = ctk.CTkButton(
            self, text="📥  Copiar y Cargar Proyecto", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#111",
            command=self._cargar_proyecto,
        )
        self.btn_cargar.pack(anchor="w", padx=20, pady=(5, 10))

        # ── O Proyectos en Workspace ──
        self.ws_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.ws_card.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkLabel(
            self.ws_card, text="🔄  O cambiar a un proyecto ya cargado en tu PC:",
            font=(FONT_FAMILY, 13, "bold"), text_color="#ccc"
        ).pack(anchor="w", padx=15, pady=(12, 5))
        
        self.combo_ws = ctk.CTkOptionMenu(
            self.ws_card, values=["-- Vacío --"], font=(FONT_FAMILY, 12),
            fg_color="#333", button_color="#444", button_hover_color="#555",
            command=self._cargar_desde_ws
        )
        self.combo_ws.pack(fill="x", padx=15, pady=(0, 15))

        # ── Progreso de copia ──
        self.prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        # No lo empaquetamos aún, lo haremos al hacer clic

        self.prog_lbl = ctk.CTkLabel(self.prog_frame, text="Preparando copia...", font=(FONT_FAMILY, 12), text_color="#aaa")
        self.prog_lbl.pack(anchor="w", pady=(0, 5))

        self.prog_bar = ctk.CTkProgressBar(self.prog_frame, height=14, corner_radius=7, fg_color="#1e1e30", progress_color=ACCENT)
        self.prog_bar.pack(fill="x")
        self.prog_bar.set(0)

        # ── Resumen ──
        self.resumen_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        self.resumen_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.label_resumen = ctk.CTkLabel(
            self.resumen_frame, text="Ningún proyecto cargado",
            font=(FONT_FAMILY, 13), text_color="#666", justify="left", anchor="w",
        )
        self.label_resumen.pack(fill="x", padx=15, pady=15)

    def _detectar_nombre_proyecto(self, ruta):
        """Extrae de forma inteligente el código o nombre del proyecto de cualquier tipo (PYT, IMA, FIA, etc.)."""
        if not ruta:
            return ""
        ruta_limpia = ruta.rstrip('\\/')
        partes = [p for p in re.split(r'[\\/]', ruta_limpia) if p]
        if not partes:
            return ""

        nombre_dir = partes[-1]
        padre_dir = partes[-2] if len(partes) > 1 else ""

        nombres_genericos = {
            'fotos', 'foto', 'fotografias', 'fotografías', 'fotografia', 'fotografía',
            'images', 'image', 'imagenes', 'imágenes', 'img', 'photos', 'photo',
            'archivos', 'files', 'data', 'datos'
        }

        # 1. Si la carpeta es genérica (FOTOS, IMAGENES, etc.) tomar la carpeta padre
        if nombre_dir.lower() in nombres_genericos and padre_dir:
            return padre_dir

        # 2. Buscar hacia atrás la primera carpeta que no sea genérica
        for parte in reversed(partes):
            if parte.lower() not in nombres_genericos:
                return parte

        return nombre_dir

    def _on_ruta_change(self, event=None):
        ruta = self.entry_ruta.get().strip()
        nom = self._detectar_nombre_proyecto(ruta)
        if nom:
            self.entry_nombre.delete(0, "end")
            self.entry_nombre.insert(0, nom)

    def _forzar_autodetectar_nombre(self):
        self._on_ruta_change()

    def _examinar(self):
        ruta = filedialog.askdirectory(title="Selecciona la carpeta del proyecto")
        if ruta:
            self.entry_ruta.delete(0, "end")
            self.entry_ruta.insert(0, ruta)
            self._on_ruta_change()

    def actualizar_estado(self):
        """Se llama al entrar a la pestaña o al iniciar la app."""
        base_dir = ROOT_DIR
        ws_dir = os.path.join(base_dir, "workspace_local")
        if os.path.exists(ws_dir):
            proyectos = [d for d in os.listdir(ws_dir) if os.path.isdir(os.path.join(ws_dir, d))]
            if proyectos:
                self.combo_ws.configure(values=proyectos)
                if self.nombre_proyecto and self.nombre_proyecto in proyectos:
                    self.combo_ws.set(self.nombre_proyecto)
                else:
                    self._cargar_desde_ws(proyectos[0])
                    self.combo_ws.set(proyectos[0])
            else:
                self.combo_ws.configure(values=["-- Vacío --"])
                self.combo_ws.set("-- Vacío --")

    def _cargar_desde_ws(self, val):
        if val in ["-- Seleccionar --", "-- Vacío --"]: return
        base_dir = ROOT_DIR
        ws_dir = os.path.join(base_dir, "workspace_local", val)
        self.proyecto_dir = ws_dir
        self.nombre_proyecto = val
        self.log_fn(f"Cambiado a proyecto local: {val}")
        self._actualizar_resumen()

    def _cargar_proyecto(self):
        ruta = self.entry_ruta.get().strip()
        if not ruta:
            messagebox.showwarning("Advertencia", "Selecciona una carpeta primero.")
            return
        if not os.path.exists(ruta):
            messagebox.showerror("Error", f"La ruta '{ruta}' no existe o no es accesible.")
            return

        nombre_ingresado = self.entry_nombre.get().strip()
        if not nombre_ingresado:
            nombre_ingresado = self._detectar_nombre_proyecto(ruta) or os.path.basename(ruta.rstrip('\\/'))

        # Sanitizar nombre para que sea válido en Windows
        nombre_orig = re.sub(r'[\\/:*?"<>|]', '_', nombre_ingresado).strip()
        if not nombre_orig:
            nombre_orig = "Proyecto_Sin_Nombre"
        
        # Iniciar copiado
        self.btn_cargar.configure(state="disabled", text="Copiando al workspace local...")
        self.prog_frame.pack(fill="x", padx=20, pady=(0, 15), before=self.resumen_frame)
        self.prog_bar.set(0)
        
        def _run_copy():
            try:
                import shutil
                # Crear workspace en la misma carpeta del ejecutable
                base_dir = ROOT_DIR
                ws_dir = os.path.join(base_dir, "workspace_local", nombre_orig)
                os.makedirs(ws_dir, exist_ok=True)
                
                # Listar archivos a copiar (imágenes y csv)
                archivos = []
                exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff', '.csv')
                
                for f in os.listdir(ruta):
                    if f.lower().endswith(exts):
                        archivos.append(f)
                
                # También buscar en subcarpeta "Fotos" si existe
                rutafotos = os.path.join(ruta, "Fotos")
                rutafotos_local = os.path.join(ws_dir, "Fotos")
                if os.path.exists(rutafotos):
                    os.makedirs(rutafotos_local, exist_ok=True)
                    for f in os.listdir(rutafotos):
                        if f.lower().endswith(exts):
                            archivos.append(os.path.join("Fotos", f))
                
                total = len(archivos)
                if total == 0:
                    self.after(0, lambda: self._copia_terminada(ws_dir, nombre_orig, "Carpeta vacía o sin fotos/CSVs válidos."))
                    return
                
                for i, arch in enumerate(archivos):
                    src = os.path.join(ruta, arch)
                    dst = os.path.join(ws_dir, arch)
                    nombre_base, ext_orig = os.path.splitext(arch)

                    if ext_orig.lower() == '.bmp':
                        dst_jpg = os.path.join(ws_dir, nombre_base + ".jpg")
                        if not os.path.exists(dst_jpg) or os.path.getmtime(src) > os.path.getmtime(dst_jpg):
                            try:
                                with Image.open(src) as img:
                                    img.convert("RGB").save(dst_jpg, "JPEG", quality=95)
                            except Exception:
                                pass
                    else:
                        # Solo copiar si no existe o si es distinto (para no demorar si ya se copió antes)
                        if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst) or os.path.getsize(src) != os.path.getsize(dst):
                            shutil.copy2(src, dst)
                    
                    pct = (i + 1) / total
                    self.after(0, lambda p=pct, n=os.path.basename(arch), c=i+1, t=total: self._update_prog(p, n, c, t))
                
                # Sincronizar silenciosamente referencias a .bmp en CSVs si los hay
                for root_c, _, files_c in os.walk(ws_dir):
                    for fc in files_c:
                        if fc.lower().endswith('.csv'):
                            csv_file = os.path.join(root_c, fc)
                            for enc in ['utf-8', 'latin1', 'cp1252']:
                                try:
                                    df = pd.read_csv(csv_file, dtype=str, encoding=enc, sep=None, engine='python')
                                    modificado = False
                                    for col in df.columns:
                                        if any(k in col.lower() for k in ['nombre', 'file', 'archivo', 'foto', 'dc.title']):
                                            mask = df[col].astype(str).str.lower().str.endswith('.bmp')
                                            if mask.any():
                                                df[col] = df[col].astype(str).str.replace(re.compile(r'\.bmp$', re.IGNORECASE), '.jpg', regex=True)
                                                modificado = True
                                    if modificado:
                                        df.to_csv(csv_file, index=False, encoding='utf-8')
                                    break
                                except Exception:
                                    continue

                self.after(0, lambda: self._copia_terminada(ws_dir, nombre_orig))
                
            except Exception as e:
                self.after(0, lambda err=str(e): self._copia_error(err))
                
        threading.Thread(target=_run_copy, daemon=True).start()

    def _update_prog(self, pct, name, cur, tot):
        self.prog_bar.set(pct)
        self.prog_lbl.configure(text=f"Copiando [{cur}/{tot}]: {name}")

    def _copia_error(self, err):
        self.btn_cargar.configure(state="normal", text="📥  Copiar y Cargar Proyecto")
        self.prog_lbl.configure(text="Error al copiar archivos", text_color=ACCENT_RED)
        messagebox.showerror("Error", f"Error copiando al workspace local:\n{err}")

    def _copia_terminada(self, ws_dir, nombre, warn=None):
        self.btn_cargar.configure(state="normal", text="📥  Copiar y Cargar Proyecto")
        self.prog_frame.pack_forget()
        
        if warn:
            self.log_fn(f"⚠️ {warn}")
            
        self.proyecto_dir = ws_dir
        self.nombre_proyecto = nombre
        self.log_fn(f"Proyecto listo en workspace local: {nombre}")
        self._actualizar_resumen()
        self.actualizar_estado() # Actualizar combobox

    def _actualizar_resumen(self):
        if not self.proyecto_dir or not os.path.exists(self.proyecto_dir):
            self.label_resumen.configure(text="Ningún proyecto cargado", text_color="#666")
            return

        stats = Catalogador.obtener_stats(self.proyecto_dir)
        n_fotos = Catalogador.contar_fotos(self.proyecto_dir)

        txt = (
            f"📁  Proyecto: {self.nombre_proyecto}\n"
            f"📂  Ruta: {self.proyecto_dir}\n"
            f"📄  CSV: {stats['csv'] or 'No encontrado'}\n"
            f"🖼️  Fotos encontradas: {n_fotos}\n"
            f"📊  Registros: {stats['total']}  |  "
            f"Catalogados: {stats['catalogados']}  |  "
            f"Pendientes: {stats['pendientes']}"
        )
        self.label_resumen.configure(text=txt, text_color="#ccc")


# ══════════════════════════════════════════════════════════════
# Frame: Catalogar
# ══════════════════════════════════════════════════════════════

class CatalogarFrame(ctk.CTkScrollableFrame):
    """Sección de catalogación con IA."""

    def __init__(self, parent, log_fn, get_proyecto, get_config, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.get_proyecto = get_proyecto  # Callable → (proyecto_dir, nombre)
        self.get_config = get_config      # Callable → dict con valores del .env
        self.catalogador = None
        self._running = False
        self._crear_ui()

    def _crear_ui(self):
        ctk.CTkLabel(
            self, text="🤖  Catalogación con IA",
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            self, text="Analiza imágenes con OpenAI para generar metadatos automáticamente",
            font=(FONT_FAMILY, 13), text_color="#888",
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # ── Stats ──
        stats_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        stats_card.pack(fill="x", padx=20, pady=(0, 12))

        self.label_stats = ctk.CTkLabel(
            stats_card,
            text="Carga un proyecto primero para ver las estadísticas",
            font=(FONT_FAMILY, 13), text_color="#888", justify="left", anchor="w",
        )
        self.label_stats.pack(fill="x", padx=15, pady=(12, 4))

        self.label_info_modelo = ctk.CTkLabel(
            stats_card,
            text="🤖 Modelo configurado: gpt-4o-mini  |  Razonamiento: none  |  Detalle: low",
            font=(FONT_FAMILY, 11), text_color=ACCENT, justify="left", anchor="w",
        )
        self.label_info_modelo.pack(fill="x", padx=15, pady=(0, 10))

        # ── Contexto del Proyecto (fia.notageneral) ──
        card_contexto = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_contexto.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            card_contexto, text="📌  Contexto Oficial del Proyecto (fia.notageneral)",
            font=(FONT_FAMILY, 13, "bold"), text_color=ACCENT, anchor="w",
        ).pack(fill="x", padx=15, pady=(12, 4))

        self.label_contexto = ctk.CTkLabel(
            card_contexto,
            text="(Carga un proyecto para visualizar el contexto oficial extraído del CSV)",
            font=(FONT_FAMILY, 11), text_color="#aaa", justify="left", anchor="w", wraplength=640,
        )
        self.label_contexto.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            card_contexto, text="✍️  Notas o especificaciones adicionales para la IA (opcional):",
            font=(FONT_FAMILY, 11, "bold"), text_color="#888", anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 3))

        self.entry_contexto_extra = ctk.CTkEntry(
            card_contexto,
            placeholder_text="Ej: Prestar especial atención a las etiquetas de botellas y maquinaria de embotellado...",
            font=(FONT_FAMILY, 12), height=34, fg_color="#1e1e30",
        )
        self.entry_contexto_extra.pack(fill="x", padx=15, pady=(0, 12))

        # ── Editor de Prompt de IA ──
        card_prompt = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_prompt.pack(fill="x", padx=20, pady=(0, 12))

        row_prompt_top = ctk.CTkFrame(card_prompt, fg_color="transparent")
        row_prompt_top.pack(fill="x", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            row_prompt_top, text="📝  Instrucciones de IA (Prompt del Sistema)",
            font=(FONT_FAMILY, 13, "bold"), text_color="#ccc", anchor="w",
        ).pack(side="left")

        self.btn_guardar_prompt = ctk.CTkButton(
            row_prompt_top, text="💾 Guardar", width=85, height=28,
            font=(FONT_FAMILY, 11, "bold"), fg_color="#333", hover_color="#444",
            command=self._guardar_prompt,
        )
        self.btn_guardar_prompt.pack(side="right", padx=(6, 0))

        self.btn_restaurar_prompt = ctk.CTkButton(
            row_prompt_top, text="🔄 Restaurar FIA", width=110, height=28,
            font=(FONT_FAMILY, 11), fg_color="#333", hover_color="#444",
            command=self._restaurar_prompt,
        )
        self.btn_restaurar_prompt.pack(side="right")

        self.textbox_prompt = ctk.CTkTextbox(
            card_prompt, height=140, font=("Consolas", 11),
            fg_color="#181828", text_color="#e0e0e0", corner_radius=6, wrap="word",
        )
        self.textbox_prompt.pack(fill="x", padx=15, pady=(0, 12))
        self.textbox_prompt.insert("1.0", cargar_prompt_sistema())

        # ── Opciones ──
        opts_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        opts_card.pack(fill="x", padx=20, pady=(0, 12))

        self.check_recatalogar = ctk.CTkCheckBox(
            opts_card, text="  Recatalogar todo (sobrescribir existentes)",
            font=(FONT_FAMILY, 13),
        )
        self.check_recatalogar.pack(anchor="w", padx=15, pady=(10, 10))

        # ── Progreso ──
        prog_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        prog_card.pack(fill="x", padx=20, pady=(0, 12))

        self.label_progreso = ctk.CTkLabel(
            prog_card, text="Esperando...",
            font=(FONT_FAMILY, 13), text_color="#aaa",
        )
        self.label_progreso.pack(anchor="w", padx=15, pady=(12, 5))

        self.progress_bar = ctk.CTkProgressBar(
            prog_card, height=14, corner_radius=7,
            fg_color="#1e1e30", progress_color=ACCENT,
        )
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 5))
        self.progress_bar.set(0)

        self.label_pct = ctk.CTkLabel(
            prog_card, text="0%", font=(FONT_FAMILY, 12), text_color="#666",
        )
        self.label_pct.pack(anchor="e", padx=15, pady=(0, 12))

        # ── Botones ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 20))

        self.btn_iniciar = ctk.CTkButton(
            btn_frame, text="▶️  Iniciar Catalogación", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#111",
            command=self._iniciar,
        )
        self.btn_iniciar.pack(side="left", padx=(0, 10))

        self.btn_detener = ctk.CTkButton(
            btn_frame, text="⏹  Detener", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT_RED, hover_color="#c0392b", state="disabled",
            command=self._detener,
        )
        self.btn_detener.pack(side="left")

    def _guardar_prompt(self):
        texto = self.textbox_prompt.get("1.0", "end").strip()
        if texto:
            guardar_prompt_sistema(texto)
            self.log_fn("💾 Prompt de sistema guardado correctamente.")
            messagebox.showinfo("Guardado", "Prompt personalizado guardado con éxito.")

    def _restaurar_prompt(self):
        if messagebox.askyesno("Confirmar", "¿Deseas restaurar el Prompt General de FIA por defecto?"):
            self.textbox_prompt.delete("1.0", "end")
            self.textbox_prompt.insert("1.0", PROMPT_SISTEMA_DEFAULT.strip())
            guardar_prompt_sistema(PROMPT_SISTEMA_DEFAULT.strip())
            self.log_fn("🔄 Prompt de sistema restaurado a la versión general FIA.")

    def actualizar_stats(self):
        """Refresca las estadísticas y contexto cuando se cambia de sección."""
        pdir, nombre = self.get_proyecto()
        if not pdir:
            self.label_stats.configure(
                text="Carga un proyecto primero para ver las estadísticas",
                text_color="#888",
            )
            self.label_contexto.configure(
                text="(Carga un proyecto para visualizar el contexto oficial extraído del CSV)",
                text_color="#666",
            )
            return

        stats = Catalogador.obtener_stats(pdir)
        pct = (
            round(stats['catalogados'] / stats['total'] * 100)
            if stats['total'] > 0 else 0
        )
        txt = (
            f"📁  Proyecto: {nombre}\n"
            f"🖼️  Total imágenes: {stats['total']}\n"
            f"✅  Ya catalogadas: {stats['catalogados']}  ({pct}%)\n"
            f"⏳  Pendientes: {stats['pendientes']}"
        )
        self.label_stats.configure(text=txt, text_color="#ccc")

        # Cargar nota general del proyecto
        nota = Catalogador.obtener_nota_general(pdir)
        if nota:
            self.label_contexto.configure(text=f'"{nota}"', text_color="#ddd")
        else:
            self.label_contexto.configure(
                text="(No se encontró columna 'fia.notageneral' en el CSV. Puedes ingresar notas abajo)",
                text_color="#888",
            )

        # Actualizar modelo y razonamiento configurado
        config = self.get_config()
        mod = config.get("OPENAI_MODEL", "gpt-4o-mini")
        reas = config.get("OPENAI_REASONING_EFFORT", "none")
        det = config.get("OPENAI_IMAGE_DETAIL", "low")
        temp = config.get("OPENAI_TEMPERATURE", "0.2")
        self.label_info_modelo.configure(
            text=f"🤖 Modelo configurado: {mod}  |  Razonamiento: {reas}  |  Detalle: {det}  |  Temp: {temp}"
        )

    def _log_safe(self, msg):
        """Log thread-safe via after()."""
        self.after(0, lambda: self.log_fn(msg))

    def _progress_safe(self, cur, tot):
        """Actualiza progreso thread-safe."""
        def _update():
            pct = cur / tot if tot > 0 else 0
            self.progress_bar.set(pct)
            self.label_pct.configure(text=f"{int(pct * 100)}%")
            self.label_progreso.configure(text=f"[{cur}/{tot}] procesadas")
        self.after(0, _update)

    def _iniciar(self):
        pdir, nombre = self.get_proyecto()
        if not pdir:
            messagebox.showwarning("Advertencia", "Carga un proyecto primero en la sección 📂 Proyecto.")
            return

        config = self.get_config()
        api_key = config.get("OPENAI_API_KEY", "")
        modelo = config.get("OPENAI_MODEL", "gpt-4o-mini")
        reasoning_effort = config.get("OPENAI_REASONING_EFFORT", "none")
        image_detail = config.get("OPENAI_IMAGE_DETAIL", "low")
        temperatura = config.get("OPENAI_TEMPERATURE", "0.2")
        if not api_key or api_key == "tu_llave_aqui":
            messagebox.showerror("Error", "Configura tu API Key de OpenAI en la sección ⚙️ Ajustes.")
            return

        prompt_actual = self.textbox_prompt.get("1.0", "end").strip()
        contexto_extra = self.entry_contexto_extra.get().strip()

        self._running = True
        self.btn_iniciar.configure(state="disabled")
        self.btn_detener.configure(state="normal")
        self.progress_bar.set(0)
        self.label_pct.configure(text="0%")
        self.label_progreso.configure(text="Iniciando...")

        forzar = self.check_recatalogar.get() == 1

        def _run():
            try:
                self.catalogador = Catalogador(
                    api_key=api_key,
                    modelo=modelo,
                    reasoning_effort=reasoning_effort,
                    image_detail=image_detail,
                    temperatura=temperatura,
                    prompt_sistema=prompt_actual,
                    log=self._log_safe,
                    progress=self._progress_safe,
                )
                ok = self.catalogador.catalogar(
                    pdir, forzar_recatalogar=forzar, contexto_extra=contexto_extra
                )
                if ok:
                    self._log_safe("🎉 ¡Proceso completado exitosamente!")
                self.after(0, self._finalizar)
            except Exception as e:
                self._log_safe(f"❌ Error inesperado: {e}")
                self.after(0, self._finalizar)

        threading.Thread(target=_run, daemon=True).start()

    def _detener(self):
        if self.catalogador:
            self.catalogador.cancelar()
            self.log_fn("Solicitando detención...")

    def _finalizar(self):
        self._running = False
        self.btn_iniciar.configure(state="normal")
        self.btn_detener.configure(state="disabled")
        self.actualizar_stats()


# ══════════════════════════════════════════════════════════════
# Frame: Exportar
# ══════════════════════════════════════════════════════════════

class ExportarFrame(ctk.CTkScrollableFrame):
    """Sección de exportación: API REST o paquete SAF."""

    def __init__(self, parent, log_fn, get_proyecto, get_config, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.get_proyecto = get_proyecto
        self.get_config = get_config
        self.importador = None
        self.saf_builder = None
        self._running = False
        
        self.col_uuid = ""
        self.col_handle = ""
        self._colecciones_export = []
        self._preview_items = []
        self._preview_idx = 0
        self._curr_ctk_img = None
        
        self._crear_ui()
        self._cargar_handle_desde_config()

    def _crear_ui(self):
        ctk.CTkLabel(
            self, text="📤  Exportar a DSpace",
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            self, text="Sube directamente por API REST o genera un paquete SAF offline",
            font=(FONT_FAMILY, 13), text_color="#888",
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # ── Colección Destino ──
        card_col = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_col.pack(fill="x", padx=20, pady=(0, 10))
        
        row_col = ctk.CTkFrame(card_col, fg_color="transparent")
        row_col.pack(fill="x", padx=15, pady=(12, 5))
        
        ctk.CTkLabel(
            row_col, text="🎯 Colección Destino", font=(FONT_FAMILY, 14, "bold"), width=150, anchor="w"
        ).pack(side="left")
        
        self.btn_cargar_cols = ctk.CTkButton(
            row_col, text="🔄 Cargar", width=80, height=36,
            fg_color="#333", hover_color="#444", font=(FONT_FAMILY, 12),
            command=self._cargar_colecciones_export
        )
        self.btn_cargar_cols.pack(side="left", padx=(5, 10))
        
        self.col_var = ctk.StringVar(value="(Cargar colecciones primero)")
        self.dropdown_cols = ctk.CTkOptionMenu(
            row_col, variable=self.col_var,
            values=["(Cargar colecciones primero)"],
            font=(FONT_FAMILY, 12), height=36,
            fg_color="#333", button_color="#444", dropdown_fg_color="#2a2a3e",
            command=self._on_col_select
        )
        self.dropdown_cols.pack(side="left", fill="x", expand=True)

        row_warn = ctk.CTkFrame(card_col, fg_color="transparent")
        row_warn.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(
            row_warn, text="⚠️  Por el momento la exportación solo funciona para FOTOS.",
            font=(FONT_FAMILY, 11), text_color="#aa8800"
        ).pack(side="left", padx=155)

        # ── Vista Previa de Datos a Exportar ──
        card_preview = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_preview.pack(fill="x", padx=20, pady=(0, 12))

        row_prev_top = ctk.CTkFrame(card_preview, fg_color="transparent")
        row_prev_top.pack(fill="x", padx=15, pady=(10, 8))

        self.btn_toggle_preview = ctk.CTkButton(
            row_prev_top, text="🔽 Plegar", width=75, height=28,
            font=(FONT_FAMILY, 11, "bold"), fg_color="#333", hover_color="#444",
            command=self._toggle_preview,
        )
        self.btn_toggle_preview.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            row_prev_top, text="👁️  Vista Previa de Metadatos y Fotos",
            font=(FONT_FAMILY, 13, "bold"), text_color=ACCENT, anchor="w",
        ).pack(side="left")

        # Controles a la derecha
        self.btn_prev_reload = ctk.CTkButton(
            row_prev_top, text="🔄", width=34, height=28,
            font=(FONT_FAMILY, 12), fg_color="#333", hover_color="#444",
            command=self._cargar_items_preview,
        )
        self.btn_prev_reload.pack(side="right", padx=(4, 0))

        self.btn_prev_next = ctk.CTkButton(
            row_prev_top, text="▶", width=34, height=28,
            font=(FONT_FAMILY, 12, "bold"), fg_color="#333", hover_color="#444",
            command=self._next_preview,
        )
        self.btn_prev_next.pack(side="right", padx=(3, 0))

        self.label_preview_pos = ctk.CTkLabel(
            row_prev_top, text="0 de 0", font=(FONT_FAMILY, 12, "bold"), text_color="#ddd",
        )
        self.label_preview_pos.pack(side="right", padx=5)

        self.btn_prev_prev = ctk.CTkButton(
            row_prev_top, text="◀", width=34, height=28,
            font=(FONT_FAMILY, 12, "bold"), fg_color="#333", hover_color="#444",
            command=self._prev_preview,
        )
        self.btn_prev_prev.pack(side="right", padx=(5, 0))

        self.combo_preview_jump = ctk.CTkOptionMenu(
            row_prev_top, values=["-- Fotos --"], width=150, height=28,
            font=(FONT_FAMILY, 11), fg_color="#222233", button_color="#333344",
            dropdown_fg_color="#1a1a2e", command=self._on_jump_select,
        )
        self.combo_preview_jump.pack(side="right", padx=(0, 8))

        # Cuerpo del Preview (Contenedor colapsable)
        self.prev_body = ctk.CTkFrame(card_preview, fg_color="#161626", corner_radius=8)
        self.prev_body.pack(fill="x", padx=15, pady=(0, 12))
        self._preview_visible = True

        # Columna Izquierda: Foto y Detalles del archivo
        col_left = ctk.CTkFrame(self.prev_body, fg_color="transparent", width=220)
        col_left.pack(side="left", padx=12, pady=12)

        self.label_preview_img = ctk.CTkLabel(
            col_left, text="Sin foto", width=210, height=155,
            fg_color="#10101e", corner_radius=6,
        )
        self.label_preview_img.pack(pady=(0, 8))

        card_file_info = ctk.CTkFrame(col_left, fg_color="#10101e", corner_radius=6)
        card_file_info.pack(fill="x")

        self.label_preview_file = ctk.CTkLabel(
            card_file_info, text="-", font=(FONT_FAMILY, 11, "bold"),
            text_color=ACCENT, wraplength=200, justify="center",
        )
        self.label_preview_file.pack(padx=8, pady=(6, 2))

        self.label_preview_filesize = ctk.CTkLabel(
            card_file_info, text="⚖️ Peso: -", font=(FONT_FAMILY, 10), text_color="#ccc",
        )
        self.label_preview_filesize.pack(padx=8, pady=1)

        self.label_preview_dims = ctk.CTkLabel(
            card_file_info, text="📐 Resolución: -", font=(FONT_FAMILY, 10), text_color="#888",
        )
        self.label_preview_dims.pack(padx=8, pady=1)

        self.label_preview_entity = ctk.CTkLabel(
            card_file_info, text="🏛️ Entidad: -", font=(FONT_FAMILY, 10), text_color="#888",
        )
        self.label_preview_entity.pack(padx=8, pady=(1, 6))

        # Columna Derecha: Inspector de Metadatos Completo (Scrollable con altura ajustable)
        col_right = ctk.CTkFrame(self.prev_body, fg_color="transparent")
        col_right.pack(side="left", fill="both", expand=True, padx=(5, 12), pady=12)

        self.scroll_metadata = ctk.CTkScrollableFrame(
            col_right, height=300, fg_color="#10101e", corner_radius=6,
        )
        self.scroll_metadata.pack(fill="both", expand=True)

        # ── Método ──
        self.modo_var = ctk.StringVar(value="api")

        card_api = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_api.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkRadioButton(
            card_api, text="  API REST — Sube directamente a DSpace 7",
            variable=self.modo_var, value="api",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 5))

        self.check_limpiar = ctk.CTkCheckBox(
            card_api, text="  Limpiar archivos locales al terminar",
            font=(FONT_FAMILY, 12),
        )
        self.check_limpiar.pack(anchor="w", padx=35, pady=(0, 12))

        self.label_api_status = ctk.CTkLabel(
            card_api, text="", font=(FONT_FAMILY, 12), text_color="#888",
        )
        self.label_api_status.pack(anchor="w", padx=35, pady=(0, 12))

        # ── SAF ──
        card_saf = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card_saf.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkRadioButton(
            card_saf, text="  Paquete SAF — Genera carpeta para importar offline",
            variable=self.modo_var, value="saf",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 12))

        # ── Progreso ──
        prog_card = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        prog_card.pack(fill="x", padx=20, pady=(5, 15))

        self.label_progreso = ctk.CTkLabel(
            prog_card, text="Esperando...",
            font=(FONT_FAMILY, 13), text_color="#aaa",
        )
        self.label_progreso.pack(anchor="w", padx=15, pady=(12, 5))

        self.progress_bar = ctk.CTkProgressBar(
            prog_card, height=14, corner_radius=7,
            fg_color="#1e1e30", progress_color=ACCENT,
        )
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 5))
        self.progress_bar.set(0)

        self.label_pct = ctk.CTkLabel(
            prog_card, text="0%", font=(FONT_FAMILY, 12), text_color="#666",
        )
        self.label_pct.pack(anchor="e", padx=15, pady=(0, 12))

        # ── Nota ──
        ctk.CTkLabel(
            self,
            text="⚠️  API REST: Los ítems se crean como BORRADORES en DSpace. Revísalos antes de publicar.",
            font=(FONT_FAMILY, 12), text_color="#e0a040", wraplength=600, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # ── Botones ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 20))

        self.btn_iniciar = ctk.CTkButton(
            btn_frame, text="🚀  Iniciar Exportación", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#111",
            command=self._iniciar,
        )
        self.btn_iniciar.pack(side="left", padx=(0, 10))

        self.btn_detener = ctk.CTkButton(
            btn_frame, text="⏹  Detener", height=42,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT_RED, hover_color="#c0392b", state="disabled",
            command=self._detener,
        )
        self.btn_detener.pack(side="left")

    def _log_safe(self, msg):
        self.after(0, lambda: self.log_fn(msg))

    def _progress_safe(self, cur, tot):
        def _update():
            pct = cur / tot if tot > 0 else 0
            self.progress_bar.set(pct)
            self.label_pct.configure(text=f"{int(pct * 100)}%")
            self.label_progreso.configure(text=f"[{cur}/{tot}] procesados")
        self.after(0, _update)

    def _cargar_handle_desde_config(self):
        config = self.get_config()
        self.col_uuid = config.get("DSPACE_COLLECTION_UUID", "")
        self.col_handle = config.get("DSPACE_COLLECTION_HANDLE", "")
        if self.col_uuid:
            self.col_var.set(f"UUID guardado: {self.col_uuid[:8]}...")
            self._actualizar_estado_lbl()

    def _cargar_colecciones_export(self):
        config = self.get_config()
        url = config.get("DSPACE_URL", "").strip()
        
        if not url:
            messagebox.showwarning("Aviso", "Ingresa primero la URL del Servidor API en Ajustes.")
            return
            
        self.btn_cargar_cols.configure(state="disabled", text="...")
        
        def _run():
            try:
                import requests
                resp = requests.get(f"{url}/core/collections?size=100")
                if resp.status_code == 200:
                    data = resp.json()
                    cols = data.get("_embedded", {}).get("collections", [])
                    self.after(0, lambda: self._mostrar_cols(cols))
                else:
                    self._log_safe(f"Error HTTP {resp.status_code}")
                    self.after(0, lambda: self.btn_cargar_cols.configure(state="normal", text="🔄 Cargar"))
            except Exception as e:
                self._log_safe(f"Error cargando colecciones: {e}")
                self.after(0, lambda: self.btn_cargar_cols.configure(state="normal", text="🔄 Cargar"))
                
        threading.Thread(target=_run, daemon=True).start()

    def _mostrar_cols(self, cols):
        self._colecciones_export = cols
        self.btn_cargar_cols.configure(state="normal", text="🔄 Cargar")
        if not cols:
            messagebox.showwarning("Aviso", "No se encontraron colecciones.")
            return
            
        nombres = [c['name'] for c in cols]
        self.dropdown_cols.configure(values=nombres)
        
        encontrado = False
        for c in cols:
            if c['uuid'] == self.col_uuid:
                self.col_var.set(c['name'])
                encontrado = True
                break
        
        if not encontrado:
            self.col_var.set(nombres[0])
            self._on_col_select(nombres[0])

    def _on_col_select(self, val):
        for c in self._colecciones_export:
            if c['name'] == val:
                self.col_uuid = c['uuid']
                self.col_handle = c['handle']
                set_key(ENV_PATH, "DSPACE_COLLECTION_UUID", self.col_uuid)
                set_key(ENV_PATH, "DSPACE_COLLECTION_HANDLE", self.col_handle)
                self._actualizar_estado_lbl()
                break

    def _actualizar_estado_lbl(self):
        config = self.get_config()
        url = config.get("DSPACE_URL", "")
        if not url:
            self.label_api_status.configure(
                text="❌ Falta configurar la URL del Servidor en ⚙️ Ajustes",
                text_color=ACCENT_RED,
            )
        elif not self.col_uuid:
            self.label_api_status.configure(
                text="❌ Por favor selecciona una Colección Destino en el bloque superior 👆",
                text_color=ACCENT_RED,
            )
        else:
            self.label_api_status.configure(
                text=f"✅ Servidor: {url}  |  Colección: {self.col_uuid[:18]}...",
                text_color=ACCENT,
            )

    def actualizar_estado(self):
        """Llamada al cambiar a esta sección."""
        self._actualizar_estado_lbl()
        self._cargar_items_preview()

    def _cargar_items_preview(self):
        """Carga los ítems del CSV catalogado para mostrarlos en el Preview."""
        pdir, _ = self.get_proyecto()
        if not pdir or not os.path.exists(pdir):
            # Fallback: buscar si hay un proyecto en workspace_local
            base_dir = ROOT_DIR
            ws_dir = os.path.join(base_dir, "workspace_local")
            if os.path.exists(ws_dir):
                subdirs = [os.path.join(ws_dir, d) for d in os.listdir(ws_dir) if os.path.isdir(os.path.join(ws_dir, d))]
                if subdirs:
                    pdir = subdirs[0]

        if not pdir or not os.path.exists(pdir):
            self._preview_items = []
            self._mostrar_preview(0)
            return

        csv_salida = os.path.join(pdir, "Catalogo_OpenAI_Completo.csv")
        csv_base_files = [
            f for f in os.listdir(pdir)
            if f.lower().endswith('.csv') and not f.startswith('Catalogo_OpenAI')
        ]

        ruta_csv = None
        if os.path.exists(csv_salida):
            ruta_csv = csv_salida
        elif csv_base_files:
            ruta_csv = os.path.join(pdir, csv_base_files[0])

        if not ruta_csv or not os.path.exists(ruta_csv):
            self._preview_items = []
            self._mostrar_preview(0)
            return

        df = None
        for enc in ['utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(ruta_csv, dtype=str, encoding=enc, sep=None, engine='python')
                break
            except Exception:
                continue

        if df is None:
            self._preview_items = []
            self._mostrar_preview(0)
            return

        df.columns = [c.strip() for c in df.columns]
        col_archivo = next(
            (c for c in df.columns if c.lower() in ['nombre archivo', 'filename', 'nombre_archivo', 'archivo', 'nombre']),
            None
        )

        if not col_archivo:
            self._preview_items = []
            self._mostrar_preview(0)
            return

        items = []
        for _, row in df.iterrows():
            fname = str(row.get(col_archivo, '')).strip()
            if not fname or fname == 'nan':
                continue

            # Buscar foto
            foto_path = os.path.join(pdir, fname)
            if not os.path.exists(foto_path):
                foto_path = os.path.join(pdir, "Fotos", fname)
                if not os.path.exists(foto_path):
                    foto_path = None

            filesize_str = '-'
            if foto_path and os.path.exists(foto_path):
                sz = os.path.getsize(foto_path) / (1024 * 1024)
                filesize_str = f"{sz:.2f} MB"
            elif row.get('dc.format.medium'):
                filesize_str = str(row.get('dc.format.medium'))

            dc_meta = {}
            fia_meta = {}
            other_meta = {}

            for col in df.columns:
                val = str(row.get(col, '')).strip()
                if not val or val == 'nan' or col == col_archivo:
                    continue
                if col.startswith('dc.'):
                    dc_meta[col] = val
                elif col.startswith('fia.'):
                    fia_meta[col] = val
                else:
                    other_meta[col] = val

            items.append({
                'filename': fname,
                'foto_path': foto_path,
                'filesize': filesize_str,
                'extent': str(row.get('dc.format.extent', '') or '').strip(),
                'entity': str(row.get('dspace.entity.type', '') or '').strip(),
                'dc': dc_meta,
                'fia': fia_meta,
                'other': other_meta,
            })

        self._preview_items = items
        if items:
            filenames = [f"{i+1}. {it['filename']}" for i, it in enumerate(items)]
            self.combo_preview_jump.configure(values=filenames)
            self.combo_preview_jump.set(filenames[0])
            self.log_fn(f"👁️ Vista previa: {len(items)} fotos y metadatos cargados.")
        else:
            self.combo_preview_jump.configure(values=["-- Sin fotos --"])
            self.combo_preview_jump.set("-- Sin fotos --")
            self.log_fn("⚠️ Vista previa: No se encontraron registros para mostrar.")

        self._mostrar_preview(self._preview_idx if self._preview_idx < len(items) else 0)

    def _mostrar_preview(self, idx):
        """Muestra el ítem actual en el visualizador con todos sus metadatos."""
        # Limpiar scroll de metadatos
        for w in self.scroll_metadata.winfo_children():
            w.destroy()

        if not self._preview_items:
            self.label_preview_pos.configure(text="0 de 0")
            self.label_preview_file.configure(text="-")
            self.label_preview_filesize.configure(text="⚖️ Peso: -")
            self.label_preview_dims.configure(text="📐 Resolución: -")
            self.label_preview_entity.configure(text="🏛️ Entidad: -")
            self.label_preview_img.configure(image=None, text="Sin datos catalogados")
            ctk.CTkLabel(
                self.scroll_metadata, text="No hay registros para mostrar. Carga un proyecto en 📂 Proyecto.",
                font=(FONT_FAMILY, 12), text_color="#666",
            ).pack(pady=40)
            return

        idx = max(0, min(idx, len(self._preview_items) - 1))
        self._preview_idx = idx
        item = self._preview_items[idx]

        self.label_preview_pos.configure(text=f"{idx + 1} de {len(self._preview_items)}")
        if hasattr(self, 'combo_preview_jump'):
            vals = self.combo_preview_jump.cget("values")
            if idx < len(vals):
                self.combo_preview_jump.set(vals[idx])

        self.label_preview_file.configure(text=item['filename'])
        self.label_preview_filesize.configure(text=f"⚖️ Peso: {item['filesize']}")
        self.label_preview_dims.configure(text=f"📐 Res: {item['extent'] or '-'}")
        self.label_preview_entity.configure(text=f"🏛️ Entidad: {item['entity'] or 'Fotografía'}")

        # Cargar foto en la miniatura
        foto_path = item.get('foto_path')
        if foto_path and os.path.exists(foto_path):
            try:
                pil_img = Image.open(foto_path)
                pil_img.thumbnail((210, 155))
                self._curr_ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
                self.label_preview_img.configure(image=self._curr_ctk_img, text="")
            except Exception:
                self.label_preview_img.configure(image=None, text="Error cargando foto")
        else:
            self.label_preview_img.configure(image=None, text="Foto no encontrada")

        # ── Renderizar TODOS los metadatos en el panel derecho ──
        def _render_section(titulo, color, metadatos_dict):
            if not metadatos_dict:
                return
            # Encabezado de sección
            sec_header = ctk.CTkFrame(self.scroll_metadata, fg_color="#18182c", corner_radius=5)
            sec_header.pack(fill="x", pady=(8, 4))
            ctk.CTkLabel(
                sec_header, text=titulo, font=(FONT_FAMILY, 11, "bold"), text_color=color, anchor="w",
            ).pack(fill="x", padx=8, pady=3)

            for key, val in metadatos_dict.items():
                row_f = ctk.CTkFrame(self.scroll_metadata, fg_color="transparent")
                row_f.pack(fill="x", pady=2, padx=4)

                # Clave
                ctk.CTkLabel(
                    row_f, text=f"{key}:", font=(FONT_FAMILY, 10, "bold"),
                    text_color="#888", width=140, anchor="nw", justify="left",
                ).pack(side="left", anchor="nw")

                # Si es multivaluado con ||
                if '||' in val or '| |' in val:
                    val_limpio = val.replace('| |', '||')
                    pills = [v.strip() for v in val_limpio.split('||') if v.strip()]
                    pills_f = ctk.CTkFrame(row_f, fg_color="transparent")
                    pills_f.pack(side="left", fill="x", expand=True)
                    
                    curr_line = None
                    curr_len = 0
                    max_len_per_line = 44  # Límite de caracteres antes de hacer salto de línea

                    for p in pills:
                        p_len = len(p) + 4
                        if curr_line is None or (curr_len + p_len > max_len_per_line and curr_len > 0):
                            curr_line = ctk.CTkFrame(pills_f, fg_color="transparent")
                            curr_line.pack(fill="x", anchor="w", pady=1)
                            curr_len = 0

                        pill = ctk.CTkFrame(curr_line, fg_color="#1c1c36", corner_radius=5)
                        pill.pack(side="left", padx=(0, 4), pady=2)
                        ctk.CTkLabel(
                            pill, text=f"🏷️ {p}", font=(FONT_FAMILY, 9, "bold"), text_color=ACCENT,
                        ).pack(padx=6, pady=2)
                        curr_len += p_len
                else:
                    ctk.CTkLabel(
                        row_f, text=val, font=(FONT_FAMILY, 11),
                        text_color="#e0e0e0" if key in ['dc.title', 'dc.description'] else "#b0b0b0",
                        wraplength=440, justify="left", anchor="w",
                    ).pack(side="left", fill="x", expand=True)

        _render_section("🏛️  Metadatos Dublin Core (dc.*)", ACCENT, item['dc'])
        _render_section("🌾  Metadatos FIA (fia.*)", "#38bdf8", item['fia'])
        _render_section("📦  Otros Campos", "#a78bfa", item['other'])

    def _prev_preview(self):
        if self._preview_items:
            self._mostrar_preview(self._preview_idx - 1)

    def _next_preview(self):
        if self._preview_items:
            self._mostrar_preview(self._preview_idx + 1)

    def _on_jump_select(self, val):
        if not self._preview_items or not val:
            return
        try:
            # val viene con formato "1. Almacigos_1.jpg"
            idx = int(val.split('.')[0]) - 1
            self._mostrar_preview(idx)
        except Exception:
            pass

    def _toggle_preview(self):
        """Plegar o desplegar el panel del Preview."""
        if self._preview_visible:
            self.prev_body.pack_forget()
            self.btn_toggle_preview.configure(text="▶ Desplegar", fg_color=ACCENT, text_color="#000")
            self._preview_visible = False
        else:
            self.prev_body.pack(fill="x", padx=15, pady=(0, 12))
            self.btn_toggle_preview.configure(text="🔽 Plegar", fg_color="#333", text_color="#fff")
            self._preview_visible = True

    def _iniciar(self):
        pdir, nombre = self.get_proyecto()
        if not pdir:
            messagebox.showwarning("Advertencia", "Carga un proyecto primero en 📂 Proyecto.")
            return

        modo = self.modo_var.get()

        if modo == "api":
            self._iniciar_api(pdir)
        else:
            self._iniciar_saf(pdir)

    def _iniciar_api(self, pdir):
        config = self.get_config()
        url = config.get("DSPACE_URL", "")
        email = config.get("DSPACE_EMAIL", "")
        pwd = config.get("DSPACE_PASSWORD", "")
        uuid = self.col_uuid

        if not all([url, email, pwd]):
            messagebox.showerror("Error", "Completa las credenciales de DSpace en ⚙️ Ajustes.")
            return
            
        if not uuid:
            messagebox.showerror("Error", "Selecciona una Colección Destino arriba.")
            return

        if not messagebox.askyesno(
            "Confirmar importación",
            "¿Deseas iniciar la carga a DSpace?\n\n"
            "Los ítems se crearán como BORRADORES.\n"
            "Esta acción no se puede deshacer fácilmente.",
        ):
            return

        self._running = True
        self.btn_iniciar.configure(state="disabled")
        self.btn_detener.configure(state="normal")
        self.progress_bar.set(0)

        limpiar = self.check_limpiar.get() == 1

        def _run():
            try:
                self.importador = ImportadorDSpace(
                    dspace_url=url, email=email, password=pwd,
                    collection_uuid=uuid,
                    log=self._log_safe, progress=self._progress_safe,
                )
                ok, err = self.importador.importar(pdir, limpiar_al_terminar=limpiar)
                if ok > 0:
                    self._log_safe(f"🎉 Importación completada: {ok} exitosos, {err} con error.")
                self.after(0, self._finalizar)
            except Exception as e:
                self._log_safe(f"❌ Error inesperado: {e}")
                self.after(0, self._finalizar)

        threading.Thread(target=_run, daemon=True).start()

    def _iniciar_saf(self, pdir):
        handle = self.col_handle
        if not handle:
            messagebox.showerror("Error", "Selecciona una Colección Destino arriba.")
            return

        self._running = True
        self.btn_iniciar.configure(state="disabled")
        self.btn_detener.configure(state="normal")
        self.progress_bar.set(0)

        def _run():
            try:
                self.saf_builder = SAFBuilder(
                    log=self._log_safe, progress=self._progress_safe,
                )
                ok = self.saf_builder.generar_saf(pdir, coleccion_handle=handle)
                if ok:
                    self._log_safe("🎉 ¡Paquete SAF generado exitosamente!")
                self.after(0, self._finalizar)
            except Exception as e:
                self._log_safe(f"❌ Error inesperado: {e}")
                self.after(0, self._finalizar)

        threading.Thread(target=_run, daemon=True).start()

    def _detener(self):
        if self.importador:
            self.importador.cancelar()
        if self.saf_builder:
            self.saf_builder.cancelar()
        self.log_fn("Solicitando detención...")

    def _finalizar(self):
        self._running = False
        self.btn_iniciar.configure(state="normal")
        self.btn_detener.configure(state="disabled")


# ══════════════════════════════════════════════════════════════
# Frame: Relaciones
# ══════════════════════════════════════════════════════════════

class RelacionesFrame(ctk.CTkScrollableFrame):
    """Sección para vincular ítems publicados en DSpace."""

    def __init__(self, parent, log_fn, get_config, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.log_fn = log_fn
        self.get_config = get_config
        self.relacionador = None
        self._running = False

        # Data
        self.rel_types = []
        self.colecciones = []
        self.datos_cargados = False

        # Origen
        self.origen_items = []
        self.origen_page = 0
        self.origen_total_pages = 0
        self.origen_total_elements = 0
        self.origen_seleccionados = set()
        self.origen_checkboxes = []

        # Destino
        self.destino_items = []
        self.destino_page = 0
        self.destino_total_pages = 0
        self.destino_total_elements = 0
        self.destino_seleccionado = None
        self.destino_titulo = ""

        # Preview
        self.ya_vinculados = set()
        self.items_a_vincular = []

        self._crear_ui()

    def _crear_ui(self):
        ctk.CTkLabel(
            self, text="🔗  Relaciones",
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w", padx=20, pady=(20, 5))
        ctk.CTkLabel(
            self, text="Vincula ítems publicados en DSpace entre sí",
            font=(FONT_FAMILY, 13), text_color="#888",
        ).pack(anchor="w", padx=20, pady=(0, 15))

        # ── Botón conectar ──
        self.btn_conectar = ctk.CTkButton(
            self, text="🔄  Conectar a DSpace y cargar datos", height=40,
            font=(FONT_FAMILY, 13, "bold"),
            fg_color="#2a4a7f", hover_color="#345a9f",
            command=self._conectar_y_cargar,
        )
        self.btn_conectar.pack(anchor="w", padx=20, pady=(0, 15))

        self.label_estado = ctk.CTkLabel(
            self, text="", font=(FONT_FAMILY, 12), text_color="#888",
        )
        self.label_estado.pack(anchor="w", padx=20)

        # ── Card 1: Tipo de relación ──
        card1 = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card1.pack(fill="x", padx=20, pady=(10, 10))

        ctk.CTkLabel(
            card1, text="📋  Tipo de relación",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 8))

        self.rel_type_var = ctk.StringVar(value="(conectar primero)")
        self.dropdown_rel_type = ctk.CTkOptionMenu(
            card1, variable=self.rel_type_var,
            values=["(conectar primero)"],
            font=(FONT_FAMILY, 12),
            fg_color="#333", button_color="#444",
            dropdown_fg_color="#2a2a3e", width=350,
            command=self._on_rel_type_change,
        )
        self.dropdown_rel_type.pack(anchor="w", padx=15, pady=(0, 12))

        # ── Card 2: Ítems origen ──
        card2 = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card2.pack(fill="x", padx=20, pady=(0, 10))

        self.label_origen_titulo = ctk.CTkLabel(
            card2, text="📦  Ítems a vincular (origen)",
            font=(FONT_FAMILY, 14, "bold"),
        )
        self.label_origen_titulo.pack(anchor="w", padx=15, pady=(12, 8))

        row_o = ctk.CTkFrame(card2, fg_color="transparent")
        row_o.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(row_o, text="Colección:", font=(FONT_FAMILY, 12)).pack(side="left")
        self.origen_col_var = ctk.StringVar(value="(conectar primero)")
        self.dropdown_origen_col = ctk.CTkOptionMenu(
            row_o, variable=self.origen_col_var,
            values=["(conectar primero)"],
            font=(FONT_FAMILY, 12),
            fg_color="#333", button_color="#444",
            dropdown_fg_color="#2a2a3e", width=220,
        )
        self.dropdown_origen_col.pack(side="left", padx=(8, 8))

        self.entry_origen_buscar = ctk.CTkEntry(
            row_o, placeholder_text="🔍 Buscar (ej. fia.clasificacionlocal:...)", 
            width=240, font=(FONT_FAMILY, 12),
        )
        self.entry_origen_buscar.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row_o, text="🔄 Cargar", width=90, height=32,
            font=(FONT_FAMILY, 12), fg_color="#333", hover_color="#444",
            command=self._cargar_items_origen,
        ).pack(side="left")

        self.origen_lista_frame = ctk.CTkScrollableFrame(
            card2, height=180, fg_color="#1a1a2e", corner_radius=6,
        )
        self.origen_lista_frame.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            self.origen_lista_frame,
            text="  Selecciona una colección y haz clic en Cargar",
            font=(FONT_FAMILY, 12), text_color="#666",
        ).pack(anchor="w", pady=10)

        pag_o = ctk.CTkFrame(card2, fg_color="transparent")
        pag_o.pack(fill="x", padx=15, pady=(0, 5))

        self.btn_origen_prev = ctk.CTkButton(
            pag_o, text="◀", width=35, height=28,
            fg_color="#333", hover_color="#444",
            command=lambda: self._paginar_origen(-1), state="disabled",
        )
        self.btn_origen_prev.pack(side="left")

        self.label_origen_pag = ctk.CTkLabel(
            pag_o, text="", font=(FONT_FAMILY, 11), text_color="#888",
        )
        self.label_origen_pag.pack(side="left", padx=10)

        self.btn_origen_next = ctk.CTkButton(
            pag_o, text="▶", width=35, height=28,
            fg_color="#333", hover_color="#444",
            command=lambda: self._paginar_origen(1), state="disabled",
        )
        self.btn_origen_next.pack(side="left")

        self.btn_sel_todo_busqueda = ctk.CTkButton(
            pag_o, text="☑ Seleccionar todo (todas las págs)", width=200, height=28,
            font=(FONT_FAMILY, 11, "bold"), fg_color="#2a4a7f", hover_color="#345a9f",
            command=self._seleccionar_todo_masivo,
        )
        self.btn_sel_todo_busqueda.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            pag_o, text="☑ Seleccionar página", width=140, height=28,
            font=(FONT_FAMILY, 11), fg_color="#333", hover_color="#444",
            command=self._seleccionar_todos_pagina,
        ).pack(side="right")

        self.label_origen_sel = ctk.CTkLabel(
            card2, text="Seleccionados: 0",
            font=(FONT_FAMILY, 12), text_color="#aaa",
        )
        self.label_origen_sel.pack(anchor="w", padx=15, pady=(0, 12))

        # ── Card 3: Ítem destino ──
        card3 = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card3.pack(fill="x", padx=20, pady=(0, 10))

        self.label_destino_titulo = ctk.CTkLabel(
            card3, text="🎯  Ítem destino",
            font=(FONT_FAMILY, 14, "bold"),
        )
        self.label_destino_titulo.pack(anchor="w", padx=15, pady=(12, 8))

        row_d = ctk.CTkFrame(card3, fg_color="transparent")
        row_d.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(row_d, text="Colección:", font=(FONT_FAMILY, 12)).pack(side="left")
        self.destino_col_var = ctk.StringVar(value="(conectar primero)")
        self.dropdown_destino_col = ctk.CTkOptionMenu(
            row_d, variable=self.destino_col_var,
            values=["(conectar primero)"],
            font=(FONT_FAMILY, 12),
            fg_color="#333", button_color="#444",
            dropdown_fg_color="#2a2a3e", width=220,
        )
        self.dropdown_destino_col.pack(side="left", padx=(8, 8))

        self.entry_destino_buscar = ctk.CTkEntry(
            row_d, placeholder_text="🔍 Buscar (ej. código FIA)", 
            width=240, font=(FONT_FAMILY, 12),
        )
        self.entry_destino_buscar.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            row_d, text="🔄 Cargar", width=90, height=32,
            font=(FONT_FAMILY, 12), fg_color="#333", hover_color="#444",
            command=self._cargar_items_destino,
        ).pack(side="left")

        self.destino_lista_frame = ctk.CTkScrollableFrame(
            card3, height=150, fg_color="#1a1a2e", corner_radius=6,
        )
        self.destino_lista_frame.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            self.destino_lista_frame,
            text="  Selecciona una colección y haz clic en Cargar",
            font=(FONT_FAMILY, 12), text_color="#666",
        ).pack(anchor="w", pady=10)

        pag_d = ctk.CTkFrame(card3, fg_color="transparent")
        pag_d.pack(fill="x", padx=15, pady=(0, 5))

        self.btn_destino_prev = ctk.CTkButton(
            pag_d, text="◀", width=35, height=28,
            fg_color="#333", hover_color="#444",
            command=lambda: self._paginar_destino(-1), state="disabled",
        )
        self.btn_destino_prev.pack(side="left")

        self.label_destino_pag = ctk.CTkLabel(
            pag_d, text="", font=(FONT_FAMILY, 11), text_color="#888",
        )
        self.label_destino_pag.pack(side="left", padx=10)

        self.btn_destino_next = ctk.CTkButton(
            pag_d, text="▶", width=35, height=28,
            fg_color="#333", hover_color="#444",
            command=lambda: self._paginar_destino(1), state="disabled",
        )
        self.btn_destino_next.pack(side="left")

        self.label_destino_sel = ctk.CTkLabel(
            card3, text="Seleccionado: (ninguno)",
            font=(FONT_FAMILY, 12), text_color="#aaa",
        )
        self.label_destino_sel.pack(anchor="w", padx=15, pady=(0, 12))

        # ── Card 4: Preview / Ejecutar ──
        card4 = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=10)
        card4.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            card4, text="👁️  Preview y ejecución",
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(anchor="w", padx=15, pady=(12, 8))

        ctk.CTkButton(
            card4, text="👁️  Generar Preview", height=36,
            font=(FONT_FAMILY, 13),
            fg_color="#2a4a7f", hover_color="#345a9f",
            command=self._generar_preview,
        ).pack(anchor="w", padx=15, pady=(0, 8))

        self.preview_frame = ctk.CTkScrollableFrame(
            card4, height=150, fg_color="#1a1a2e", corner_radius=6,
        )
        self.preview_frame.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            self.preview_frame,
            text="  Haz clic en Generar Preview para ver las relaciones",
            font=(FONT_FAMILY, 12), text_color="#666",
        ).pack(anchor="w", pady=10)

        self.label_preview_resumen = ctk.CTkLabel(
            card4, text="", font=(FONT_FAMILY, 12), text_color="#aaa",
        )
        self.label_preview_resumen.pack(anchor="w", padx=15, pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(card4, height=8)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 5))
        self.progress_bar.set(0)

        row_btns = ctk.CTkFrame(card4, fg_color="transparent")
        row_btns.pack(fill="x", padx=15, pady=(0, 12))

        self.btn_ejecutar = ctk.CTkButton(
            row_btns, text="🔗  Crear Relaciones", height=40,
            font=(FONT_FAMILY, 14, "bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#111",
            command=self._ejecutar, state="disabled",
        )
        self.btn_ejecutar.pack(side="left")

        self.btn_detener = ctk.CTkButton(
            row_btns, text="⏹ Detener", height=40, width=100,
            font=(FONT_FAMILY, 13),
            fg_color="#8b0000", hover_color="#a00000",
            command=self._detener, state="disabled",
        )
        self.btn_detener.pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------
    # Conectar y cargar datos (solo GETs)
    # ------------------------------------------------------------------

    def _conectar_y_cargar(self):
        config = self.get_config()
        url = config.get("DSPACE_URL", "").strip()
        if not url:
            messagebox.showwarning(
                "Advertencia", "Configura la URL de DSpace en Ajustes."
            )
            return

        self.btn_conectar.configure(state="disabled", text="Cargando...")
        self.label_estado.configure(
            text="Conectando a DSpace...", text_color="#aaa"
        )

        def _run():
            try:
                rel = RelacionadorDSpace(
                    dspace_url=url,
                    email=config.get("DSPACE_EMAIL", ""),
                    password=config.get("DSPACE_PASSWORD", ""),
                    log=self._log_safe,
                )
                self.relacionador = rel
                rt = rel.obtener_relationship_types()
                cols = rel.obtener_colecciones()
                self.after(0, lambda: self._datos_cargados(rt, cols))
            except Exception as e:
                self._log_safe(f"❌ Error: {e}")
                self.after(0, lambda: self.btn_conectar.configure(
                    state="normal",
                    text="🔄  Conectar a DSpace y cargar datos",
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _datos_cargados(self, rel_types, colecciones):
        self.rel_types = rel_types
        self.colecciones = colecciones
        self.datos_cargados = True

        if rel_types:
            displays = [rt['display'] for rt in rel_types]
            self.dropdown_rel_type.configure(values=displays)
            self.rel_type_var.set(displays[0])

        if colecciones:
            nombres = [c['name'] for c in colecciones]
            self.dropdown_origen_col.configure(values=nombres)
            self.origen_col_var.set(nombres[0])
            self.dropdown_destino_col.configure(values=nombres)
            self.destino_col_var.set(nombres[0])

        self.btn_conectar.configure(
            state="normal", text="✅  Datos cargados — Reconectar",
        )
        self.label_estado.configure(
            text=(f"{len(rel_types)} tipos de relación, "
                  f"{len(colecciones)} colecciones"),
            text_color="#6c6",
        )
        self.log_fn(
            f"Datos cargados: {len(rel_types)} tipos, "
            f"{len(colecciones)} colecciones"
        )
        self._on_rel_type_change(None)

    # ------------------------------------------------------------------
    # Tipo de relación
    # ------------------------------------------------------------------

    def _on_rel_type_change(self, _):
        rt = self._get_selected_rel_type()
        if not rt:
            return
        self.label_origen_titulo.configure(
            text=f"📦  {rt['left_label']}s a vincular (origen)"
        )
        self.label_destino_titulo.configure(
            text=f"🎯  {rt['right_label']} destino"
        )

    def _get_selected_rel_type(self):
        display = self.rel_type_var.get()
        for rt in self.rel_types:
            if rt['display'] == display:
                return rt
        return None

    def _get_col_uuid(self, col_name):
        for c in self.colecciones:
            if c['name'] == col_name:
                return c['uuid']
        return None

    # ------------------------------------------------------------------
    # Ítems ORIGEN (solo lectura)
    # ------------------------------------------------------------------

    def _cargar_items_origen(self):
        if not self.datos_cargados or not self.relacionador:
            return
        col_uuid = self._get_col_uuid(self.origen_col_var.get())
        if not col_uuid:
            return
        self.origen_page = 0
        self.origen_seleccionados.clear()
        query = self.entry_origen_buscar.get().strip()

        def _run():
            items, total, pages = self.relacionador.obtener_items_coleccion(
                col_uuid, page=0, size=20, query=query
            )
            self.after(
                0, lambda: self._mostrar_items_origen(items, total, pages)
            )

        threading.Thread(target=_run, daemon=True).start()

    def _paginar_origen(self, delta):
        new_page = self.origen_page + delta
        if new_page < 0 or new_page >= self.origen_total_pages:
            return
        self._guardar_seleccion_origen()
        self.origen_page = new_page
        col_uuid = self._get_col_uuid(self.origen_col_var.get())
        query = self.entry_origen_buscar.get().strip()

        def _run():
            items, total, pages = self.relacionador.obtener_items_coleccion(
                col_uuid, page=new_page, size=20, query=query
            )
            self.after(
                0, lambda: self._mostrar_items_origen(items, total, pages)
            )

        threading.Thread(target=_run, daemon=True).start()

    def _mostrar_items_origen(self, items, total, pages):
        self.origen_items = items
        self.origen_total_pages = pages
        self.origen_total_elements = total

        for w in self.origen_lista_frame.winfo_children():
            w.destroy()
        self.origen_checkboxes = []

        if not items:
            ctk.CTkLabel(
                self.origen_lista_frame,
                text="  Sin ítems en esta colección",
                font=(FONT_FAMILY, 12), text_color="#666",
            ).pack(anchor="w", pady=10)
        else:
            for item in items:
                is_sel = item['uuid'] in self.origen_seleccionados
                var = ctk.IntVar(value=1 if is_sel else 0)
                row = ctk.CTkFrame(
                    self.origen_lista_frame, fg_color="transparent"
                )
                row.pack(fill="x", pady=1)
                t = item['title']
                t_short = t[:65] + "..." if len(t) > 65 else t
                cb = ctk.CTkCheckBox(
                    row, text=f"  {t_short}",
                    variable=var, font=(FONT_FAMILY, 11),
                    checkbox_width=18, checkbox_height=18,
                    command=lambda u=item['uuid'], v=var: (
                        self._toggle_origen(u, v)
                    ),
                )
                cb.pack(side="left", fill="x", expand=True)
                if item.get('entity_type'):
                    ctk.CTkLabel(
                        row, text=item['entity_type'],
                        font=(FONT_FAMILY, 10), text_color="#666",
                        width=80,
                    ).pack(side="right", padx=5)
                self.origen_checkboxes.append((item['uuid'], var))

        self.label_origen_pag.configure(
            text=f"Página {self.origen_page + 1} de {pages}  ({total} ítems)"
        )
        self.btn_origen_prev.configure(
            state="normal" if self.origen_page > 0 else "disabled"
        )
        self.btn_origen_next.configure(
            state="normal" if self.origen_page < pages - 1 else "disabled"
        )
        self._actualizar_contador_origen()

    def _toggle_origen(self, uuid, var):
        if var.get():
            self.origen_seleccionados.add(uuid)
        else:
            self.origen_seleccionados.discard(uuid)
        self._actualizar_contador_origen()

    def _guardar_seleccion_origen(self):
        for uuid, var in self.origen_checkboxes:
            if var.get():
                self.origen_seleccionados.add(uuid)
            else:
                self.origen_seleccionados.discard(uuid)

    def _seleccionar_todos_pagina(self):
        for uuid, var in self.origen_checkboxes:
            var.set(1)
            self.origen_seleccionados.add(uuid)
        self._actualizar_contador_origen()

    def _actualizar_contador_origen(self):
        self._guardar_seleccion_origen()
        n = len(self.origen_seleccionados)
        self.label_origen_sel.configure(text=f"Seleccionados: {n}")

    def _seleccionar_todo_masivo(self):
        if not self.datos_cargados or not self.relacionador:
            return
        col_uuid = self._get_col_uuid(self.origen_col_var.get())
        if not col_uuid:
            return

        query = self.entry_origen_buscar.get().strip()
        self.btn_sel_todo_busqueda.configure(state="disabled", text="Cargando...")

        def _run():
            try:
                uuids = self.relacionador.obtener_uuids_busqueda(col_uuid, query)
                self.after(0, lambda: self._aplicar_seleccion_masiva(uuids))
            except Exception as e:
                self._log_safe(f"Error seleccionando todo: {e}")
                self.after(0, lambda: self.btn_sel_todo_busqueda.configure(
                    state="normal", text="☑ Seleccionar todo (todas las págs)"
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _aplicar_seleccion_masiva(self, uuids):
        self.origen_seleccionados.update(uuids)
        # Actualizar visualmente la página actual
        for u, var in self.origen_checkboxes:
            if u in self.origen_seleccionados:
                var.set(1)
        self._actualizar_contador_origen()
        self.btn_sel_todo_busqueda.configure(
            state="normal", text="☑ Seleccionar todo (todas las págs)"
        )

    # ------------------------------------------------------------------
    # Ítems DESTINO (solo lectura)
    # ------------------------------------------------------------------

    def _cargar_items_destino(self):
        if not self.datos_cargados or not self.relacionador:
            return
        col_uuid = self._get_col_uuid(self.destino_col_var.get())
        if not col_uuid:
            return
        self.destino_page = 0
        self.destino_seleccionado = None
        self.destino_titulo = ""
        query = self.entry_destino_buscar.get().strip()

        def _run():
            items, total, pages = self.relacionador.obtener_items_coleccion(
                col_uuid, page=0, size=20, query=query
            )
            self.after(
                0, lambda: self._mostrar_items_destino(items, total, pages)
            )

        threading.Thread(target=_run, daemon=True).start()

    def _paginar_destino(self, delta):
        new_page = self.destino_page + delta
        if new_page < 0 or new_page >= self.destino_total_pages:
            return
        self.destino_page = new_page
        col_uuid = self._get_col_uuid(self.destino_col_var.get())
        query = self.entry_destino_buscar.get().strip()

        def _run():
            items, total, pages = self.relacionador.obtener_items_coleccion(
                col_uuid, page=new_page, size=20, query=query
            )
            self.after(
                0, lambda: self._mostrar_items_destino(items, total, pages)
            )

        threading.Thread(target=_run, daemon=True).start()

    def _mostrar_items_destino(self, items, total, pages):
        self.destino_items = items
        self.destino_total_pages = pages
        self.destino_total_elements = total

        for w in self.destino_lista_frame.winfo_children():
            w.destroy()

        if not items:
            ctk.CTkLabel(
                self.destino_lista_frame,
                text="  Sin ítems en esta colección",
                font=(FONT_FAMILY, 12), text_color="#666",
            ).pack(anchor="w", pady=10)
        else:
            self._destino_radio_var = ctk.StringVar(
                value=self.destino_seleccionado or ""
            )
            for item in items:
                row = ctk.CTkFrame(
                    self.destino_lista_frame, fg_color="transparent"
                )
                row.pack(fill="x", pady=1)
                t = item['title']
                t_short = t[:65] + "..." if len(t) > 65 else t
                rb = ctk.CTkRadioButton(
                    row, text=f"  {t_short}",
                    variable=self._destino_radio_var,
                    value=item['uuid'],
                    font=(FONT_FAMILY, 11),
                    command=lambda u=item['uuid'], ti=item['title']: (
                        self._seleccionar_destino(u, ti)
                    ),
                )
                rb.pack(side="left", fill="x", expand=True)
                if item.get('entity_type'):
                    ctk.CTkLabel(
                        row, text=item['entity_type'],
                        font=(FONT_FAMILY, 10), text_color="#666",
                        width=80,
                    ).pack(side="right", padx=5)

        self.label_destino_pag.configure(
            text=f"Página {self.destino_page + 1} de {pages}  ({total} ítems)"
        )
        self.btn_destino_prev.configure(
            state="normal" if self.destino_page > 0 else "disabled"
        )
        self.btn_destino_next.configure(
            state="normal" if self.destino_page < pages - 1 else "disabled"
        )

    def _seleccionar_destino(self, uuid, titulo):
        self.destino_seleccionado = uuid
        self.destino_titulo = titulo
        self.label_destino_sel.configure(
            text=f"Seleccionado: {titulo}", text_color="#6c6",
        )

    # ------------------------------------------------------------------
    # Preview (solo lectura — GET para verificar existentes)
    # ------------------------------------------------------------------

    def _generar_preview(self):
        self._guardar_seleccion_origen()
        rt = self._get_selected_rel_type()
        if not rt:
            messagebox.showwarning("Aviso", "Selecciona un tipo de relación.")
            return
        if not self.origen_seleccionados:
            messagebox.showwarning("Aviso", "Selecciona al menos un ítem.")
            return
        if not self.destino_seleccionado:
            messagebox.showwarning("Aviso", "Selecciona un ítem destino.")
            return

        self.log_fn("Verificando relaciones existentes...")

        def _run():
            ya = self.relacionador.obtener_items_ya_relacionados(
                self.destino_seleccionado, rt['id'],
            )
            self.after(0, lambda: self._mostrar_preview(ya, rt))

        threading.Thread(target=_run, daemon=True).start()

    def _mostrar_preview(self, ya_vinculados, rt):
        self.ya_vinculados = ya_vinculados
        for w in self.preview_frame.winfo_children():
            w.destroy()

        titulos = {it['uuid']: it['title'] for it in self.origen_items}
        self.items_a_vincular = []
        ya_count = 0

        for uuid in self.origen_seleccionados:
            titulo = titulos.get(uuid, uuid[:12] + "...")
            if uuid in ya_vinculados:
                ya_count += 1
                row = ctk.CTkFrame(
                    self.preview_frame, fg_color="transparent"
                )
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(
                    row, text=f"  ⚠️ {titulo[:55]}",
                    font=(FONT_FAMILY, 11), text_color="#886",
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text="ya vinculado",
                    font=(FONT_FAMILY, 10), text_color="#664",
                ).pack(side="right", padx=5)
            else:
                self.items_a_vincular.append(
                    {'uuid': uuid, 'title': titulo}
                )
                row = ctk.CTkFrame(
                    self.preview_frame, fg_color="transparent"
                )
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(
                    row, text=f"  ✅ {titulo[:55]}",
                    font=(FONT_FAMILY, 11), text_color="#ccc",
                ).pack(side="left")
                ctk.CTkLabel(
                    row,
                    text=f"→ {self.destino_titulo[:25]}",
                    font=(FONT_FAMILY, 10), text_color="#888",
                ).pack(side="right", padx=5)

        nuevas = len(self.items_a_vincular)
        self.label_preview_resumen.configure(
            text=(f"Nuevas: {nuevas}  |  Ya vinculados: {ya_count}"
                  f"  |  Tipo: {rt['display']}")
        )
        if nuevas > 0:
            self.btn_ejecutar.configure(
                state="normal",
                text=f"🔗  Crear {nuevas} Relaciones",
            )
        else:
            self.btn_ejecutar.configure(
                state="disabled", text="🔗  Crear Relaciones"
            )
        self.log_fn(f"Preview: {nuevas} nuevas, {ya_count} ya existentes")

    # ------------------------------------------------------------------
    # Ejecutar (única escritura — POST, solo con confirmación)
    # ------------------------------------------------------------------

    def _ejecutar(self):
        if not self.items_a_vincular:
            return
        n = len(self.items_a_vincular)
        ok = messagebox.askyesno(
            "Confirmar",
            f"¿Crear {n} relaciones?\n\n"
            f"Esto vinculará los ítems seleccionados "
            f"con '{self.destino_titulo}'.",
        )
        if not ok:
            return

        rt = self._get_selected_rel_type()
        if not rt:
            return

        self._running = True
        self.btn_ejecutar.configure(state="disabled")
        self.btn_detener.configure(state="normal")
        self.progress_bar.set(0)
        uuids = [item['uuid'] for item in self.items_a_vincular]

        def _progress_safe(cur, tot):
            self.after(
                0, lambda: self.progress_bar.set(cur / tot if tot else 0)
            )

        def _run():
            try:
                self.relacionador.progress = _progress_safe
                self.relacionador.crear_relaciones(
                    uuids, self.destino_seleccionado, rt['id'],
                )
                self.after(0, self._finalizar)
            except Exception as e:
                self._log_safe(f"❌ Error: {e}")
                self.after(0, self._finalizar)

        threading.Thread(target=_run, daemon=True).start()

    def _detener(self):
        if self.relacionador:
            self.relacionador.cancelar()
        self.log_fn("Solicitando detención...")

    def _finalizar(self):
        self._running = False
        self.btn_ejecutar.configure(state="normal")
        self.btn_detener.configure(state="disabled")

    def _log_safe(self, msg):
        self.after(0, lambda: self.log_fn(msg))


# ══════════════════════════════════════════════════════════════
# Aplicación principal
# ══════════════════════════════════════════════════════════════

class CatalogadorApp(ctk.CTk):
    """Ventana principal del Catalogador DSpace."""

    def __init__(self):
        super().__init__()

        # Configuración ventana
        self.title("🏛️  Catalogador DSpace")
        self.geometry("1150x780")
        self.minsize(950, 650)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Layout principal: sidebar + contenido + log
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # ── Sidebar ──
        self.sidebar = ctk.CTkFrame(
            self, width=200, fg_color=SIDEBAR_COLOR, corner_radius=0,
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)

        # Logo / título
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(25, 30))

        ctk.CTkLabel(
            logo_frame, text="🏛️", font=(FONT_FAMILY, 32),
        ).pack()
        ctk.CTkLabel(
            logo_frame, text="CATALOGADOR", font=(FONT_FAMILY, 14, "bold"),
            text_color=ACCENT,
        ).pack()
        ctk.CTkLabel(
            logo_frame, text="DSpace", font=(FONT_FAMILY, 11), text_color="#666",
        ).pack()

        # Botones de navegación
        self.nav_buttons = {}
        secciones = [
            ("proyecto", "📂  Proyecto"),
            ("catalogar", "🤖  Catalogar"),
            ("exportar", "📤  Exportar"),
            ("relaciones", "🔗  Relaciones (BETA - NO USAR)"),
        ]

        for key, label in secciones:
            btn = ctk.CTkButton(
                self.sidebar, text=label, height=44,
                font=(FONT_FAMILY, 14), anchor="w",
                fg_color="transparent", hover_color=SIDEBAR_HOVER,
                text_color="#ccc", corner_radius=8,
                command=lambda k=key: self._cambiar_seccion(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn

        # ── Ajustes al fondo de la sidebar ──
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        btn_ajustes = ctk.CTkButton(
            self.sidebar, text="⚙️  Ajustes", height=44,
            font=(FONT_FAMILY, 14), anchor="w",
            fg_color="transparent", hover_color=SIDEBAR_HOVER,
            text_color="#888", corner_radius=8,
            command=lambda: self._cambiar_seccion("ajustes"),
        )
        btn_ajustes.pack(fill="x", padx=10, pady=(0, 5), side="bottom")
        self.nav_buttons["ajustes"] = btn_ajustes

        ctk.CTkLabel(
            self.sidebar, text="v1.0.0", font=(FONT_FAMILY, 10), text_color="#444",
        ).pack(side="bottom", pady=(0, 10))

        # ── Área de contenido ──
        self.content_area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)

        # ── Consola de Log ──
        self.log_console = LogConsole(self, height=180)
        self.log_console.grid(row=1, column=1, sticky="sew", padx=10, pady=(0, 10))

        # ── Crear frames de cada sección ──
        self.frames = {}

        self.frames["ajustes"] = AjustesFrame(
            self.content_area, log_fn=self.log,
        )

        self.frames["proyecto"] = ProyectoFrame(
            self.content_area, log_fn=self.log,
        )

        self.frames["catalogar"] = CatalogarFrame(
            self.content_area, log_fn=self.log,
            get_proyecto=self._get_proyecto,
            get_config=self._get_config,
        )

        self.frames["exportar"] = ExportarFrame(
            self.content_area, log_fn=self.log,
            get_proyecto=self._get_proyecto,
            get_config=self._get_config,
        )

        self.frames["relaciones"] = RelacionesFrame(
            self.content_area, log_fn=self.log,
            get_config=self._get_config,
        )

        for frame in self.frames.values():
            frame.pack_forget()

        # Sección inicial: Proyecto es lo primero que el usuario necesita
        self._cambiar_seccion("proyecto")
        self.log("Catalogador DSpace iniciado. Configura tus ajustes para comenzar.")

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    def _cambiar_seccion(self, key):
        # Ocultar todos los frames
        for frame in self.frames.values():
            frame.pack_forget()

        # Mostrar el seleccionado
        self.frames[key].pack(fill="both", expand=True)

        # Actualizar estilo de botones
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=SIDEBAR_ACTIVE, text_color="#fff")
            else:
                btn.configure(fg_color="transparent", text_color="#ccc")

        # Hooks al cambiar de sección
        if key == "catalogar":
            self.frames["catalogar"].actualizar_stats()
        elif key == "exportar":
            self.frames["exportar"].actualizar_estado()
        elif key == "proyecto":
            self.frames["proyecto"].actualizar_estado()

        # Ajustes usa color dimmer en la sidebar
        ajustes_btn = self.nav_buttons.get("ajustes")
        if ajustes_btn and key != "ajustes":
            ajustes_btn.configure(fg_color="transparent", text_color="#888")

    # ------------------------------------------------------------------
    # Getters compartidos entre secciones
    # ------------------------------------------------------------------

    def _get_proyecto(self):
        """Retorna (proyecto_dir, nombre) del proyecto cargado, o (None, None)."""
        pf = self.frames["proyecto"]
        return pf.proyecto_dir, pf.nombre_proyecto

    def _get_config(self):
        """Retorna dict con todos los valores de configuración."""
        af = self.frames["ajustes"]
        return {key: af.obtener_valor(key) for key in af.campos}

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def log(self, mensaje):
        """Escribe en la consola de log (thread-safe)."""
        self.log_console.escribir(mensaje)


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = CatalogadorApp()
    app.mainloop()
