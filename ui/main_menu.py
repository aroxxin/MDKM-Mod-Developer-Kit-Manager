from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.app import configure_logging, load_config
from ui.configure_projects import ConfigureProjects
from ui.quick_create import QuickCreate
from ui.settings import Settings


class MainMenu:
    def __init__(self):
        self.console = Console()
        self.config = load_config()
        self.logger = configure_logging(bool(self.config.get("log_enabled", True)))

    def header(self):
        self.console.clear()
        self.console.print(Panel.fit(
            "[bold cyan]MDK MANAGER[/bold cyan]\n[dim]Minecraft Mod Development Manager Kit[/dim]",
            border_style="cyan",
            padding=(1, 5),
        ))

    def run(self):
        while True:
            self.header()
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_row("[bold cyan][1][/bold cyan]", "[bold]QUICK CREATE[/bold]", "Szybkie utworzenie projektu moda")
            table.add_row("[bold cyan][2][/bold cyan]", "[bold]CONFIGURE PROJECTS[/bold]", "Konfiguracja istniejących projektów")
            table.add_row("[bold cyan][3][/bold cyan]", "[bold]SETTINGS[/bold]", "Ustawienia programu")
            table.add_row("[bold cyan][4][/bold cyan]", "[bold]ABOUT[/bold]", "Informacje o programie")
            table.add_row("[bold red][0][/bold red]", "[bold]EXIT[/bold]", "Zakończ program")
            self.console.print(Panel(table, title="MENU", border_style="cyan"))
            choice = self.console.input("\n[bold]Wybierz opcję:[/bold] ").strip().lower()
            if choice == "1":
                self.logger.info("Otworzono Quick Create")
                QuickCreate(self.console).run()
            elif choice == "2":
                self.logger.info("Otworzono Configure Projects")
                ConfigureProjects(self.console).run()
            elif choice == "3":
                Settings(self.console).run()
            elif choice == "4":
                self.about()
            elif choice == "0":
                self.console.print("\n[dim]Zamykanie MDK Manager...[/dim]")
                break
            else:
                self.console.print("[red]Nieprawidłowa opcja.[/red]")
                self.console.input("Naciśnij ENTER...")

    def about(self):
        self.header()
        self.console.print(Panel(
            "[bold]MDK Manager[/bold]\n\n"
            "Terminalowe narzędzie do przygotowywania środowiska modderskiego Minecraft.\n\n"
            "Obsługiwane loadery: Forge, Fabric, NeoForge\n"
            "Etap projektu: Forge / Fabric / NeoForge / Configure Projects",
            title="ABOUT",
            border_style="cyan",
        ))
        self.console.input("\nNaciśnij ENTER, aby wrócić...")
