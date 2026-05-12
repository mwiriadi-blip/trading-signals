'''dashboard_legacy retired — all rendering lives in dashboard_renderer.

Any attribute access or submodule-style import raises ImportError to catch
accidental re-introduction. Setting __path__ = [] makes submodule imports
(e.g. `import dashboard_legacy.render_helpers`) fall back to __getattr__,
so they raise ImportError (not ModuleNotFoundError) with the locked message.
'''
import sys

__path__ = []


class _RetiredSubmoduleFinder:
  '''Meta-path finder that intercepts dashboard_legacy.* submodule imports
  and raises ImportError with the locked retirement message — ensuring
  the exception type is ImportError (not ModuleNotFoundError) on Python 3.13.
  Only intercepts strict submodule paths (contains a dot after the package name).
  '''

  def find_spec(self, fullname, path, target=None):
    if fullname.startswith('dashboard_legacy.'):
      raise ImportError("dashboard_legacy retired — use dashboard_renderer")
    return None


_finder = _RetiredSubmoduleFinder()
if not any(
  type(f).__name__ == '_RetiredSubmoduleFinder' for f in sys.meta_path
):
  sys.meta_path.insert(0, _finder)


def __getattr__(name):
  raise ImportError("dashboard_legacy retired — use dashboard_renderer")
