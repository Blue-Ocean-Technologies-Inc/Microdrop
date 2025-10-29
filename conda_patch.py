import shutil
from pathlib import Path

# Patches should be idempotent (i.e., can be applied multiple times without changing the result beyond the initial application).
# This allows re-running the patch script without worrying about whether a patch has already been applied.


def main():
    # Patch pyface/toolkit.py to use Qt toolkit
    # This patch is applied to make dynamic import explicit for PyInstaller.
    # See https://github.com/enthought/pyface/issues/350#issuecomment-632545893
    import pyface.toolkit as toolkit
    shutil.copy2("patches/toolkit.py", str(Path(toolkit.__file__).parent / "toolkit.py"))

if __name__ == "__main__":
    main()