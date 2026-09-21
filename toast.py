"""Всплывающее уведомление справа снизу экрана."""

from __future__ import annotations

import customtkinter as ctk

_STYLES = {
    "warn": {
        "frame": "#2a2024",
        "border": "#c04050",
        "accent": "#e04050",
        "title": "#f07070",
    },
    "info": {
        "frame": "#202428",
        "border": "#408060",
        "accent": "#40a060",
        "title": "#70d090",
    },
}


class ToastNotification:
    WIDTH = 360
    HEIGHT = 96
    MARGIN = 20
    TASKBAR_OFFSET = 48
    SLIDE_STEP_MS = 12
    SLIDE_STEPS = 14

    def __init__(self, parent: ctk.CTk) -> None:
        self._parent = parent
        self._window: ctk.CTkToplevel | None = None
        self._visible = False
        self._target_x = 0
        self._target_y = 0
        self._start_y = 0
        self._auto_hide_id: str | None = None

    def show(self, title: str, message: str, *, kind: str = "warn") -> None:
        if self._visible and self._window is not None:
            return

        style = _STYLES.get(kind, _STYLES["warn"])
        self._visible = True
        screen_w = self._parent.winfo_screenwidth()
        screen_h = self._parent.winfo_screenheight()
        self._target_x = screen_w - self.WIDTH - self.MARGIN
        self._target_y = screen_h - self.HEIGHT - self.MARGIN - self.TASKBAR_OFFSET
        self._start_y = screen_h

        win = ctk.CTkToplevel(self._parent)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{self._target_x}+{self._start_y}")
        self._window = win

        frame = ctk.CTkFrame(
            win,
            corner_radius=12,
            fg_color=style["frame"],
            border_width=1,
            border_color=style["border"],
        )
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        accent = ctk.CTkFrame(
            frame, width=4, corner_radius=2, fg_color=style["accent"]
        )
        accent.pack(side="left", fill="y", padx=(10, 0), pady=10)

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=10)

        ctk.CTkLabel(
            content,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=style["title"],
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            content,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color="#d0d0d8",
            anchor="w",
            wraplength=self.WIDTH - 70,
            justify="left",
        ).pack(fill="x", pady=(2, 0))

        ctk.CTkButton(
            frame,
            text="✕",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color="#4a3038",
            text_color="#909090",
            command=self.hide,
        ).pack(side="right", padx=(0, 8), pady=8)

        self._animate_in(0)

    def show_info(self, title: str, message: str, *, auto_hide_ms: int = 4000) -> None:
        self.show(title, message, kind="info")
        if self._auto_hide_id is not None:
            self._parent.after_cancel(self._auto_hide_id)
        self._auto_hide_id = self._parent.after(auto_hide_ms, self.hide)

    def hide(self) -> None:
        if self._auto_hide_id is not None:
            self._parent.after_cancel(self._auto_hide_id)
            self._auto_hide_id = None
        if not self._visible or self._window is None:
            return
        self._animate_out(0)

    def destroy(self) -> None:
        if self._auto_hide_id is not None:
            try:
                self._parent.after_cancel(self._auto_hide_id)
            except Exception:
                pass
            self._auto_hide_id = None
        self._visible = False
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    def _animate_in(self, step: int) -> None:
        if self._window is None:
            return

        progress = min(1.0, step / self.SLIDE_STEPS)
        eased = 1 - (1 - progress) ** 3
        y = int(self._start_y + (self._target_y - self._start_y) * eased)
        alpha = 0.4 + 0.6 * eased

        self._window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{self._target_x}+{y}")
        self._window.attributes("-alpha", alpha)

        if step < self.SLIDE_STEPS:
            self._parent.after(
                self.SLIDE_STEP_MS,
                lambda: self._animate_in(step + 1),
            )

    def _animate_out(self, step: int) -> None:
        if self._window is None:
            return

        progress = min(1.0, step / self.SLIDE_STEPS)
        eased = progress**2
        y = int(self._target_y + (self._start_y - self._target_y) * eased)
        alpha = max(0.0, 1.0 - progress)

        self._window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{self._target_x}+{y}")
        self._window.attributes("-alpha", alpha)

        if step < self.SLIDE_STEPS:
            self._parent.after(
                self.SLIDE_STEP_MS,
                lambda: self._animate_out(step + 1),
            )
        else:
            self.destroy()
