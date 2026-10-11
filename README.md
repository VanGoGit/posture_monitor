# Монитор осанки

Приложение следит через веб-камеру за осанкой (наклон шеи и спины), предупреждает на экране и подаёт звуковой сигнал.

## Требования

- Python **3.11+** (рекомендуется 3.12 или 3.13)
- Веб-камера
- Windows / macOS / Linux

## Установка

```powershell
cd posture_monitor
py -m pip install -r requirements.txt
```

Для разработки и сборки:

```powershell
py -m pip install -r requirements-dev.txt
```

При первом запуске скачается модель Pose Landmarker (~6 МБ) в `models/` (с проверкой SHA-256).

## Запуск

```powershell
py posture_monitor.py
```

## Возможности

- Калибровка эталонной осанки
- Контроль шеи и спины
- Звук и всплывающие уведомления (можно отключить)
- Выбор камеры с авто-переподключением
- **Статистика** срабатываний за день и за 7 дней
- **Свернуть в трей** — мониторинг в фоне
- **Автозапуск** с системой (Windows / Linux / macOS)

### Горячие клавиши

| Клавиша | Действие |
|---|---|
| `C` (`С` в русской раскладке) | Калибровка |
| `+` / `-` | Допуск ±1° |
| `Q` (`Й`) | Свернуть в трей (если включено) или выход |

## Сборка exe (Windows)

```powershell
py -m pip install -r requirements-lock.txt pyinstaller
py -c "from model_utils import ensure_model; ensure_model()"
py -m PyInstaller build.spec --noconfirm
```

Готовый файл: `dist\PostureMonitor.exe`. CI собирает его на каждый push в `main` (артефакт `PostureMonitor-windows`).

`requirements-lock.txt` — проверенные точные версии зависимостей для воспроизводимой сборки.

> **pyinstaller не в PATH?** Используйте `py -m PyInstaller` вместо `pyinstaller`.  
> **PermissionError при сборке?** Закройте запущенный `PostureMonitor.exe` и повторите.

## Тесты и проверки

```powershell
pytest -q
ruff check .
ruff format --check .
mypy .
```

## Структура

```
posture_monitor/
  posture_monitor.py    # точка входа
  gui.py                # интерфейс
  posture_engine.py     # MediaPipe + алгоритм
  worker.py             # камера в фоне, сообщения GUI ⇄ поток
  video_renderer.py     # отрисовка скелета на кадре
  alarm.py              # звуковой сигнал
  alarm_controller.py   # реакция на тревогу (звук, уведомление, статистика)
  stats.py              # статистика
  tray.py               # системный трей
  toast.py              # всплывающие уведомления
  camera_utils.py       # поиск камер
  model_utils.py        # загрузка модели
  platform_utils.py     # камера/автозапуск по ОС
  paths.py              # папка данных, атомарная запись
  app_logging.py        # лог-файл
  config.py             # settings.json
  tests/                # pytest
  build.spec            # PyInstaller
```

## Кросс-платформенность

| Компонент | Windows | macOS | Linux |
|---|---|---|---|
| UI | ✅ | ✅ | ✅ |
| Камера | DirectShow | AVFoundation | V4L2 |
| Имена камер | pygrabber | номер | номер |
| Звук | winsound | afplay | paplay/aplay |
| Автозапуск | реестр | LaunchAgent | .desktop |
| Трей | ✅ | ✅ | ✅ |

## Настройки и данные

`settings.json`, `stats.json` и лог `posture_monitor.log` хранятся в папке пользователя:

| ОС | Папка |
|---|---|
| Windows | `%APPDATA%\PostureMonitor` |
| macOS | `~/Library/Application Support/PostureMonitor` |
| Linux | `~/.config/posturemonitor` (или `$XDG_CONFIG_HOME`) |

Папку можно переопределить переменной окружения `POSTURE_MONITOR_DATA_DIR`. Файлы старых версий (рядом с программой) переносятся автоматически.

> После обновления до версии 0.2 перекалибруйте осанку: исправлен расчёт угла спины, старый эталон спины сбрасывается.

## Лицензия

[MIT](LICENSE)
