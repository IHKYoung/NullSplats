"""COLMAP (SfM) tab UI for NullSplats."""

from __future__ import annotations

import logging
import queue
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext, ttk
from typing import Optional

from nullsplats.app_state import AppState
from nullsplats.backend.sfm_pipeline import SfmConfig, SfmResult, run_sfm
from nullsplats.util.logging import get_logger
from nullsplats.util.tooling_paths import default_colmap_path
from nullsplats.util.threading import run_in_background


class ColmapTab:
    """Dedicated COLMAP/SfM tab."""

    def __init__(self, master: tk.Misc, app_state: AppState) -> None:
        self.app_state = app_state
        self.logger = get_logger("ui.colmap")
        self.logger.setLevel(logging.DEBUG)
        self.frame = ttk.Frame(master)

        self.status_var = tk.StringVar(value="Configure COLMAP and run SfM.")
        self.colmap_path_var = tk.StringVar(value=default_colmap_path())
        self.matcher_var = tk.StringVar(value="exhaustive")
        self.camera_model_var = tk.StringVar(value="PINHOLE")
        self.force_sfm_var = tk.BooleanVar(value=False)
        self.progress_var = tk.DoubleVar(value=0.0)

        self.scene_label: Optional[ttk.Label] = None
        self.scene_status_label: Optional[ttk.Label] = None
        self.status_label: Optional[ttk.Label] = None
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.log_view: Optional[scrolledtext.ScrolledText] = None
        self._log_handler: Optional[logging.Handler] = None
        self._interactive_controls: list[tk.Widget] = []
        self._working = False

        self._build_contents()
        self._update_scene_label()

    def on_tab_selected(self, selected: bool) -> None:
        if selected:
            self._update_scene_label()

    def on_scene_changed(self, scene_id: Optional[str]) -> None:
        if scene_id is not None:
            self.app_state.set_current_scene(scene_id)
        self._update_scene_label()

    def apply_colmap_preset(self, preset: Optional[str] = None) -> None:
        if preset:
            preset = preset.lower().strip()
            if preset in {"exhaustive", "sequential", "spatial"}:
                self.matcher_var.set(preset)

    def run_sfm(self) -> None:
        self._run_sfm()

    def is_working(self) -> bool:
        return self._working

    def _build_contents(self) -> None:
        paned = ttk.Panedwindow(self.frame, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_col = ttk.Frame(paned, width=420)
        right_col = ttk.Frame(paned)
        paned.add(left_col, weight=2)
        paned.add(right_col, weight=3)

        ttk.Label(left_col, text="COLMAP workflow", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=10, pady=(10, 6)
        )

        scene_card = ttk.LabelFrame(left_col, text="Scene context")
        scene_card.pack(fill="x", padx=10, pady=(0, 6))
        self.scene_label = ttk.Label(scene_card, text=self._scene_text(), anchor="w", justify="left", font=("Segoe UI", 10, "bold"))
        self.scene_label.pack(fill="x", padx=6, pady=(6, 2))
        self.scene_status_label = ttk.Label(
            scene_card,
            text=self._scene_status_text(),
            anchor="w",
            justify="left",
            foreground="#444",
        )
        self.scene_status_label.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(
            scene_card,
            text="Select a scene in Inputs; COLMAP outputs land under cache/outputs/<scene>/sfm.",
            foreground="#666",
            wraplength=380,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=6, pady=(0, 6))

        status_card = ttk.LabelFrame(left_col, text="Run status")
        status_card.pack(fill="x", padx=10, pady=(0, 6))
        self.status_label = ttk.Label(
            status_card, textvariable=self.status_var, foreground="#333", font=("Segoe UI", 11, "bold"), wraplength=380
        )
        self.status_label.pack(fill="x", padx=6, pady=(6, 4))
        self.progress_bar = ttk.Progressbar(status_card, variable=self.progress_var, mode="determinate", maximum=1.0)
        self.progress_bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(
            status_card,
            text="Run COLMAP to generate camera poses before training.",
            foreground="#666",
            wraplength=380,
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=6, pady=(0, 4))
        primary_row = ttk.Frame(status_card)
        primary_row.pack(fill="x", padx=6, pady=(0, 6))
        btn_run = ttk.Button(primary_row, text="Run COLMAP", command=self._run_sfm)
        btn_run.pack(side="left")
        self._register_control(btn_run)
        ttk.Checkbutton(primary_row, text="Re-run from scratch", variable=self.force_sfm_var).pack(side="left", padx=(6, 0))
        btn_open = ttk.Button(primary_row, text="Open log folder", command=self._open_log_folder)
        btn_open.pack(side="right")
        self._register_control(btn_open)

        cfg_card = ttk.LabelFrame(left_col, text="SfM settings")
        cfg_card.pack(fill="x", padx=10, pady=(0, 6))
        row1 = ttk.Frame(cfg_card)
        row1.pack(fill="x", padx=6, pady=(6, 4))
        ttk.Label(row1, text="COLMAP path:").pack(side="left")
        ttk.Entry(row1, textvariable=self.colmap_path_var, width=36).pack(side="left", padx=(4, 0), fill="x", expand=True)

        row2 = ttk.Frame(cfg_card)
        row2.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(row2, text="Matcher:").pack(side="left")
        ttk.Combobox(
            row2,
            textvariable=self.matcher_var,
            values=["exhaustive", "sequential", "spatial"],
            state="readonly",
            width=12,
        ).pack(side="left", padx=(4, 12))
        ttk.Label(row2, text="Camera model:").pack(side="left")
        ttk.Combobox(
            row2,
            textvariable=self.camera_model_var,
            values=["PINHOLE", "SIMPLE_PINHOLE", "OPENCV"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=(4, 0))
        ttk.Label(
            cfg_card,
            text=(
                "Matcher: exhaustive for smaller sets, sequential for ordered captures, "
                "spatial for larger unordered sets. "
                "Camera model: PINHOLE is a safe default; OPENCV includes distortion terms."
            ),
            foreground="#666",
            wraplength=380,
            justify="left",
        ).pack(fill="x", padx=6, pady=(4, 4))

        ttk.Label(left_col, text="Live logs stream on the right.", anchor="w", justify="left").pack(
            anchor="w", padx=10, pady=(4, 4)
        )

        log_frame = ttk.LabelFrame(right_col, text="COLMAP logs")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(10, 10))
        self.log_view = scrolledtext.ScrolledText(log_frame, wrap="word", height=20, width=80)
        self.log_view.pack(fill="both", expand=True, padx=6, pady=6)
        self.log_view.configure(state="disabled")
        self._attach_log_handler()

    def _register_control(self, widget: tk.Widget) -> None:
        self._interactive_controls.append(widget)
        widget.bind(
            "<Destroy>",
            lambda e: self._interactive_controls.remove(widget)
            if widget in self._interactive_controls
            else None,
        )

    def _reset_progress(self, *, indeterminate: bool = False) -> None:
        if self.progress_bar is None:
            return
        self.progress_bar.stop()
        self.progress_bar.configure(mode="indeterminate" if indeterminate else "determinate", maximum=1.0)
        self.progress_var.set(0.0)
        if indeterminate:
            self.progress_bar.start(90)

    def _set_progress(self, fraction: float) -> None:
        if self.progress_bar is None:
            return
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate", maximum=1.0)
        self.progress_var.set(max(0.0, min(1.0, fraction)))

    def _scene_text(self) -> str:
        scene = self.app_state.current_scene_id
        if scene is None:
            return "No active scene selected."
        return f"Active scene: {scene}"

    def _scene_status_text(self) -> str:
        scene = self.app_state.current_scene_id
        if scene is None:
            return "No active scene set."
        try:
            statuses = self.app_state.refresh_scene_status()
            status = next((s for s in statuses if str(s.scene_id) == str(scene)), None)
            if status is None:
                return "Scene status unknown."
            parts = [
                f"Inputs {'OK' if status.has_inputs else '--'}",
                f"SfM {'OK' if status.has_sfm else '--'}",
                f"Splats {'OK' if status.has_splats else '--'}",
            ]
            return " > ".join(parts)
        except Exception:  # noqa: BLE001
            return "Scene status unavailable."

    def _update_scene_label(self) -> None:
        if self.scene_label is not None:
            self.scene_label.config(text=self._scene_text())
        if self.scene_status_label is not None:
            self.scene_status_label.config(text=self._scene_status_text())

    def _require_scene(self) -> Optional[str]:
        scene = self.app_state.current_scene_id
        if scene is None:
            self._set_status("Select or create a scene in the Inputs tab first.", is_error=True)
            return None
        return str(scene)

    def _run_sfm(self) -> None:
        if self._working:
            self._set_status("Another operation is running; wait for it to finish.", is_error=True)
            return
        scene_id = self._require_scene()
        if scene_id is None:
            return
        if self.force_sfm_var.get():
            if not self._clear_outputs(scene_id):
                return
        sfm_config = SfmConfig(
            colmap_path=self.colmap_path_var.get().strip() or "colmap",
            matcher=self.matcher_var.get().strip() or "exhaustive",
            camera_model=self.camera_model_var.get().strip() or "PINHOLE",
        )
        self._working = True
        self._set_status("Running COLMAP...")
        self._reset_progress(indeterminate=True)
        self._set_controls_enabled(False)
        run_in_background(
            self._execute_sfm,
            scene_id,
            sfm_config,
            tk_root=self.frame.winfo_toplevel(),
            on_success=self._handle_sfm_success,
            on_error=self._handle_error,
            thread_name=f"sfm_only_{scene_id}",
        )

    def _execute_sfm(self, scene_id: str, sfm_config: SfmConfig) -> SfmResult:
        return run_sfm(scene_id, config=sfm_config, cache_root=self.app_state.config.cache_root)

    def _handle_sfm_success(self, sfm_result: SfmResult) -> None:
        self._working = False
        self._set_controls_enabled(True)
        self.app_state.refresh_scene_status()
        self._update_scene_label()
        self._set_progress(1.0)
        self._set_status(f"SfM finished. Output: {sfm_result.converted_model_path}", is_error=False)

    def _handle_error(self, exc: Exception) -> None:
        self._working = False
        self._set_controls_enabled(True)
        self._reset_progress()
        self.logger.exception("COLMAP operation failed")
        self._set_status(f"Operation failed: {exc}", is_error=True)

    def _set_status(self, message: str, *, is_error: bool = False) -> None:
        self.status_var.set(message)
        if self.status_label is not None:
            self.status_label.config(foreground="#a00" if is_error else "#444")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in self._interactive_controls:
            try:
                widget.configure(state=state)
            except Exception:
                continue

    def _clear_outputs(self, scene_id: str) -> bool:
        try:
            paths = self.app_state.scene_manager.get(scene_id).paths
            if paths.outputs_root.exists():
                shutil.rmtree(paths.outputs_root)
            self.logger.info("Cleared outputs for scene=%s at %s", scene_id, paths.outputs_root)
            return True
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Failed to clear outputs for scene %s", scene_id)
            self._set_status(f"Failed to clear outputs: {exc}", is_error=True)
            return False

    def _open_log_folder(self) -> None:
        scene = self.app_state.current_scene_id
        if scene is None:
            self._set_status("Select a scene to open its log folder.", is_error=True)
            return
        try:
            paths = self.app_state.scene_manager.get(str(scene)).paths
            log_dir = paths.sfm_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            import os

            os.startfile(str(log_dir))
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Failed to open log folder: {exc}", is_error=True)

    def _attach_log_handler(self) -> None:
        if self.log_view is None:
            return
        root_logger = logging.getLogger("nullsplats")
        if self._log_handler is not None:
            return

        class TkLogHandler(logging.Handler):
            def __init__(self, widget: scrolledtext.ScrolledText) -> None:
                super().__init__()
                self.widget = widget
                self._queue: "queue.SimpleQueue[str]" = queue.SimpleQueue()
                try:
                    self.widget.after(50, self._flush)
                except Exception:  # noqa: BLE001
                    pass

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    self._queue.put_nowait(msg)
                except Exception:  # noqa: BLE001
                    return

            def _flush(self) -> None:
                if not self.widget.winfo_exists():
                    return
                try:
                    self.widget.configure(state="normal")
                    while not self._queue.empty():
                        try:
                            msg = self._queue.get_nowait()
                        except Exception:  # noqa: BLE001
                            break
                        self.widget.insert("end", msg + "\n")
                    self.widget.see("end")
                    self.widget.configure(state="disabled")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.widget.after(50, self._flush)
                except Exception:  # noqa: BLE001
                    pass

        handler = TkLogHandler(self.log_view)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        root_logger.addHandler(handler)
        self._log_handler = handler


__all__ = ["ColmapTab"]
