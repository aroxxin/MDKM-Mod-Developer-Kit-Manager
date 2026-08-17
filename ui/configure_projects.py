from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.app import load_config
from core.project_config import ProjectConfigError, apply_mod_id_change, detect_project, scan_changes, validate_mod_id


class ConfigureProjects:
    def __init__(self, console: Console):
        self.console = console
        self.config = load_config()
        self.project_root = Path(str(self.config.get("project_path", Path.home() / "MinecraftMods"))).expanduser()

    def run(self):
        while True:
            self.console.clear()
            projects = self._projects()
            table = Table(show_header=False, box=None, padding=(0, 2))
            if projects:
                for index, project in enumerate(projects, 1):
                    try:
                        info = detect_project(project)
                        label = f"{project.name}  [dim]({info.loader}, {info.mod_id})[/dim]"
                    except ProjectConfigError:
                        label = f"{project.name}  [dim](nierozpoznany projekt)[/dim]"
                    table.add_row(f"[bold cyan][{index}][/bold cyan]", label)
            else:
                table.add_row("", "[dim]Brak projektów w domyślnej lokalizacji.[/dim]")
            table.add_row("[bold cyan][P][/bold cyan]", "Podaj ścieżkę projektu ręcznie")
            table.add_row("[bold red][B][/bold red]", "Powrót")
            self.console.print(Panel(table, title="[bold cyan]CONFIGURE PROJECTS[/bold cyan]", border_style="cyan"))
            self.console.print(f"[dim]Katalog projektów: {self.project_root}[/dim]")
            choice = self.console.input("\nWybierz projekt / [P] ścieżka / [B] powrót: ").strip().lower()
            if choice == "b":
                return
            if choice == "p":
                raw = self.console.input("Ścieżka projektu: ").strip()
                if raw:
                    self.configure(Path(raw).expanduser())
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(projects):
                self.configure(projects[int(choice) - 1])

    def _projects(self) -> list[Path]:
        if not self.project_root.is_dir():
            return []
        return sorted((p for p in self.project_root.iterdir() if p.is_dir()), key=lambda p: p.name.lower())

    def configure(self, root: Path):
        try:
            info = detect_project(root)
        except ProjectConfigError as exc:
            self.console.print(Panel(f"[red]{exc}[/red]", title="BŁĄD", border_style="red"))
            self.console.input("Naciśnij ENTER...")
            return
        while True:
            self.console.clear()
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_row("Projekt", str(info.path))
            table.add_row("Loader", info.loader)
            table.add_row("Mod ID", f"[bold cyan]{info.mod_id}[/bold cyan]")
            self.console.print(Panel(table, title="PROJECT INFORMATION", border_style="cyan"))
            self.console.print("\n[1] Zmień Mod ID")
            self.console.print("[B] Powrót")
            choice = self.console.input("\nWybierz: ").strip().lower()
            if choice == "b":
                return
            if choice == "1" and self.change_mod_id(info.path, info.mod_id, info.loader):
                info = detect_project(info.path)

    def change_mod_id(self, root: Path, old_id: str, loader: str) -> bool:
        new_id = self.console.input(f"\nNowy Mod ID (obecnie {old_id}): ").strip()
        valid, message = validate_mod_id(loader, new_id)
        if not valid:
            self.console.print(f"[red]✗ {message}[/red]")
            self.console.input("Naciśnij ENTER...")
            return False
        if new_id == old_id:
            self.console.print("[yellow]Nowy Mod ID jest taki sam jak obecny.[/yellow]")
            self.console.input("Naciśnij ENTER...")
            return False
        try:
            changes = scan_changes(root, old_id, new_id)
        except OSError as exc:
            self.console.print(f"[red]Nie można przeskanować projektu: {exc}[/red]")
            self.console.input("Naciśnij ENTER...")
            return False
        self.console.clear()
        self.console.print(Panel(
            f"[bold]Stare Mod ID:[/bold] {old_id}\n[bold]Nowe Mod ID:[/bold] {new_id}\n\n"
            "Program zmieni wystąpienia ID w plikach tekstowych oraz nazwach plików/katalogów. "
            "Katalogi build/.gradle/.git i pliki binarne są pomijane.",
            title="MOD ID CHANGE", border_style="cyan",
        ))
        if changes:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Typ")
            table.add_column("Element")
            for change in changes[:80]:
                table.add_row("Treść" if change.kind == "content" else "Nazwa", str(change.path))
            self.console.print(table)
            if len(changes) > 80:
                self.console.print(f"[dim]... oraz {len(changes) - 80} kolejnych zmian.[/dim]")
        else:
            self.console.print("[yellow]Nie znaleziono wystąpień starego ID.[/yellow]")
            self.console.input("Naciśnij ENTER...")
            return False
        self.console.print("\n[bold yellow]Przed zmianą zostanie utworzony backup projektu.[/bold yellow]")
        if self.console.input("Zastosować zmiany? [y/N]: ").strip().lower() != "y":
            self.console.print("[dim]Anulowano.[/dim]")
            self.console.input("Naciśnij ENTER...")
            return False
        try:
            backup, applied, changed_files = apply_mod_id_change(root, old_id, new_id)
        except ProjectConfigError as exc:
            self.console.print(Panel(f"[red]{exc}[/red]", title="MOD ID CHANGE — BŁĄD", border_style="red"))
            self.console.input("Naciśnij ENTER...")
            return False
        self.console.print(Panel(
            f"[green]✓ Mod ID zmieniony poprawnie.[/green]\n\nStare ID: {old_id}\nNowe ID:  {new_id}\n"
            f"Zmiany:   {len(applied)}\nPliki tekstowe: {changed_files}\n\nBackup:\n{backup}\n\n"
            "Pozostałe odniesienia do starego ID: 0",
            title="MOD ID CHANGE — GOTOWE", border_style="green",
        ))
        content_changes = sorted({str(change.path) for change in applied if change.kind == "content"}, key=str.lower)
        path_changes = sorted({str(change.path) for change in applied if change.kind == "path"}, key=str.lower)
        if content_changes:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Plik")
            for index, path in enumerate(content_changes, 1):
                table.add_row(str(index), path)
            self.console.print(Panel(table, title="ZMIENIONE PLIKI", border_style="cyan"))
        if path_changes:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("#", justify="right", style="dim")
            table.add_column("Zmieniona ścieżka")
            for index, path in enumerate(path_changes, 1):
                table.add_row(str(index), path)
            self.console.print(Panel(table, title="ZMIENIONE NAZWY PLIKÓW / KATALOGÓW", border_style="cyan"))
        self.console.input("Naciśnij ENTER...")
        return True
