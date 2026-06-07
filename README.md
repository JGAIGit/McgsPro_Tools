# McgsPro_Tools

McgsPro_Tools contains two PySide6 desktop utilities for editing MCGS Pro XML configuration files.

## Files

- `McgsPro_multi_language.py` - XML import/export editor for multilingual text configuration.
- `McgsPro_new_alarm_input.py` - Alarm configuration editor for generating and editing alarm XML entries.

## Requirements

- Python 3.9+
- PySide6

Install dependencies:

```bash
pip install PySide6
```

China mirror examples:

```bash
pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install PySide6 -i https://mirrors.aliyun.com/pypi/simple
```

## Usage

Run the multilingual text editor:

```bash
python McgsPro_multi_language.py
```

Run the alarm editor:

```bash
python McgsPro_new_alarm_input.py
```

Both tools provide a GUI for opening, editing, and exporting XML files used by MCGS Pro projects.

## Notes

- Keep a backup of the original XML files before batch editing.
- If Chinese text appears garbled, check that the source XML and Python files are opened with the expected text encoding.
