'''Dashboard I/O helpers.'''

import os
import tempfile
from pathlib import Path


def atomic_write_html(data: str, path: Path) -> None:
  parent = path.parent
  tmp_path_str = None
  try:
    with tempfile.NamedTemporaryFile(
      dir=parent, delete=False, mode='w', suffix='.tmp', encoding='utf-8',
      newline='\n',
    ) as tmp:
      tmp_path_str = tmp.name
      tmp.write(data)
      tmp.flush()
      os.fsync(tmp.fileno())
    os.replace(tmp_path_str, path)
    if os.name == 'posix':
      dir_fd = os.open(str(parent), os.O_RDONLY)
      try:
        os.fsync(dir_fd)
      finally:
        os.close(dir_fd)
    tmp_path_str = None
  finally:
    if tmp_path_str is not None:
      try:
        os.unlink(tmp_path_str)
      except FileNotFoundError:
        pass
