"""
main.py
-------
Entry point for the IFC → DXF Converter desktop application.
Run directly:   python main.py
Frozen by PyInstaller, the generated .exe invokes this module.
"""

import sys
import os

# When running as a PyInstaller --onefile bundle the temp extraction
# directory is sys._MEIPASS; make sure local imports still resolve.
if hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)

from gui import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
