"""Графический интерфейс на CustomTkinter."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from . import __version__
from .alarm import AlarmSiren
from .alarm_controller import AlarmController
from .app_logging import setup_logging
from .camera_utils import CameraDevice, find_device, list_cameras
from .config import DELTA_MAX, DELTA_MIN, Settings
from .model_utils import ensure_model
from .platform_utils import is_autostart_enabled, set_autostart
from .posture_engine import FrameResult, PoseEngine, PostureMetrics, PostureState, calibrate
from .stats import StatsTracker
from .toast import ToastNotification
from .tray import TrayIcon
from .worker import (
    CameraSwitchFailed,
    CameraWaiting,
    CameraWorker,
    ResetBadPosture,
    SwitchCamera,
    UpdateSettings,
    WorkerCommand,
    WorkerMessage,
)

log = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

POLL_MS = 30
SAVE_DEBOUNCE_MS = 500
WORKER_JOIN_SECONDS = 3.0
NO_CAMERAS_LABEL = "Нет камер"
SEARCHING_CAMERAS_LABEL = "Поиск камер…"

COLOR_OK = "#50c878"
COLOR_WARN = "#e0a040"
COLOR_ALARM = "#e04040"
COLOR_MUTED = "#909090"
COLOR_INFO = "#70d090"
COLOR_SECONDARY_BTN = "#3a3a48"
COLOR_SECONDARY_BTN_HOVER = "#4a4a58"


class PostureMonitorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"Монитор осанки {__version__}")
        self.geometry("1100x780")
        self.minsize(900, 640)

        self.settings = Settings.load()
        self.siren = AlarmSiren()
        self._photo: ImageTk.PhotoImage | None = None
        self._last_metrics: PostureMetrics | None = None
        self._last_posture: PostureState | None = None
        self._previous_camera_index = self.settings.camera_index
        # starting → (модель загружена) waiting ⇄ connected; error — модель не загрузилась
        self._camera_state = "starting"
        self._cameras: list[CameraDevice] = []
        self._scanning_cameras = False
        self._status_override: str | None = None
        self._status_override_until = 0.0
        self._save_after_id: str | None = None
        self._closing = False
        self._stats = StatsTracker()
        self._toast = ToastNotification(self)
        self._alarm = AlarmController(self.siren, self._toast, self._stats)
        self._tray: TrayIcon | None = None
        self._stop_event = threading.Event()
        self._result_queue: queue.Queue[WorkerMessage] = queue.Queue(maxsize=2)
        self._command_queue: queue.Queue[WorkerCommand] = queue.Queue()
        # Вызовы из чужих потоков (трей, фоновые задачи) выполняются в UI-потоке.
        self._ui_calls: queue.Queue[Callable[[], None]] = queue.Queue()
        self._engine: PoseEngine | None = None
        self._worker: CameraWorker | None = None

        self.settings.autostart = is_autostart_enabled()
        if self.settings.autostart:
            # Обновить команду запуска: программа могла переехать или смениться точка входа.
            try:
                set_autostart(True)
            except OSError:
                log.warning("Не удалось обновить запись автозапуска", exc_info=True)
        self._build_ui()
        self._update_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.settings.minimize_to_tray:
            self._start_tray()
        self._run_in_background(self._load_engine, name="ModelLoader")
        self._refresh_cameras()
        self.after(POLL_MS, self._poll_results)

    # --- Потоки ---

    def _call_in_ui(self, func: Callable[[], None]) -> None:
        """Потокобезопасно запланировать вызов в UI-потоке."""
        self._ui_calls.put(func)

    @staticmethod
    def _run_in_background(func: Callable[[], None], *, name: str) -> None:
        threading.Thread(target=func, daemon=True, name=name).start()

    def _load_engine(self) -> None:
        try:
            engine = PoseEngine(str(ensure_model()))
        except Exception as exc:
            log.exception("Не удалось загрузить модель")
            message = str(exc)
            self._call_in_ui(lambda: self._on_engine_failed(message))
            return
        self._call_in_ui(lambda: self._on_engine_ready(engine))

    def _on_engine_ready(self, engine: PoseEngine) -> None:
        if self._closing:
            engine.close()
            return
        self._engine = engine
        self._camera_state = "waiting"
        self._worker = CameraWorker(
            engine,
            self.settings,
            self._result_queue,
            self._command_queue,
            self._stop_event,
        )
        self._worker.start()
        self._update_status()

    def _on_engine_failed(self, message: str) -> None:
        self._camera_state = "error"
        self._show_video_placeholder("Модель распознавания позы не загружена")
        self._update_status()
        messagebox.showerror(
            "Модель",
            f"Не удалось загрузить модель распознавания позы:\n{message}\n\n"
            "Проверьте подключение к интернету и перезапустите приложение.",
        )

    # --- Построение интерфейса ---

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_settings_panel()
        self._build_video_panel()
        self._build_status_panel()
        self._show_video_placeholder("Загрузка…")
        self._refresh_metric_labels()

    def _make_switch(
        self, parent: ctk.CTkFrame, text: str, value: bool, command: Callable[[], None]
    ) -> ctk.CTkSwitch:
        switch = ctk.CTkSwitch(parent, text=text, command=command)
        if value:
            switch.select()
        return switch

    def _build_settings_panel(self) -> None:
        panel = ctk.CTkFrame(self, corner_radius=0)
        panel.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        panel.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            panel,
            text="Монитор осанки",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=0, rowspan=4, padx=16, pady=12, sticky="nw")

        metrics_frame = ctk.CTkFrame(panel, fg_color="transparent")
        metrics_frame.grid(row=0, column=1, padx=8, pady=(10, 0), sticky="w")

        self.lbl_neck = ctk.CTkLabel(metrics_frame, text="Шея: —")
        self.lbl_neck.grid(row=0, column=0, padx=(0, 16), sticky="w")
        self.lbl_back = ctk.CTkLabel(metrics_frame, text="Спина: —")
        self.lbl_back.grid(row=0, column=1, padx=(0, 16), sticky="w")
        self.lbl_baseline = ctk.CTkLabel(metrics_frame, text="Эталон: —")
        self.lbl_baseline.grid(row=0, column=2, padx=(0, 16), sticky="w")
        self.lbl_threshold = ctk.CTkLabel(metrics_frame, text="Порог: —")
        self.lbl_threshold.grid(row=0, column=3, sticky="w")

        controls = ctk.CTkFrame(panel, fg_color="transparent")
        controls.grid(row=1, column=1, padx=8, pady=(4, 10), sticky="ew")
        controls.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(controls, text="Допуск").grid(row=0, column=0, padx=(0, 6))
        self.slider_delta = ctk.CTkSlider(
            controls,
            from_=DELTA_MIN,
            to=DELTA_MAX,
            number_of_steps=DELTA_MAX - DELTA_MIN,
            command=self._on_delta_changed,
            width=160,
        )
        self.slider_delta.set(self.settings.delta_degrees)
        self.slider_delta.grid(row=0, column=1, padx=(0, 6))
        self.lbl_delta = ctk.CTkLabel(controls, text=f"{self.settings.delta_degrees}°", width=36)
        self.lbl_delta.grid(row=0, column=2, padx=(0, 14))

        ctk.CTkLabel(controls, text="Задержка").grid(row=0, column=3, padx=(0, 6))
        self.slider_delay = ctk.CTkSlider(
            controls,
            from_=0.5,
            to=5.0,
            number_of_steps=9,
            command=self._on_delay_changed,
            width=120,
        )
        self.slider_delay.set(self.settings.bad_posture_seconds)
        self.slider_delay.grid(row=0, column=4, padx=(0, 6))
        self.lbl_delay = ctk.CTkLabel(
            controls, text=f"{self.settings.bad_posture_seconds:.1f} с", width=48
        )
        self.lbl_delay.grid(row=0, column=5, padx=(0, 14), sticky="w")

        self.switch_skeleton = self._make_switch(
            controls, "Скелет", self.settings.show_skeleton, self._on_skeleton_toggle
        )
        self.switch_skeleton.grid(row=0, column=6, padx=(0, 10))

        self.switch_sound = self._make_switch(
            controls, "Звук", self.settings.enable_sound, self._on_sound_toggle
        )
        self.switch_sound.grid(row=0, column=7, padx=(0, 10))

        self.switch_notifications = self._make_switch(
            controls,
            "Уведомл.",
            self.settings.enable_notifications,
            self._on_notifications_toggle,
        )
        self.switch_notifications.grid(row=0, column=8, padx=(0, 10))

        self.btn_calibrate = ctk.CTkButton(
            controls,
            text="Калибровка",
            command=self._on_calibrate,
            width=120,
        )
        self.btn_calibrate.grid(row=0, column=9, padx=(0, 8))

        self.btn_exit = ctk.CTkButton(
            controls,
            text="Выход",
            command=self._shutdown,
            width=90,
            fg_color="#5a3340",
            hover_color="#7a4350",
        )
        self.btn_exit.grid(row=0, column=10)

        camera_row = ctk.CTkFrame(panel, fg_color="transparent")
        camera_row.grid(row=2, column=1, padx=8, pady=(0, 10), sticky="w")

        ctk.CTkLabel(camera_row, text="Камера").grid(row=0, column=0, padx=(0, 8))
        self.camera_box = ctk.CTkComboBox(
            camera_row,
            values=[SEARCHING_CAMERAS_LABEL],
            command=self._on_camera_changed,
            width=320,
            state="readonly",
        )
        self.camera_box.set(SEARCHING_CAMERAS_LABEL)
        self.camera_box.grid(row=0, column=1, padx=(0, 8))

        self.btn_refresh_cameras = ctk.CTkButton(
            camera_row,
            text="Обновить",
            command=self._refresh_cameras,
            width=100,
            fg_color=COLOR_SECONDARY_BTN,
            hover_color=COLOR_SECONDARY_BTN_HOVER,
        )
        self.btn_refresh_cameras.grid(row=0, column=2)

        extra_row = ctk.CTkFrame(panel, fg_color="transparent")
        extra_row.grid(row=3, column=1, padx=8, pady=(0, 10), sticky="w")

        self.switch_tray = self._make_switch(
            extra_row, "Свернуть в трей", self.settings.minimize_to_tray, self._on_tray_toggle
        )
        self.switch_tray.grid(row=0, column=0, padx=(0, 14))

        self.switch_autostart = self._make_switch(
            extra_row, "Автозапуск", self.settings.autostart, self._on_autostart_toggle
        )
        self.switch_autostart.grid(row=0, column=1, padx=(0, 14))

        self.btn_stats = ctk.CTkButton(
            extra_row,
            text="Статистика",
            command=self._show_stats,
            width=110,
            fg_color=COLOR_SECONDARY_BTN,
            hover_color=COLOR_SECONDARY_BTN_HOVER,
        )
        self.btn_stats.grid(row=0, column=2)

    def _build_video_panel(self) -> None:
        self.video_frame = ctk.CTkFrame(self, fg_color="#141418")
        self.video_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(8, 8))
        self.video_frame.grid_columnconfigure(0, weight=1)
        self.video_frame.grid_rowconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(self.video_frame, text="")
        self.video_label.grid(row=0, column=0, sticky="nsew")

    def _build_status_panel(self) -> None:
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=16),
            anchor="center",
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

    # --- Настройки ---

    def _settings_changed(self) -> None:
        """Передать настройки потоку камеры и сохранить их с задержкой."""
        self._command_queue.put(UpdateSettings(replace(self.settings)))
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
        self._save_after_id = self.after(SAVE_DEBOUNCE_MS, self._save_settings)

    def _save_settings(self) -> None:
        if self._save_after_id is not None:
            self.after_cancel(self._save_after_id)
            self._save_after_id = None
        try:
            self.settings.save()
        except OSError:
            log.exception("Не удалось сохранить настройки")

    def _on_delta_changed(self, value: float) -> None:
        delta = round(value)
        if delta == self.settings.delta_degrees:
            return
        self.settings.delta_degrees = delta
        self.lbl_delta.configure(text=f"{delta}°")
        self._settings_changed()
        self._refresh_metric_labels()

    def _on_delay_changed(self, value: float) -> None:
        delay = round(value, 1)
        if delay == self.settings.bad_posture_seconds:
            return
        self.settings.bad_posture_seconds = delay
        self.lbl_delay.configure(text=f"{delay:.1f} с")
        self._settings_changed()

    def _on_skeleton_toggle(self) -> None:
        self.settings.show_skeleton = bool(self.switch_skeleton.get())
        self._settings_changed()

    def _on_sound_toggle(self) -> None:
        self.settings.enable_sound = bool(self.switch_sound.get())
        self._settings_changed()
        if not self.settings.enable_sound:
            self.siren.stop()

    def _on_notifications_toggle(self) -> None:
        self.settings.enable_notifications = bool(self.switch_notifications.get())
        self._settings_changed()
        if not self.settings.enable_notifications:
            self._toast.hide()

    def _on_tray_toggle(self) -> None:
        self.settings.minimize_to_tray = bool(self.switch_tray.get())
        self._settings_changed()
        if self.settings.minimize_to_tray:
            self._start_tray()
        elif self._tray is not None:
            self._tray.stop()
            self._tray = None

    def _on_autostart_toggle(self) -> None:
        enabled = bool(self.switch_autostart.get())
        try:
            set_autostart(enabled)
            self.settings.autostart = enabled
            self._settings_changed()
        except OSError as exc:
            log.exception("Не удалось изменить автозапуск")
            messagebox.showerror("Автозапуск", f"Не удалось изменить автозапуск:\n{exc}")
            if enabled:
                self.switch_autostart.deselect()
            else:
                self.switch_autostart.select()

    def _bump_delta(self, step: int) -> None:
        value = max(DELTA_MIN, min(DELTA_MAX, self.settings.delta_degrees + step))
        self.slider_delta.set(value)
        self._on_delta_changed(value)

    # --- Трей и окна ---

    def _start_tray(self) -> None:
        if self._tray is not None:
            return
        # Колбэки pystray приходят из потока трея — Tk трогать оттуда нельзя.
        self._tray = TrayIcon(
            on_show=lambda: self._call_in_ui(self._show_window),
            on_calibrate=lambda: self._call_in_ui(self._on_calibrate),
            on_quit=lambda: self._call_in_ui(self._shutdown),
        )
        if not self._tray.start():
            log.warning("Системный трей недоступен")
            self._tray = None

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _show_stats(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Статистика осанки")
        win.geometry("420x360")
        win.transient(self)
        ctk.CTkLabel(
            win,
            text=self._stats.format_summary(),
            font=ctk.CTkFont(size=14),
            justify="left",
            anchor="nw",
        ).pack(fill="both", expand=True, padx=16, pady=16)

    # --- Камеры ---

    def _camera_labels(self) -> list[str]:
        if self._cameras:
            return [d.label for d in self._cameras]
        return [NO_CAMERAS_LABEL]

    def _select_camera_in_box(self, index: int) -> None:
        if not self._cameras:
            self.camera_box.set(NO_CAMERAS_LABEL)
            return
        device = find_device(self._cameras, index)
        self.camera_box.set(device.label if device is not None else self._cameras[0].label)

    def _refresh_cameras(self) -> None:
        """Перебор камер занимает секунды (DirectShow), поэтому идёт в фоне."""
        if self._scanning_cameras:
            return
        self._scanning_cameras = True
        self.btn_refresh_cameras.configure(state="disabled")
        # Камеру, открытую потоком, повторно не открыть — считаем её доступной.
        in_use = {self.settings.camera_index} if self._camera_state == "connected" else set()

        def scan() -> None:
            try:
                cameras = list_cameras(assume_available=in_use)
            except Exception:
                log.exception("Не удалось получить список камер")
                cameras = []
            self._call_in_ui(lambda: self._on_cameras_listed(cameras))

        self._run_in_background(scan, name="CameraScan")

    def _on_cameras_listed(self, cameras: list[CameraDevice]) -> None:
        self._scanning_cameras = False
        self.btn_refresh_cameras.configure(state="normal")
        self._cameras = cameras
        self.camera_box.configure(values=self._camera_labels())
        if not cameras:
            self._select_camera_in_box(self.settings.camera_index)
            if self._camera_state == "waiting":
                self._show_no_camera()
            self._update_status()
            return
        if find_device(cameras, self.settings.camera_index) is None:
            self._switch_camera(cameras[0].index)
        self._select_camera_in_box(self.settings.camera_index)

    def _switch_camera(self, index: int) -> None:
        self._previous_camera_index = self.settings.camera_index
        self.settings.camera_index = index
        self._save_settings()
        self._command_queue.put(SwitchCamera(index))

    def _on_camera_changed(self, choice: str) -> None:
        device = next((d for d in self._cameras if d.label == choice), None)
        if device is None or device.index == self.settings.camera_index:
            return
        self._switch_camera(device.index)

    def _revert_camera_selection(self) -> None:
        self.settings.camera_index = self._previous_camera_index
        self._save_settings()
        self._select_camera_in_box(self.settings.camera_index)

    # --- Калибровка и отображение ---

    def _on_calibrate(self) -> None:
        if self._last_metrics is None or not self._last_metrics.is_valid:
            messagebox.showwarning(
                "Калибровка",
                "Не удалось определить позу. Встаньте так, чтобы камера видела плечи и голову.",
            )
            return

        if calibrate(self.settings, self._last_metrics):
            self._command_queue.put(UpdateSettings(replace(self.settings)))
            self._command_queue.put(ResetBadPosture())
            self.siren.stop()
            self._refresh_metric_labels()
            msg = f"Шея: {self.settings.baseline_neck:.1f}°"
            if self.settings.baseline_back is not None:
                msg += f", спина: {self.settings.baseline_back:.1f}°"
            self._toast.show_info("Калибровка выполнена", msg)
            self._show_status_message(f"Эталон сохранён — {msg}")

    def _show_status_message(self, text: str, *, seconds: float = 5.0) -> None:
        self._status_override = text
        self._status_override_until = time.monotonic() + seconds
        self._update_status()

    def _refresh_metric_labels(self) -> None:
        if self._last_metrics is not None:
            self.lbl_neck.configure(text=f"Шея: {self._last_metrics.display_neck}")
            self.lbl_back.configure(text=f"Спина: {self._last_metrics.display_back}")
        else:
            self.lbl_neck.configure(text="Шея: —")
            self.lbl_back.configure(text="Спина: —")

        baseline_neck = self.settings.baseline_neck
        baseline_back = self.settings.baseline_back
        if baseline_neck is None:
            self.lbl_baseline.configure(text="Эталон: —")
            self.lbl_threshold.configure(text="Порог: —")
            return

        delta = self.settings.delta_degrees
        baseline = f"{baseline_neck:.1f}°"
        threshold = f"{baseline_neck + delta:.1f}°"
        if baseline_back is not None:
            baseline += f" / {baseline_back:.1f}°"
            threshold += f" / {baseline_back + delta:.1f}°"
        self.lbl_baseline.configure(text=f"Эталон: {baseline}")
        self.lbl_threshold.configure(text=f"Порог: {threshold}")

    def _show_video_placeholder(self, text: str) -> None:
        self._photo = None
        self.video_label.configure(
            image="",
            text=text,
            font=ctk.CTkFont(size=18),
            text_color="#9090a0",
        )

    def _show_no_camera(self) -> None:
        self._show_video_placeholder(
            "Камера не найдена\n\nВыберите устройство в списке\nили нажмите «Обновить»"
        )

    def _status_text(self) -> tuple[str, str]:
        if self._camera_state == "starting":
            return "Загрузка модели распознавания позы…", COLOR_MUTED
        if self._camera_state == "error":
            return "Модель не загружена — перезапустите приложение", COLOR_ALARM
        if self._camera_state == "waiting":
            return "Камера не найдена. Выберите устройство или нажмите «Обновить»", COLOR_WARN

        posture = self._last_posture
        if self.settings.baseline_neck is None:
            return "Сядьте ровно и нажмите «Калибровка» (или клавишу C)", COLOR_WARN
        if posture is None:
            return "Ожидание данных с камеры…", COLOR_MUTED
        if posture.alarm_active:
            return "ВЫ СУТУЛИТЕСЬ! ВЫПРЯМИТЕСЬ!", COLOR_ALARM
        if posture.posture_ok is True:
            return "Осанка в норме", COLOR_OK
        if posture.bad_elapsed > 0:
            return (
                f"Отклонение… {posture.bad_elapsed:.1f} с / "
                f"{self.settings.bad_posture_seconds:.1f} с",
                COLOR_WARN,
            )
        return "Ожидание данных с камеры…", COLOR_MUTED

    def _update_status(self) -> None:
        if self._status_override and time.monotonic() < self._status_override_until:
            self.status_label.configure(text=self._status_override, text_color=COLOR_INFO)
            return
        self._status_override = None
        text, color = self._status_text()
        self.status_label.configure(text=text, text_color=color)

    def _show_frame(self, frame: Any) -> None:
        label_w = max(self.video_label.winfo_width(), 640)
        label_h = max(self.video_label.winfo_height(), 360)

        h, w = frame.shape[:2]
        scale = min(label_w / w, label_h / h)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        # cv2.resize заметно быстрее PIL LANCZOS, а UI-поток обрабатывает каждый кадр.
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(frame, size, interpolation=interpolation)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.video_label.configure(image=self._photo, text="")

    # --- Цикл опроса ---

    def _poll_results(self) -> None:
        if self._closing:
            return

        while True:
            try:
                call = self._ui_calls.get_nowait()
            except queue.Empty:
                break
            try:
                call()
            except Exception:
                log.exception("Ошибка в отложенном вызове UI")
            if self._closing:
                return

        while True:
            try:
                item = self._result_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_worker_message(item)

        self.after(POLL_MS, self._poll_results)

    def _handle_worker_message(self, item: WorkerMessage) -> None:
        if isinstance(item, CameraWaiting):
            if self._camera_state != "waiting":
                self._camera_state = "waiting"
                self._show_no_camera()
                self._update_status()
        elif isinstance(item, CameraSwitchFailed):
            self._revert_camera_selection()
            self._update_status()
        else:
            self._handle_frame(item)

    def _handle_frame(self, item: FrameResult) -> None:
        self._camera_state = "connected"
        self._last_metrics = item.metrics
        self._last_posture = item.posture
        self._show_frame(item.frame)
        self._alarm.update(item.posture.alarm_active, self.settings, now=time.monotonic())
        self._refresh_metric_labels()
        self._update_status()

    # --- Завершение ---

    def _on_close(self) -> None:
        if self.settings.minimize_to_tray and self._tray is not None:
            self.withdraw()
            return
        self._shutdown()

    def _shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._alarm.finish(now=time.monotonic())
        self._save_settings()
        self._toast.destroy()
        if self._tray is not None:
            self._tray.stop()
        self._stop_event.set()
        # Модель закрываем только после остановки потока, иначе гонка с process().
        worker_stopped = True
        if self._worker is not None:
            self._worker.join(timeout=WORKER_JOIN_SECONDS)
            worker_stopped = not self._worker.is_alive()
            if not worker_stopped:
                log.warning("Поток камеры не завершился за %s с", WORKER_JOIN_SECONDS)
        self.siren.shutdown()
        if self._engine is not None and worker_stopped:
            try:
                self._engine.close()
            except Exception:
                log.exception("Ошибка при закрытии модели")
        self.destroy()

    def bind_shortcuts(self) -> None:
        # Cyrillic_* — те же физические клавиши в русской раскладке (C → С, Q → Й).
        for key in ("c", "C", "Cyrillic_es", "Cyrillic_ES"):
            self.bind(f"<{key}>", lambda _e: self._on_calibrate())
        for key in ("q", "Q", "Cyrillic_shorti", "Cyrillic_SHORTI"):
            self.bind(f"<{key}>", lambda _e: self._on_close())
        for key in ("plus", "equal", "KP_Add"):
            self.bind(f"<{key}>", lambda _e: self._bump_delta(1))
        for key in ("minus", "KP_Subtract"):
            self.bind(f"<{key}>", lambda _e: self._bump_delta(-1))


def run_app() -> None:
    setup_logging()
    app = PostureMonitorApp()
    app.bind_shortcuts()
    app.mainloop()
