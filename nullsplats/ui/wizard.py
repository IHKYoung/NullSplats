"""Wizard flow to guide users from inputs through training to exports."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Callable, List

from nullsplats.app_state import AppState


INPUT_TYPE_VIDEO = "Video file"
INPUT_TYPE_IMAGE = "Image file"
INPUT_TYPE_IMAGES = "Image files"
INPUT_TYPE_FOLDER = "Image folder"
INPUT_TYPE_OPTIONS = [
    INPUT_TYPE_VIDEO,
    INPUT_TYPE_IMAGE,
    INPUT_TYPE_IMAGES,
    INPUT_TYPE_FOLDER,
]

BACKEND_GSPLAT = "Gsplat"
BACKEND_DA3 = "DA3"
BACKEND_SHARP = "SHARP"
BACKEND_OPTIONS = [BACKEND_GSPLAT, BACKEND_DA3, BACKEND_SHARP]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class WizardStep:
    """Single wizard step definition."""

    def __init__(self, title: str, description: str, require: Callable[[], bool], on_navigate: Callable[[], None]) -> None:
        self.title = title
        self.description = description
        self.require = require
        self.on_navigate = on_navigate
        self.status = "pending"


class WizardWindow(tk.Toplevel):
    """Guided flow overlay."""

    def __init__(self, root: tk.Tk, app_state: AppState, select_tab: Callable[[int], None]) -> None:
        super().__init__(root)
        self.title("NullSplats Wizard")
        self.geometry("900x600")
        self.app_state = app_state
        self.select_tab = select_tab
        self.steps: List[WizardStep] = []
        self.current_idx = 0
        self.status_var = tk.StringVar(value="")
        self._build_steps()
        self._build_ui()
        self._refresh_status()

    def _build_steps(self) -> None:
        def require_inputs() -> bool:
            scene = self.app_state.current_scene_id
            if scene is None:
                return False
            paths = self.app_state.scene_manager.get(scene).paths
            return paths.frames_selected_dir.exists() and any(paths.frames_selected_dir.iterdir())

        def require_colmap() -> bool:
            scene = self.app_state.current_scene_id
            if scene is None:
                return False
            paths = self.app_state.scene_manager.get(scene).paths
            return paths.sfm_dir.exists() and any(paths.sfm_dir.iterdir())

        def require_training() -> bool:
            scene = self.app_state.current_scene_id
            if scene is None:
                return False
            paths = self.app_state.scene_manager.get(scene).paths
            return paths.splats_dir.exists() and any(paths.splats_dir.iterdir())

        def require_exports() -> bool:
            scene = self.app_state.current_scene_id
            if scene is None:
                return False
            paths = self.app_state.scene_manager.get(scene).paths
            return paths.splats_dir.exists() and any(paths.splats_dir.iterdir())

        self.steps = [
            WizardStep(
                "Step 1: Inputs",
                "Create/select a scene, choose video or images, extract frames, and save selected/resized images.",
                require_inputs,
                lambda: self._go_tab(0),
            ),
            WizardStep(
                "Step 2: COLMAP",
                "Run COLMAP to compute camera poses for the active scene (skip for DA3-only or SHARP-only runs).",
                require_colmap,
                lambda: self._go_tab(1),
            ),
            WizardStep(
                "Step 3: Training",
                "Train Gaussian splats for the active scene. Watch preview while training.",
                require_training,
                lambda: self._go_tab(2),
            ),
            WizardStep(
                "Step 4: Exports",
                "Preview checkpoints and export .ply or renders for the active scene.",
                require_exports,
                lambda: self._go_tab(3),
            ),
        ]

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self)
        sidebar.grid(row=0, column=0, sticky="ns")
        self.listbox = tk.Listbox(sidebar, height=10)
        for step in self.steps:
            self.listbox.insert(tk.END, step.title)
        self.listbox.bind("<<ListboxSelect>>", self._on_step_select)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=8)

        main = ttk.Frame(self)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self.title_label = ttk.Label(main, text=self.steps[0].title, font=("Segoe UI", 12, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        self.desc_label = ttk.Label(main, text=self.steps[0].description, wraplength=520, justify="left")
        self.desc_label.grid(row=1, column=0, sticky="nw", padx=10, pady=(0, 10))

        controls = ttk.Frame(main)
        controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        controls.columnconfigure(1, weight=1)

        self.status_display = ttk.Label(main, textvariable=self.status_var, foreground="#444")
        self.status_display.grid(row=3, column=0, sticky="w", padx=10, pady=(0, 8))

        btn_prev = ttk.Button(controls, text="Previous", command=self._prev_step)
        btn_prev.grid(row=0, column=0, sticky="w")
        btn_next = ttk.Button(controls, text="Next", command=self._next_step)
        btn_next.grid(row=0, column=2, sticky="e")
        btn_goto = ttk.Button(controls, text="Go to tab", command=self._open_current_tab)
        btn_goto.grid(row=0, column=1, sticky="e", padx=(0, 8))
        btn_refresh = ttk.Button(controls, text="Refresh status", command=self._refresh_status)
        btn_refresh.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.listbox.selection_set(0)

    def _open_current_tab(self) -> None:
        self.steps[self.current_idx].on_navigate()

    def _go_tab(self, index: int) -> None:
        try:
            self.select_tab(index)
        except Exception:
            pass

    def _on_step_select(self, _: tk.Event) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self.current_idx = sel[0]
        self._refresh_status()

    def _next_step(self) -> None:
        if self.current_idx < len(self.steps) - 1:
            self.current_idx += 1
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.current_idx)
            self._refresh_status()
        else:
            messagebox.showinfo("Wizard", "You have reached the final step.")

    def _prev_step(self) -> None:
        if self.current_idx > 0:
            self.current_idx -= 1
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.current_idx)
            self._refresh_status()

    def _refresh_status(self) -> None:
        step = self.steps[self.current_idx]
        complete = step.require()
        step.status = "complete" if complete else "pending"
        self.title_label.config(text=step.title)
        self.desc_label.config(text=step.description)
        self.status_var.set(f"Status: {'Complete' if complete else 'Pending'} | Active scene: {self._scene_label()}")
        self._update_listbox_labels()

    def _scene_label(self) -> str:
        scene = self.app_state.current_scene_id
        return str(scene) if scene is not None else "(none)"

    def _update_listbox_labels(self) -> None:
        self.listbox.delete(0, tk.END)
        for idx, step in enumerate(self.steps):
            prefix = "OK " if step.status == "complete" else " - "
            self.listbox.insert(tk.END, f"{prefix}{step.title}")
        self.listbox.selection_set(self.current_idx)


__all__ = ["WizardWindow", "GuidedWizard"]


class GuidedWizard(tk.Toplevel):
    """Actionable wizard that executes extract -> train -> export."""

    def __init__(
        self,
        root: tk.Misc,
        app_state: AppState,
        *,
        inputs_tab,
        colmap_tab,
        training_tab,
        exports_tab,
        notebook,
    ) -> None:
        super().__init__(root)
        self.title("Wizard mode")
        self.geometry("820x640")
        self.app_state = app_state
        self.inputs_tab = inputs_tab
        self.colmap_tab = colmap_tab
        self.training_tab = training_tab
        self.exports_tab = exports_tab
        self.notebook = notebook
        self.current_step = 0

        self.input_type_var = tk.StringVar(value=getattr(self.inputs_tab, "input_type_var", tk.StringVar(value=INPUT_TYPE_VIDEO)).get())
        self.input_path_var = tk.StringVar(value=getattr(self.inputs_tab, "input_path_var", tk.StringVar()).get())
        self.candidate_var = tk.IntVar(value=self.inputs_tab.candidate_var.get())
        self.target_var = tk.IntVar(value=self.inputs_tab.target_var.get())
        self.resolution_var = tk.IntVar(value=self.inputs_tab.training_resolution_var.get())
        self.mode_var = tk.StringVar(value=self.inputs_tab.training_resample_var.get())
        self.preset_var = tk.StringVar(value="low")
        self.backend_var = tk.StringVar(value=BACKEND_GSPLAT)
        self.colmap_var = tk.BooleanVar(value=True)
        self.resize_var = tk.BooleanVar(value=True)
        self.training_hint_var = tk.StringVar(value="")
        self.training_warn_var = tk.StringVar(value="")
        self.detected_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        ttk.Label(header, text="Guided flow", font=("Segoe UI", 12, "bold")).pack(side="left")
        self.step_label = ttk.Label(header, text="Step 1 of 4")
        self.step_label.pack(side="right")

        self.card_frame = ttk.Frame(self)
        self.card_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        self.card_frame.columnconfigure(0, weight=1)

        footer = ttk.Frame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))
        ttk.Button(footer, text="Back", command=self._prev_step).pack(side="left")
        ttk.Button(footer, text="Next", command=self._next_step).pack(side="right")

        self.cards: list[ttk.Frame] = [
            self._build_step_inputs(),
            self._build_step_colmap(),
            self._build_step_training(),
            self._build_step_exports(),
        ]
        for card in self.cards:
            card.grid(row=0, column=0, sticky="nsew")
        self._show_step(0)

    def _build_step_inputs(self) -> ttk.Frame:
        frame = ttk.LabelFrame(self.card_frame, text="Inputs")
        ttk.Label(frame, text="Input path:").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 0))
        ttk.Entry(frame, textvariable=self.input_path_var, width=60).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(0, 6), pady=(6, 0)
        )

        type_row = ttk.Frame(frame)
        type_row.grid(row=1, column=0, columnspan=3, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(type_row, text="Input type:").pack(side="left")
        ttk.Combobox(
            type_row,
            values=INPUT_TYPE_OPTIONS,
            textvariable=self.input_type_var,
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 10))
        ttk.Button(type_row, text="Browse", command=self._browse_input).pack(side="left")

        backend_row = ttk.Frame(frame)
        backend_row.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(backend_row, text="Training backend:").pack(side="left")
        backend_combo = ttk.Combobox(
            backend_row,
            values=BACKEND_OPTIONS,
            textvariable=self.backend_var,
            state="readonly",
            width=14,
        )
        backend_combo.pack(side="left", padx=(6, 12))
        self.colmap_toggle = ttk.Checkbutton(backend_row, text="Use COLMAP", variable=self.colmap_var)
        self.colmap_toggle.pack(side="left")
        self.resize_toggle = ttk.Checkbutton(backend_row, text="Resize frames", variable=self.resize_var)
        self.resize_toggle.pack(side="left", padx=(12, 0))

        detected_label = ttk.Label(frame, textvariable=self.detected_var, foreground="#444", wraplength=540, justify="left")
        detected_label.grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 0))
        hint_label = ttk.Label(frame, textvariable=self.training_hint_var, foreground="#555", wraplength=540, justify="left")
        hint_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 0))
        warn_label = ttk.Label(frame, textvariable=self.training_warn_var, foreground="#a00", wraplength=540, justify="left")
        warn_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 0))
        backend_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_backend_constraints())

        row3 = ttk.Frame(frame)
        row3.grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 4))
        ttk.Label(row3, text="Candidate frames:").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=10000, textvariable=self.candidate_var, width=8).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Target frames:").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=10000, textvariable=self.target_var, width=8).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Resolution (px, small side):").pack(side="left")
        self.res_combo = ttk.Combobox(row3, values=[720, 1080, 2160], textvariable=self.resolution_var, state="readonly", width=12)
        self.res_combo.pack(side="left", padx=(4, 8))
        self.mode_combo = ttk.Combobox(row3, values=["lanczos", "bicubic", "bilinear", "nearest"], textvariable=self.mode_var, width=10, state="readonly")
        self.mode_combo.pack(side="left")

        ttk.Button(frame, text="Extract and continue", command=self._extract_and_continue).grid(
            row=7, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 6)
        )
        self.input_path_var.trace_add("write", lambda *_args: self._apply_profile_defaults())
        self.input_type_var.trace_add("write", lambda *_args: self._apply_profile_defaults())
        self.resize_var.trace_add("write", lambda *_args: self._update_resize_controls())
        self._apply_profile_defaults()
        return frame

    def _build_step_colmap(self) -> ttk.Frame:
        frame = ttk.LabelFrame(self.card_frame, text="COLMAP")
        ttk.Label(
            frame,
            text="Run COLMAP to compute camera poses for the active scene before training.",
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=6, pady=(6, 4))
        ttk.Button(frame, text="Run COLMAP", command=self._run_colmap_and_continue).pack(
            anchor="w", padx=6, pady=(6, 6)
        )
        return frame

    def _build_step_training(self) -> ttk.Frame:
        frame = ttk.LabelFrame(self.card_frame, text="Training")
        row = ttk.Frame(frame)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Label(row, text="Preset:").pack(side="left")
        ttk.Combobox(row, values=["low", "medium", "high"], textvariable=self.preset_var, state="readonly", width=10).pack(side="left", padx=(4, 8))
        ttk.Button(frame, text="Run training", command=self._train_and_continue).pack(anchor="w", padx=6, pady=(6, 6))
        ttk.Label(frame, text="Training runs on the active scene. Preview updates while training.", wraplength=540, justify="left").pack(anchor="w", padx=6, pady=(0, 6))
        return frame

    def _build_step_exports(self) -> ttk.Frame:
        frame = ttk.LabelFrame(self.card_frame, text="Exports")
        ttk.Label(
            frame,
            text="Latest checkpoint will be selected automatically. You can render or copy .ply from the Exports tab.",
            wraplength=540,
            justify="left",
        ).pack(anchor="w", padx=6, pady=6)
        ttk.Button(frame, text="Open Exports tab", command=lambda: self._select_tab(3)).pack(anchor="w", padx=6, pady=(4, 6))
        return frame

    def _show_step(self, idx: int) -> None:
        for i, card in enumerate(self.cards):
            card.grid_remove()
            if i == idx:
                card.grid()
        self.current_step = idx
        self.step_label.config(text=f"Step {idx + 1} of {len(self.cards)}")

    def _next_step(self) -> None:
        if self.current_step < len(self.cards) - 1:
            self._show_step(self.current_step + 1)

    def _prev_step(self) -> None:
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _select_tab(self, index: int) -> None:
        if self.notebook is not None:
            try:
                self.notebook.select(index)
            except Exception:
                pass

    def _backend_vram_warning(self, backend: str, count: int | None) -> str:
        if count is None or count <= 10:
            return ""
        if backend in {BACKEND_DA3, BACKEND_SHARP}:
            return "Warning: DA3/SHARP with more than 10 frames can require 40GB+ of VRAM."
        return ""

    def _backend_hint(self, profile: str) -> str:
        if profile == "single":
            return "Single frame mode. COLMAP disabled. Resize disabled."
        if profile == "few":
            return "Few-frame mode (2–15). COLMAP optional. Resize optional."
        return "Many-frame mode (video or 16+). COLMAP recommended. Resize on by default."

    def _infer_input_profile(self, path_str: str, input_type: str) -> dict | None:
        if not path_str:
            return None
        path = Path(path_str)
        count: int | None = None
        if input_type == INPUT_TYPE_VIDEO:
            profile = "many"
        elif path.is_file():
            count = 1
            profile = "single"
        elif path.is_dir():
            count = sum(
                1 for entry in path.iterdir() if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS
            )
            if count <= 1:
                profile = "single"
            elif count <= 15:
                profile = "few"
            else:
                profile = "many"
        else:
            return None

        if profile == "single":
            backend = BACKEND_SHARP
            colmap = False
            resize = False
            resize_allowed = False
        elif profile == "few":
            backend = BACKEND_DA3
            colmap = False
            resize = False
            resize_allowed = True
        else:
            backend = BACKEND_GSPLAT
            colmap = True
            resize = True
            resize_allowed = True

        detected = f"Detected {count} image(s)." if count is not None else "Detected video input."
        return {
            "profile": profile,
            "count": count,
            "backend": backend,
            "colmap": colmap,
            "resize": resize,
            "resize_allowed": resize_allowed,
            "detected": detected,
        }

    def _apply_profile_defaults(self) -> None:
        profile = self._infer_input_profile(self.input_path_var.get().strip(), self.input_type_var.get())
        if profile is None:
            self.detected_var.set("")
            self.training_hint_var.set("")
            self.training_warn_var.set("")
            return
        self.detected_var.set(profile["detected"])
        self.training_hint_var.set(self._backend_hint(profile["profile"]))
        self.backend_var.set(profile["backend"])
        self.colmap_var.set(profile["colmap"])
        self.resize_var.set(profile["resize"])
        res_state = "readonly" if profile["resize_allowed"] else "disabled"
        self.res_combo.configure(state=res_state)
        self.mode_combo.configure(state=res_state)
        self.resize_toggle.configure(state="normal" if profile["resize_allowed"] else "disabled")
        if not profile["resize_allowed"]:
            self.resize_var.set(False)
        if self.backend_var.get() == BACKEND_GSPLAT:
            self.colmap_var.set(True)
            self.colmap_toggle.configure(state="disabled")
        elif profile["profile"] == "single":
            self.colmap_var.set(False)
            self.colmap_toggle.configure(state="disabled")
        else:
            self.colmap_toggle.configure(state="normal")
        self.training_warn_var.set(self._backend_vram_warning(self.backend_var.get(), profile.get("count")))

    def _refresh_backend_constraints(self) -> None:
        profile = self._infer_input_profile(self.input_path_var.get().strip(), self.input_type_var.get())
        if self.backend_var.get() == BACKEND_GSPLAT:
            self.colmap_var.set(True)
            self.colmap_toggle.configure(state="disabled")
        elif profile and profile["profile"] == "single":
            self.colmap_var.set(False)
            self.colmap_toggle.configure(state="disabled")
        else:
            self.colmap_toggle.configure(state="normal")
        if profile:
            self.training_warn_var.set(self._backend_vram_warning(self.backend_var.get(), profile.get("count")))

    def _update_resize_controls(self) -> None:
        state = "readonly" if self.resize_var.get() else "disabled"
        self.res_combo.configure(state=state)
        self.mode_combo.configure(state=state)

    def _browse_input(self) -> None:
        input_type = self.input_type_var.get()
        if input_type == INPUT_TYPE_VIDEO:
            path = filedialog.askopenfilename(
                parent=self,
                title="Select video file",
                filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv"), ("All files", "*.*")],
            )
            if path:
                self.input_path_var.set(path)
            return
        if input_type == INPUT_TYPE_IMAGE:
            path = filedialog.askopenfilename(
                parent=self,
                title="Select image file",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
            )
            if path:
                self.input_path_var.set(path)
            return
        if input_type == INPUT_TYPE_IMAGES:
            paths = filedialog.askopenfilenames(
                parent=self,
                title="Select image files",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
            )
            staged = self.inputs_tab._stage_multi_image_selection(list(paths))
            if staged:
                self.input_path_var.set(staged)
            return
        path = filedialog.askdirectory(parent=self, title="Select image folder")
        if path:
            self.input_path_var.set(path)

    def _apply_training_mode_to_tab(self) -> None:
        backend = self.backend_var.get()
        colmap_enabled = bool(self.colmap_var.get())
        if backend == BACKEND_GSPLAT:
            self.training_tab.training_method_var.set("gsplat")
        elif backend == BACKEND_DA3:
            self.training_tab.training_method_var.set("depth_anything_3")
            self.training_tab.da3_allow_unposed_var.set(not colmap_enabled)
        else:
            self.training_tab.training_method_var.set("sharp")
            self.training_tab.sharp_intrinsics_source_var.set("colmap" if colmap_enabled else "exif")
        try:
            self.training_tab._apply_trainer_capabilities()
        except Exception:
            pass

    def _extract_and_continue(self) -> None:
        try:
            # Sync vars to inputs tab
            self.inputs_tab._apply_input_selection(self.input_type_var.get(), self.input_path_var.get())
            self.inputs_tab.candidate_var.set(self.candidate_var.get())
            self.inputs_tab.target_var.set(self.target_var.get())
            self.inputs_tab.training_resolution_var.set(self.resolution_var.get() if self.resize_var.get() else 0)
            self.inputs_tab.training_resample_var.set(self.mode_var.get())
            self.inputs_tab._on_resolution_change()
            self.inputs_tab._start_extraction()
            self.after(500, self._wait_for_extract)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Wizard", f"Extraction failed: {exc}", parent=self)

    def _wait_for_extract(self) -> None:
        if getattr(self.inputs_tab, "_extracting", False):
            self.after(500, self._wait_for_extract)
            return
        # Auto-save selection with resolution
        self.inputs_tab._persist_selection()
        self.after(500, self._wait_for_save)

    def _wait_for_save(self) -> None:
        if getattr(self.inputs_tab, "_saving", False):
            self.after(500, self._wait_for_save)
            return
        self._select_tab(1)
        self._show_step(1)

    def _run_colmap_and_continue(self) -> None:
        if not self.colmap_var.get():
            self._select_tab(2)
            self._show_step(2)
            return
        if self.colmap_tab is None:
            self._select_tab(2)
            self._show_step(2)
            return
        try:
            self.colmap_tab.run_sfm()
            self.after(1000, self._wait_for_colmap)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Wizard", f"COLMAP failed: {exc}", parent=self)

    def _wait_for_colmap(self) -> None:
        if self.colmap_tab is not None and self.colmap_tab.is_working():
            self.after(1000, self._wait_for_colmap)
            return
        self._select_tab(2)
        self._show_step(2)

    def _train_and_continue(self) -> None:
        if self.training_tab is None:
            return
        try:
            self._apply_training_mode_to_tab()
            self.training_tab.apply_training_preset(self.preset_var.get())
            self.training_tab.run_training()
            self.after(1000, self._wait_for_training)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Wizard", f"Training failed: {exc}", parent=self)

    def _wait_for_training(self) -> None:
        if self.training_tab is not None and self.training_tab.is_working():
            self.after(1000, self._wait_for_training)
            return
        # Jump to exports and select latest
        if self.exports_tab is not None:
            try:
                self.exports_tab._load_checkpoints()
            except Exception:
                pass
        self._select_tab(3)
        self._show_step(3)
