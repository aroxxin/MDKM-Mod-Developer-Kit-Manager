from __future__ import annotations

import logging

from ui.main_menu import MainMenu


def main():
    try:
        MainMenu().run()
    except KeyboardInterrupt:
        print("\nZamykanie MDK Manager...")
    except Exception as exc:
        logging.getLogger("mdk-manager").exception("Nieobsłużony błąd programu")
        print(f"\nBŁĄD KRYTYCZNY: {exc}")
        print("Szczegóły zostały zapisane w ~/.config/mdk-manager/logs/mdk-manager.log")


if __name__ == "__main__":
    main()
