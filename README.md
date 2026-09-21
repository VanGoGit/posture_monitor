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

При первом запуске скачается модель Pose Landmarker (~6 МБ) в `models/`.

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
| `C` | Калибровка |
| `+` / `-` | Допуск ±1° |
| `Q` | Свернуть в трей или выход |

## Сборка exe (Windows)

```powershell
py -m pip install pyinstaller
py posture_monitor.py   # скачает модель, если её ещё нет
py -m PyInstaller build.spec --noconfirm
```

Готовый файл: `dist\PostureMonitor.exe`

> **pyinstaller не в PATH?** Используйте `py -m PyInstaller` вместо `pyinstaller`.  
> **PermissionError при сборке?** Закройте запущенный `PostureMonitor.exe` и повторите.

## Тесты

```powershell
pytest tests/ -q
```

## Структура

```
posture_monitor/
  posture_monitor.py    # точка входа
  gui.py                # интерфейс
  posture_engine.py     # MediaPipe + алгоритм
  worker.py             # камера в фоне
  stats.py              # статистика
  tray.py               # системный трей
  platform_utils.py     # камера/автозапуск по ОС
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

## Настройки

Сохраняются в `settings.json`, статистика — в `stats.json`.
