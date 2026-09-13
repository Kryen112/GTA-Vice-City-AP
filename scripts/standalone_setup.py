"""Windows entry point; build_setup.py supplies the shared installer package."""

import shutil
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import setup_dependencies
from gta_vc_setup import installer, setup


def open_directory(title):
    return filedialog.askdirectory(title=title, mustexist=True)


def show_message(title, text, *, error=False):
    show = messagebox.showerror if error else messagebox.showinfo
    show(title, text)


def verify_payload(stock_script):
    """Check the frozen runtime and all bundled script patches without installing."""
    with tempfile.TemporaryDirectory() as temporary:
        game = Path(temporary)
        (game / "data").mkdir()
        shutil.copyfile(stock_script, game / "data/main.scm")
        files = installer.materialize_payload(game)
        if {name for name, _ in files} != set(installer.SHIPPED_PAYLOAD_PATHS) | {"main.scm"}:
            raise RuntimeError("Incomplete setup payload")


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--verify-payload":
            try:
                verify_payload(sys.argv[2])
            except Exception:
                sys.exit(1)
        else:
            setup.launch(open_directory=open_directory, messagebox=show_message,
                         before_install=setup_dependencies.install)
    finally:
        root.destroy()
