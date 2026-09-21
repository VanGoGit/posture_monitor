"""Графический интерфейс на CustomTkinter."""

from __future__ import annotations

import queue
import threading
import time
from tkinter import messagebox

import customtkinter as ctk
import cv2
from PIL import Image, ImageTk

from alarm import AlarmSiren
from camera_utils import CameraDevice, find_device, list_cameras
from config import DELTA_MAX, DELTA_MIN, Settings
from model_utils import ensure_model
from platform_utils import is_autostart_enabled, set_autostart
from posture_engine import PoseEngine, calibrate
from stats import StatsTracker
from toast import ToastNotification
from tray import TrayIcon
from worker import CameraWorker, WorkerCommand

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PostureMonitorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Монитор осанки")
        self.geometry("1100x780")
        self.minsize(900, 640)

        self.settings = Settings.load()
        self.siren = AlarmSiren()
        self._photo: ImageTk.PhotoImage | None = None
        self._last_metrics = None
        self._last_posture = None
        self._alarm_was_active = False
        self._previous_camera_index = self.settings.camera_index
        self._camera_state = "waiting"
        self._status_override: str | None = None
        self._status_override_until = 0.0
        self._stats = StatsTracker()
        self._toast = ToastNotification(self)
        self._tray: TrayIcon | None = None
        self._stop_event = threading.Event()
        self._result_queue: queue.Queue = queue.Queue(maxsize=2)
        self._command_queue: queue.Queue[WorkerCommand] = queue.Queue()

        self._engine = PoseEngine(str(ensure_model()))
        self._worker = CameraWorker(
            self._engine,
            self.settings,
            self._result_queue,
            self._command_queue,
            self._stop_event,
        )

        self.settings.autostart = is_autostart_enabled()
        self._build_ui()
        self._update_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.settings.minimize_to_tray:
            self._start_tray()
        self._worker.start()
        self.after(30, self._poll_results)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_settings_panel()
        self._build_video_panel()
        self._build_status_panel()
        if not self._cameras:
            self._show_no_camera()
        self._refresh_metric_labels()

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

        self.switch_skeleton = ctk.CTkSwitch(
            controls,
            text="Скелет",
            command=self._on_skeleton_toggle,
        )
        if self.settings.show_skeleton:
            self.switch_skeleton.select()
        self.switch_skeleton.grid(row=0, column=6, padx=(0, 10))

        self.switch_sound = ctk.CTkSwitch(
            controls,
            text="Звук",
            command=self._on_sound_toggle,
        )
        if self.settings.enable_sound:
            self.switch_sound.select()
        self.switch_sound.grid(row=0, column=7, padx=(0, 10))

        self.switch_notifications = ctk.CTkSwitch(
            controls,
            text="Уведомл.",
            command=self._on_notifications_toggle,
        )
        if self.settings.enable_notifications:
            self.switch_notifications.select()
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
            command=self._on_close,
            width=90,
            fg_color="#5a3340",
            hover_color="#7a4350",
        )
        self.btn_exit.grid(row=0, column=10)

        camera_row = ctk.CTkFrame(panel, fg_color="transparent")
        camera_row.grid(row=2, column=1, padx=8, pady=(0, 10), sticky="w")

        ctk.CTkLabel(camera_row, text="Камера").grid(row=0, column=0, padx=(0, 8))
        self._cameras: list[CameraDevice] = list_cameras()
        self.camera_box = ctk.CTkComboBox(
            camera_row,
            values=self._camera_labels(),
            command=self._on_camera_changed,
            width=320,
            state="readonly",
        )
        self._select_camera_in_box(self.settings.camera_index)
        self.camera_box.grid(row=0, column=1, padx=(0, 8))

        self.btn_refresh_cameras = ctk.CTkButton(
            camera_row,
            text="Обновить",
            command=self._refresh_cameras,
            width=100,
            fg_color="#3a3a48",
            hover_color="#4a4a58",
        )
        self.btn_refresh_cameras.grid(row=0, column=2)

        extra_row = ctk.CTkFrame(panel, fg_color="transparent")
        extra_row.grid(row=3, column=1, padx=8, pady=(0, 10), sticky="w")

        self.switch_tray = ctk.CTkSwitch(
            extra_row,
            text="Свернуть в трей",
            command=self._on_tray_toggle,
        )
        if self.settings.minimize_to_tray:
            self.switch_tray.select()
        self.switch_tray.grid(row=0, column=0, padx=(0, 14))

        self.switch_autostart = ctk.CTkSwitch(
            extra_row,
            text="Автозапуск",
            command=self._on_autostart_toggle,
        )
        if self.settings.autostart:
            self.switch_autostart.select()
        self.switch_autostart.grid(row=0, column=1, padx=(0, 14))

        self.btn_stats = ctk.CTkButton(
            extra_row,
            text="Статистика",
            command=self._show_stats,
            width=110,
            fg_color="#3a3a48",
            hover_color="#4a4a58",
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
            text="Сядьте ровно и нажмите «Калибровка»",
            font=ctk.CTkFont(size=16),
            anchor="center",
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

    def _on_delta_changed(self, value: float) -> None:
        self.settings.delta_degrees = int(round(value))
        self.lbl_delta.configure(text=f"{self.settings.delta_degrees}°")
        self.settings.save()
        self._refresh_metric_labels()

    def _on_delay_changed(self, value: float) -> None:
        self.settings.bad_posture_seconds = round(value, 1)
        self.lbl_delay.configure(text=f"{self.settings.bad_posture_seconds:.1f} с")
        self.settings.save()

    def _on_skeleton_toggle(self) -> None:
        self.settings.show_skeleton = bool(self.switch_skeleton.get())
        self.settings.save()

    def _on_sound_toggle(self) -> None:
        self.settings.enable_sound = bool(self.switch_sound.get())
        self.settings.save()
        if not self.settings.enable_sound:
            self.siren.stop()

    def _on_notifications_toggle(self) -> None:
        self.settings.enable_notifications = bool(self.switch_notifications.get())
        self.settings.save()
        if not self.settings.enable_notifications:
            self._toast.hide()

    def _on_tray_toggle(self) -> None:
        self.settings.minimize_to_tray = bool(self.switch_tray.get())
        self.settings.save()
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
            self.settings.save()
        except OSError as exc:
            messagebox.showerror("Автозапуск", f"Не удалось изменить автозапуск:\n{exc}")
            if enabled:
                self.switch_autostart.deselect()
            else:
                self.switch_autostart.select()

    def _start_tray(self) -> None:
        if self._tray is not None:
            return
        self._tray = TrayIcon(
            on_show=self._show_window,
            on_calibrate=self._on_calibrate,
            on_quit=self._shutdown,
        )
        self._tray.start()

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _show_status_message(self, text: str, *, seconds: float = 5.0) -> None:
        self._status_override = text
        self._status_override_until = time.time() + seconds
        self._update_status()

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

    def _camera_labels(self) -> list[str]:
        if self._cameras:
            return [d.label for d in self._cameras]
        return ["Нет камер"]

    def _select_camera_in_box(self, index: int) -> None:
        if not self._cameras:
            self.camera_box.set("Нет камер")
            return
        device = find_device(self._cameras, index)
        if device is not None:
            self.camera_box.set(device.label)
        else:
            self.camera_box.set(self._cameras[0].label)

    def _refresh_cameras(self) -> None:
        current_index = self.settings.camera_index
        self._cameras = list_cameras()
        self.camera_box.configure(values=self._camera_labels())
        if not self._cameras:
            self._camera_state = "waiting"
            self._show_no_camera()
            self._update_status()
            return
        if find_device(self._cameras, current_index) is None:
            current_index = self._cameras[0].index
            self.settings.camera_index = current_index
            self.settings.save()
            self._command_queue.put(WorkerCommand("camera", current_index))
        self._select_camera_in_box(current_index)

    def _on_camera_changed(self, choice: str) -> None:
        if choice == "Нет камер":
            return
        device = next((d for d in self._cameras if d.label == choice), None)
        if device is None or device.index == self.settings.camera_index:
            return
        self._previous_camera_index = self.settings.camera_index
        self.settings.camera_index = device.index
        self.settings.save()
        self._command_queue.put(WorkerCommand("camera", device.index))

    def _revert_camera_selection(self) -> None:
        self.settings.camera_index = self._previous_camera_index
        self.settings.save()
        self._select_camera_in_box(self.settings.camera_index)

    def _on_calibrate(self) -> None:
        if self._last_metrics is None or not self._last_metrics.is_valid:
            messagebox.showwarning(
                "Калибровка",
                "Не удалось определить позу. Встаньте так, чтобы камера видела плечи и голову.",
            )
            return

        if calibrate(self.settings, self._last_metrics):
            self._command_queue.put(WorkerCommand("reset_bad"))
            self.siren.stop()
            self._refresh_metric_labels()
            msg = f"Шея: {self.settings.baseline_neck:.1f}°"
            if self.settings.baseline_back is not None:
                msg += f", спина: {self.settings.baseline_back:.1f}°"
            self._toast.show_info("Калибровка выполнена", msg)
            self._show_status_message(f"Эталон сохранён — {msg}")

    def _refresh_metric_labels(self) -> None:
        if self._last_metrics is not None:
            self.lbl_neck.configure(text=f"Шея: {self._last_metrics.display_neck}")
            self.lbl_back.configure(text=f"Спина: {self._last_metrics.display_back}")
        else:
            self.lbl_neck.configure(text="Шея: —")
            self.lbl_back.configure(text="Спина: —")

        if self.settings.baseline_neck is not None:
            neck = f"{self.settings.baseline_neck:.1f}°"
            back = (
                f" / {self.settings.baseline_back:.1f}°"
                if self.settings.baseline_back is not None
                else ""
            )
            self.lbl_baseline.configure(text=f"Эталон: {neck}{back}")
            threshold_neck = self.settings.baseline_neck + self.settings.delta_degrees
            threshold_back = (
                self.settings.baseline_back + self.settings.delta_degrees
                if self.settings.baseline_back is not None
                else None
            )
            if threshold_back is not None:
                self.lbl_threshold.configure(
                    text=f"Порог: {threshold_neck:.1f}° / {threshold_back:.1f}°"
                )
            else:
                self.lbl_threshold.configure(text=f"Порог: {threshold_neck:.1f}°")
        else:
            self.lbl_baseline.configure(text="Эталон: —")
            self.lbl_threshold.configure(text="Порог: —")

    def _show_no_camera(self) -> None:
        self._photo = None
        self.video_label.configure(
            image="",
            text="Камера не найдена\n\nВыберите устройство в списке\nили нажмите «Обновить»",
            font=ctk.CTkFont(size=18),
            text_color="#9090a0",
        )

    def _update_status(self) -> None:
        if (
            self._status_override
            and time.time() < self._status_override_until
        ):
            self.status_label.configure(
                text=self._status_override,
                text_color="#70d090",
            )
            return
        self._status_override = None

        if self._camera_state == "waiting":
            self.status_label.configure(
                text="Камера не найдена. Выберите устройство или нажмите «Обновить»",
                text_color="#e0a040",
            )
            return

        if self.settings.baseline_neck is None:
            text = "Сядьте ровно и нажмите «Калибровка» (или клавишу C)"
            color = "#e0a040"
        elif self._last_posture is None:
            text = "Ожидание данных с камеры…"
            color = "#909090"
        elif self._last_posture.alarm_active:
            text = "СУТУЛИШЬСЬ! ВЫПРЯМИТЕСЬ!"
            color = "#e04040"
        elif self._last_posture.posture_ok is True:
            text = "Осанка в норме"
            color = "#50c878"
        elif self._last_posture.bad_elapsed > 0:
            text = (
                f"Отклонение… {self._last_posture.bad_elapsed:.1f} с / "
                f"{self.settings.bad_posture_seconds:.1f} с"
            )
            color = "#e0a040"
        else:
            text = "Ожидание данных с камеры…"
            color = "#909090"

        self.status_label.configure(text=text, text_color=color)

    def _show_frame(self, frame) -> None:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        label_w = max(self.video_label.winfo_width(), 640)
        label_h = max(self.video_label.winfo_height(), 360)

        h, w = frame_rgb.shape[:2]
        scale = min(label_w / w, label_h / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))

        img = Image.fromarray(frame_rgb).resize((new_w, new_h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self._photo, text="")

    def _poll_results(self) -> None:
        if not self.winfo_exists():
            return

        try:
            while True:
                item = self._result_queue.get_nowait()
                if isinstance(item, str):
                    if item == "status:camera_waiting":
                        if self._camera_state != "waiting":
                            self._camera_state = "waiting"
                            self._show_no_camera()
                            self._update_status()
                        continue
                    if item.startswith("camera_error:"):
                        self._revert_camera_selection()
                        self._camera_state = "waiting"
                        self._show_no_camera()
                        self._update_status()
                        continue
                    continue

                self._camera_state = "connected"
                self._last_metrics = item.metrics
                self._last_posture = item.posture
                self._show_frame(item.frame)

                alarm_active = item.posture.alarm_active
                now = time.time()
                if alarm_active:
                    if not self._alarm_was_active:
                        self._stats.on_alarm_start(now=now)
                    if self.settings.enable_sound:
                        self.siren.start()
                    else:
                        self.siren.stop()
                    if (
                        self.settings.enable_notifications
                        and not self._alarm_was_active
                    ):
                        self._toast.show(
                            "Сутулость!",
                            "Выпрямите спину и поднимите голову.",
                        )
                else:
                    if self._alarm_was_active:
                        self._stats.on_alarm_end(now=now)
                    self.siren.stop()
                    if self._alarm_was_active:
                        self._toast.hide()
                self._alarm_was_active = alarm_active

                self._refresh_metric_labels()
                self._update_status()
        except queue.Empty:
            pass

        self.after(30, self._poll_results)

    def _on_close(self) -> None:
        if self.settings.minimize_to_tray:
            self.withdraw()
            return
        self._shutdown()

    def _shutdown(self) -> None:
        if self._alarm_was_active:
            self._stats.on_alarm_end(now=time.time())
        self._toast.destroy()
        if self._tray is not None:
            self._tray.stop()
        self._stop_event.set()
        self.siren.shutdown()
        try:
            self._engine.close()
        except Exception:
            pass
        self.destroy()

    def bind_shortcuts(self) -> None:
        self.bind("<c>", lambda _e: self._on_calibrate())
        self.bind("<C>", lambda _e: self._on_calibrate())
        self.bind("<q>", lambda _e: self._on_close())
        self.bind("<Q>", lambda _e: self._shutdown())
        self.bind("<plus>", lambda _e: self._bump_delta(1))
        self.bind("<equal>", lambda _e: self._bump_delta(1))
        self.bind("<minus>", lambda _e: self._bump_delta(-1))

    def _bump_delta(self, step: int) -> None:
        value = max(DELTA_MIN, min(DELTA_MAX, self.settings.delta_degrees + step))
        self.slider_delta.set(value)
        self._on_delta_changed(value)


def run_app() -> None:
    app = PostureMonitorApp()
    app.bind_shortcuts()
    app.mainloop()
