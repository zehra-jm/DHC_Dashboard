"""DHC Rate Board as a desktop app: the live dashboard in its own window.

The window keeps its own storage (in the user's app-data folder), so the DHC rate sheet
loaded once stays loaded between launches, the same way it does in a browser.
Built into DHC-Rate-Board.exe (Windows) and DHC Rate Board.app (Mac) by .github/workflows/desktop.yml.
"""
import os
import sys

import webview

URL = "https://zehra-jm.github.io/DHC_Dashboard/"


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, "DHC Rate Board")
    os.makedirs(path, exist_ok=True)
    return path


def main():
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # "Open on Booking.com" goes to the normal browser
    webview.create_window("DHC Rate Board", URL, width=1320, height=900, min_size=(380, 600))
    webview.start(private_mode=False, storage_path=data_dir())


if __name__ == "__main__":
    main()
