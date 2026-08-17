from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.app import clear_cache, configure_logging, load_config, save_config


class Settings:
    def __init__(self, console: Console):
        self.console = console
        self.config = load_config()

    def run(self):
        while True:
            self.render()
            choice = self.console.input("\n[bold]Wybierz opcję (1-6), [B] powrót:[/bold] ").strip().lower()
            if choice == "b":
                save_config(self.config)
                configure_logging(bool(self.config.get("log_enabled", True)))
                return
            if choice == "1":
                self.config["cache_enabled"] = not bool(self.config.get("cache_enabled", True))
            elif choice == "2":
                value = self.console.input("Czas cache (godziny): ").strip()
                try:
                    self.config["cache_ttl_hours"] = max(1, int(value))
                except ValueError:
                    self.console.print("[red]Podaj liczbę całkowitą.[/red]")
                    self.console.input("Naciśnij ENTER...")
            elif choice == "3":
                value = self.console.input("Liczba prób pobierania (1-10): ").strip()
                try:
                    self.config["download_retries"] = min(10, max(1, int(value)))
                except ValueError:
                    self.console.print("[red]Podaj liczbę całkowitą.[/red]")
                    self.console.input("Naciśnij ENTER...")
            elif choice == "4":
                self.config["log_enabled"] = not bool(self.config.get("log_enabled", True))
                save_config(self.config)
                configure_logging(bool(self.config["log_enabled"]))
            elif choice == "5":
                path = self.console.input("Domyślna lokalizacja projektów: ").strip()
                if path:
                    self.config["project_path"] = path
            elif choice == "6":
                count = clear_cache()
                self.console.print(f"[green]Usunięto {count} elementów cache.[/green]")
                self.console.input("Naciśnij ENTER...")
            else:
                self.console.print("[red]Nieprawidłowa opcja.[/red]")

    def render(self):
        self.console.clear()
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]1. Cache[/bold]", "[green]WŁĄCZONY[/green]" if self.config.get("cache_enabled") else "[dim]WYŁĄCZONY[/dim]")
        table.add_row("[bold]2. Cache TTL[/bold]", f"{self.config.get('cache_ttl_hours', 12)} h")
        table.add_row("[bold]3. Ponawianie pobierania[/bold]", f"{self.config.get('download_retries', 3)} prób")
        table.add_row("[bold]4. Logi[/bold]", "[green]WŁĄCZONE[/green]" if self.config.get("log_enabled") else "[dim]WYŁĄCZONE[/dim]")
        table.add_row("[bold]5. Lokalizacja projektów[/bold]", str(self.config.get("project_path")))
        table.add_row("[bold]6. Wyczyść cache[/bold]", "Usuń zapisane dane wersji")
        self.console.print(Panel(table, title="[bold cyan]SETTINGS[/bold cyan]", border_style="cyan"))
        self.console.print("[dim]Zmiana pola: 1-6 • B: powrót[/dim]")
