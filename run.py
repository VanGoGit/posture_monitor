"""Точка входа — монитор осанки (для запуска из исходников и сборки PyInstaller)."""

from posture_monitor.gui import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
