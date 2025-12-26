"""Wizard flow and dialog helpers for InputsTab."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


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


class InputsTabWizardMixin:
    def _start_inline_wizard(self) -> None:
        if self._wizard_running:
            return
        params = self._wizard_prompt_settings()
        if params is None:
            return
        self._wizard_running = True
        self._wizard_preset = params["preset"]
        self._wizard_colmap_matcher = params["colmap_matcher"]
        self._wizard_colmap_camera_model = params["colmap_camera_model"]
        self._wizard_backend = params["backend"]
        self._wizard_colmap_enabled = params["colmap_enabled"]
        self._wizard_resize_enabled = params["resize_enabled"]
        self._apply_input_selection(params["input_type"], params["input_path"])
        self.candidate_var.set(params["candidate"])
        self.target_var.set(params["target"])
        self.training_resolution_var.set(params["resolution"] if params["resize_enabled"] else 0)
        self.training_resample_var.set(params["mode"])
        self._on_resolution_change()
        self._start_extraction()
        self.frame.after(500, self._wizard_wait_for_extract)

    def _wizard_wait_for_extract(self) -> None:
        if self._extracting:
            self.frame.after(500, self._wizard_wait_for_extract)
            return
        if self.current_result is None or not self.current_result.available_frames:
            messagebox.showerror("Wizard", "Extraction did not produce frames. Check the input and try again.", parent=self.frame.winfo_toplevel())
            self._wizard_running = False
            return
        self._persist_selection()
        self.frame.after(500, self._wizard_wait_for_save)

    def _wizard_wait_for_save(self) -> None:
        if self._saving:
            self.frame.after(500, self._wizard_wait_for_save)
            return
        if self.notebook is not None:
            try:
                self.notebook.select(1)
            except Exception:
                pass
        if self.colmap_tab is not None and getattr(self, "_wizard_colmap_enabled", True):
            try:
                if hasattr(self, "_wizard_colmap_matcher"):
                    self.colmap_tab.matcher_var.set(self._wizard_colmap_matcher)
                if hasattr(self, "_wizard_colmap_camera_model"):
                    self.colmap_tab.camera_model_var.set(self._wizard_colmap_camera_model)
                self.colmap_tab.run_sfm()
                self.frame.after(1000, self._wizard_wait_for_sfm)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Wizard", f"COLMAP failed: {exc}", parent=self.frame.winfo_toplevel())
                self._wizard_running = False
        else:
            self._wizard_start_training()

    def _wizard_wait_for_sfm(self) -> None:
        if self.colmap_tab is not None and self.colmap_tab.is_working():
            self.frame.after(1000, self._wizard_wait_for_sfm)
            return
        self._wizard_start_training()

    def _wizard_start_training(self) -> None:
        preset = getattr(self, "_wizard_preset", None)
        if not preset or self.training_tab is None:
            self._wizard_running = False
            return
        self._apply_wizard_training_mode()
        if self.notebook is not None:
            try:
                self.notebook.select(2)
            except Exception:
                pass
        try:
            self.training_tab.apply_training_preset(preset)
            self.training_tab.run_training()
            self.frame.after(1000, self._wizard_wait_for_training)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Wizard", f"Training failed: {exc}", parent=self.frame.winfo_toplevel())
            self._wizard_running = False

    def _wizard_wait_for_training(self) -> None:
        if self.training_tab is not None and self.training_tab.is_working():
            self.frame.after(1000, self._wizard_wait_for_training)
            return
        if self.exports_tab is not None:
            try:
                self.exports_tab._load_checkpoints()
            except Exception:
                pass
        if self.notebook is not None:
            try:
                self.notebook.select(3)
            except Exception:
                pass
        self._wizard_finish_exports()
        self._wizard_running = False

    def _wizard_prompt_settings(self) -> dict | None:
        dialog = tk.Toplevel(self.frame)
        dialog.title("Wizard: Inputs + Training preset")
        dialog.transient(self.frame.winfo_toplevel())
        dialog.grab_set()
        self._center_dialog(dialog)
        result: dict | None = None

        input_type_var = tk.StringVar(value=getattr(self, "input_type_var", tk.StringVar(value=INPUT_TYPE_VIDEO)).get())
        input_path_var = tk.StringVar(value=getattr(self, "input_path_var", tk.StringVar()).get())
        cand_var = tk.IntVar(value=self.candidate_var.get())
        target_var = tk.IntVar(value=self.target_var.get())
        res_var = tk.IntVar(value=self.training_resolution_var.get())
        mode_var = tk.StringVar(value=self.training_resample_var.get())
        preset_var = tk.StringVar(value="medium")
        matcher_var = tk.StringVar(value="exhaustive")
        camera_model_var = tk.StringVar(value="PINHOLE")

        dialog.columnconfigure(1, weight=1)
        ttk.Label(dialog, text="Input path:").grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        ttk.Entry(dialog, textvariable=input_path_var, width=50).grid(row=0, column=1, sticky="ew", padx=4, pady=(6, 0))

        type_row = ttk.Frame(dialog)
        type_row.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        ttk.Label(type_row, text="Input type:").pack(side="left")
        ttk.Combobox(
            type_row,
            values=INPUT_TYPE_OPTIONS,
            textvariable=input_type_var,
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 10))
        ttk.Button(
            type_row,
            text="Browse",
            command=lambda: self._wizard_browse_input(input_type_var, input_path_var),
        ).pack(side="left")

        backend_var = tk.StringVar(value=BACKEND_GSPLAT)
        colmap_var = tk.BooleanVar(value=True)
        resize_var = tk.BooleanVar(value=True)
        hint_var = tk.StringVar(value="")
        warn_var = tk.StringVar(value="")
        detected_var = tk.StringVar(value="")

        backend_row = ttk.Frame(dialog)
        backend_row.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 0))
        ttk.Label(backend_row, text="Training backend:").pack(side="left")
        backend_combo = ttk.Combobox(
            backend_row,
            values=BACKEND_OPTIONS,
            textvariable=backend_var,
            state="readonly",
            width=14,
        )
        backend_combo.pack(side="left", padx=(6, 12))
        colmap_toggle = ttk.Checkbutton(backend_row, text="Use COLMAP", variable=colmap_var)
        colmap_toggle.pack(side="left")
        resize_toggle = ttk.Checkbutton(backend_row, text="Resize frames", variable=resize_var)
        resize_toggle.pack(side="left", padx=(12, 0))

        detected_label = ttk.Label(dialog, textvariable=detected_var, foreground="#444", wraplength=520, justify="left")
        detected_label.grid(row=3, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 0))
        hint_label = ttk.Label(dialog, textvariable=hint_var, foreground="#555", wraplength=520, justify="left")
        hint_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 0))
        warn_label = ttk.Label(dialog, textvariable=warn_var, foreground="#a00", wraplength=520, justify="left")
        warn_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(2, 0))

        row3 = ttk.Frame(dialog)
        row3.grid(row=6, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(row3, text="Candidates").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=10000, textvariable=cand_var, width=7).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Targets").pack(side="left")
        ttk.Spinbox(row3, from_=1, to=10000, textvariable=target_var, width=7).pack(side="left", padx=(4, 12))
        ttk.Label(row3, text="Resolution (px, small side)").pack(side="left")
        res_combo = ttk.Combobox(row3, values=[720, 1080, 2160], textvariable=res_var, state="readonly", width=10)
        res_combo.pack(side="left", padx=(4, 6))
        mode_combo = ttk.Combobox(row3, values=["lanczos", "bicubic", "bilinear", "nearest"], textvariable=mode_var, state="readonly", width=10)
        mode_combo.pack(side="left")

        row4 = ttk.Frame(dialog)
        row4.grid(row=7, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(row4, text="Training preset").pack(side="left")
        ttk.Combobox(row4, values=["low", "medium", "high"], textvariable=preset_var, state="readonly", width=10).pack(
            side="left", padx=(4, 0)
        )

        row5 = ttk.Frame(dialog)
        row5.grid(row=8, column=0, columnspan=3, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(row5, text="COLMAP matcher").pack(side="left")
        ttk.Combobox(
            row5,
            values=["exhaustive", "sequential", "spatial"],
            textvariable=matcher_var,
            state="readonly",
            width=12,
        ).pack(side="left", padx=(4, 12))
        ttk.Label(row5, text="Camera model").pack(side="left")
        ttk.Combobox(
            row5,
            values=["PINHOLE", "SIMPLE_PINHOLE", "OPENCV"],
            textvariable=camera_model_var,
            state="readonly",
            width=14,
        ).pack(side="left", padx=(4, 0))

        def _ok() -> None:
            nonlocal result
            path = input_path_var.get().strip()
            if not path:
                messagebox.showerror("Wizard", "Provide a video file, image file(s), or image folder.", parent=dialog)
                return
            result = {
                "input_type": input_type_var.get(),
                "input_path": path,
                "backend": backend_var.get(),
                "colmap_enabled": bool(colmap_var.get()),
                "resize_enabled": bool(resize_var.get()),
                "candidate": max(1, int(cand_var.get())),
                "target": max(1, int(target_var.get())),
                "resolution": max(1, int(res_var.get())),
                "mode": mode_var.get(),
                "preset": preset_var.get(),
                "colmap_matcher": matcher_var.get(),
                "colmap_camera_model": camera_model_var.get(),
            }
            dialog.destroy()

        def _cancel() -> None:
            dialog.destroy()

        btn_row = ttk.Frame(dialog)
        btn_row.grid(row=9, column=0, columnspan=3, sticky="e", padx=8, pady=(8, 8))
        ttk.Button(btn_row, text="Cancel", command=_cancel).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="OK", command=_ok).pack(side="right")

        def _apply_profile_defaults() -> None:
            profile = self._infer_input_profile(input_path_var.get().strip(), input_type_var.get())
            if profile is None:
                detected_var.set("")
                hint_var.set("")
                warn_var.set("")
                return
            detected_var.set(profile["detected"])
            hint_var.set(profile["hint"])
            backend_var.set(profile["backend"])
            colmap_var.set(profile["colmap"])
            resize_var.set(profile["resize"])
            res_state = "readonly" if profile["resize_allowed"] else "disabled"
            res_combo.configure(state=res_state)
            mode_combo.configure(state=res_state)
            resize_toggle.configure(state="normal" if profile["resize_allowed"] else "disabled")
            if not profile["resize_allowed"]:
                resize_var.set(False)
            warn_var.set(profile["warning"])
            if backend_var.get() == BACKEND_GSPLAT:
                colmap_var.set(True)
                colmap_toggle.configure(state="disabled")
            elif profile["profile"] == "single":
                colmap_var.set(False)
                colmap_toggle.configure(state="disabled")
            else:
                colmap_toggle.configure(state="normal")

        def _refresh_backend_constraints(*_args) -> None:
            profile = self._infer_input_profile(input_path_var.get().strip(), input_type_var.get())
            if backend_var.get() == BACKEND_GSPLAT:
                colmap_var.set(True)
                colmap_toggle.configure(state="disabled")
            elif profile and profile["profile"] == "single":
                colmap_var.set(False)
                colmap_toggle.configure(state="disabled")
            else:
                colmap_toggle.configure(state="normal")
            if profile:
                warn_var.set(self._backend_vram_warning(backend_var.get(), profile.get("count")))

        input_path_var.trace_add("write", lambda *_args: _apply_profile_defaults())
        input_type_var.trace_add("write", lambda *_args: _apply_profile_defaults())
        backend_combo.bind("<<ComboboxSelected>>", _refresh_backend_constraints)
        resize_var.trace_add("write", lambda *_args: res_combo.configure(state="readonly" if resize_var.get() else "disabled"))
        resize_var.trace_add("write", lambda *_args: mode_combo.configure(state="readonly" if resize_var.get() else "disabled"))

        _apply_profile_defaults()

        dialog.wait_window()
        return result

    def _wizard_browse_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self.frame.winfo_toplevel(),
            title="Select video file",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _wizard_browse_folder(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(parent=self.frame.winfo_toplevel(), title="Select image folder")
        if path:
            var.set(path)

    def _wizard_browse_image(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self.frame.winfo_toplevel(),
            title="Select image file",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def _wizard_browse_input(self, input_type_var: tk.StringVar, path_var: tk.StringVar) -> None:
        input_type = input_type_var.get()
        if input_type == INPUT_TYPE_VIDEO:
            self._wizard_browse_file(path_var)
        elif input_type == INPUT_TYPE_IMAGE:
            self._wizard_browse_image(path_var)
        elif input_type == INPUT_TYPE_IMAGES:
            paths = filedialog.askopenfilenames(
                parent=self.frame.winfo_toplevel(),
                title="Select image files",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
            )
            staged = self._stage_multi_image_selection(list(paths))
            if staged:
                path_var.set(staged)
        else:
            self._wizard_browse_folder(path_var)

    def _backend_vram_warning(self, backend: str, count: int | None) -> str:
        if count is None or count <= 10:
            return ""
        if backend in {BACKEND_DA3, BACKEND_SHARP}:
            return "Warning: DA3/SHARP with more than 10 frames can require 40GB+ of VRAM."
        return ""

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
            hint = "Single frame mode. COLMAP disabled. Resize disabled."
        elif profile == "few":
            backend = BACKEND_DA3
            colmap = False
            resize = False
            resize_allowed = True
            hint = "Few-frame mode (2–15). COLMAP optional. Resize optional."
        else:
            backend = BACKEND_GSPLAT
            colmap = True
            resize = True
            resize_allowed = True
            hint = "Many-frame mode (video or 16+). COLMAP recommended. Resize on by default."

        detected = f"Detected {count} image(s)." if count is not None else "Detected video input."
        warning = self._backend_vram_warning(backend, count)
        return {
            "profile": profile,
            "count": count,
            "backend": backend,
            "colmap": colmap,
            "resize": resize,
            "resize_allowed": resize_allowed,
            "hint": hint,
            "detected": detected,
            "warning": warning,
        }

    def _apply_wizard_training_mode(self) -> None:
        backend = getattr(self, "_wizard_backend", BACKEND_GSPLAT)
        colmap_enabled = getattr(self, "_wizard_colmap_enabled", True)
        if self.training_tab is None:
            return
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

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        """Center a dialog over the main window."""
        try:
            dialog.update_idletasks()
            parent = self.frame.winfo_toplevel()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = dialog.winfo_width()
            h = dialog.winfo_height()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            return

    def _wizard_finish_exports(self) -> None:
        latest = None
        if self.exports_tab is not None and getattr(self.exports_tab, "checkpoint_paths", None):
            latest = self.exports_tab.checkpoint_paths[0] if self.exports_tab.checkpoint_paths else None
        msg = "Extraction and training complete."
        if latest:
            msg += f"\nLatest checkpoint: {latest.name}"
        if messagebox.askyesno("Wizard complete", msg + "\nOpen output folder?"):
            try:
                if latest:
                    Path(latest).parent.mkdir(parents=True, exist_ok=True)
                    import os
                    os.startfile(str(Path(latest).parent))
            except Exception:
                pass

