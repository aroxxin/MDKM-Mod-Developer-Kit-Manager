from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.table import Table

from core.app import load_config
from core.fabric import FabricError, create_project as create_fabric_project, get_supported_minecraft_versions as get_fabric_minecraft_versions, get_template as get_fabric_template
from core.forge import ForgeError, download_file, extract_mdk, get_latest_release, get_supported_minecraft_versions, verify_release
from core.java import detect_java, java_compatible, required_java_for_minecraft
from core.neoforge import NeoForgeError, create_project as create_neoforge_project, get_supported_minecraft_versions as get_neoforge_minecraft_versions, get_template as get_neoforge_template
from core.retry import with_retry
from loaders.base import LOADERS


class QuickCreate:
    def __init__(self, console: Console):
        self.console = console
        self.mod_name = ""
        self.loader_index = 0
        self.minecraft_version = "latest"
        self.minecraft_display = "Najnowsza wersja"
        self.config = load_config()
        self.project_path = str(self.config.get("project_path", Path.home() / "MinecraftMods"))
        self.auto_java = bool(self.config.get("auto_java", False))
        self._forge_versions: list[str] | None = None
        self._fabric_template = None
        self._neoforge_template = None

    def run(self):
        while True:
            self.render()
            choice = self.console.input("\n[bold]Wybierz pole (1-6), [C] sprawdź Java, [ENTER] utwórz, [B] powrót:[/bold] ").strip().lower()
            if choice == "b":
                return
            if choice == "":
                if self.validate():
                    self.create_project()
                    return
                continue
            if choice == "1":
                self.mod_name = self.console.input("Nazwa moda: ").strip()
            elif choice == "2":
                self.select_loader()
            elif choice == "3":
                self.select_minecraft()
            elif choice == "4":
                self.project_path = self.console.input("Ścieżka projektu: ").strip() or self.project_path
            elif choice == "5":
                self.auto_java = not self.auto_java
            elif choice == "6" or choice == "c":
                self.check_java()
            else:
                self.console.print("[red]Nieprawidłowy wybór.[/red]")

    def render(self):
        self.console.clear()
        java = detect_java()
        required = self.required_java_display()
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]1. Nazwa moda[/bold]", self.mod_name or "[dim]nie ustawiono[/dim]")
        table.add_row("[bold]2. Mod Loader[/bold]", LOADERS[self.loader_index].display_name)
        table.add_row("[bold]3. Minecraft[/bold]", self.minecraft_display)
        table.add_row("[bold]4. Lokalizacja[/bold]", self.project_path)
        table.add_row("[bold]5. Auto-install Java[/bold]", "[green][x][/green] Tak" if self.auto_java else "[dim][ ] Nie[/dim]")
        table.add_row("[bold]6. Sprawdź Java[/bold]", "Ponownie wykryj środowisko")
        java_table = Table(show_header=False, box=None, padding=(0, 1))
        java_table.add_row("Wykryta wersja:", f"Java {java.version}" if java.installed and java.version else "[red]BRAK[/red]")
        java_table.add_row("Wersja dokładna:", java.raw_version or "-")
        java_table.add_row("Wymagana:", required)
        java_table.add_row("Status:", self.java_status(java, self.required_java()))
        java_table.add_row("Automatyczna instalacja:", "[green]WŁĄCZONA[/green]" if self.auto_java else "[dim]WYŁĄCZONA[/dim]")
        self.console.print(Panel(table, title="[bold cyan]QUICK CREATE[/bold cyan]", border_style="cyan"))
        self.console.print(Panel(java_table, title="[bold]JAVA[/bold]", border_style="yellow"))
        self.console.print("[dim]Zmiana pola: 1-6 • C: sprawdź Java • ENTER: utwórz • B: powrót[/dim]")

    def required_java(self) -> int:
        if self.minecraft_version == "latest":
            return 25
        return required_java_for_minecraft(self.minecraft_version)

    def required_java_display(self) -> str:
        if self.loader_index != 0:
            return "Do ustalenia po implementacji loadera"
        return f"Java {self.required_java()}"

    @staticmethod
    def java_status(java, required: int):
        if not java.installed:
            return f"[red]✗ Java nie została znaleziona (wymagana Java {required})[/red]"
        if java.error:
            return f"[yellow]⚠ {java.error}[/yellow]"
        if not java_compatible(java, required):
            return f"[red]✗ Wymagana Java {required}, wykryto Java {java.version}[/red]"
        return "[green]✓ Java jest kompatybilna[/green]"

    def select_loader(self):
        self.console.print("\n[bold]Wybierz Mod Loader:[/bold]")
        for i, loader in enumerate(LOADERS, 1):
            marker = "<" if i - 1 == self.loader_index else ""
            self.console.print(f"  [{i}] {loader.display_name} {marker}")
        value = self.console.input("> ").strip()
        if value.isdigit() and 1 <= int(value) <= len(LOADERS):
            self.loader_index = int(value) - 1

    def select_minecraft(self):
        self.console.clear()
        loader_name = LOADERS[self.loader_index].display_name.upper()
        self.console.print(Panel(f"[bold cyan]{loader_name} — WERSJE MINECRAFT[/bold cyan]", border_style="cyan"))
        try:
            if self.loader_index == 0:
                versions = get_supported_minecraft_versions()
            elif self.loader_index == 1:
                versions = get_fabric_minecraft_versions()
            else:
                versions = get_neoforge_minecraft_versions()
        except (ForgeError, FabricError, NeoForgeError) as exc:
            self.console.print(f"[red]{exc}[/red]")
            self.console.input("Naciśnij ENTER...")
            return
        self.console.print("[bold][1][/bold] Najnowsza wersja")
        for index, version in enumerate(versions[:30], 2):
            self.console.print(f"[bold][{index}][/bold] {version}")
        self.console.print("[dim]Wyświetlono maksymalnie 30 najnowszych wersji.[/dim]")
        value = self.console.input("\nWybierz wersję: ").strip()
        if value == "1":
            self.minecraft_version = "latest"
            self.minecraft_display = "Najnowsza wersja"
        elif value.isdigit() and 2 <= int(value) <= min(len(versions) + 1, 31):
            selected = versions[int(value) - 2]
            self.minecraft_version = selected
            self.minecraft_display = selected

    def check_java(self):
        java = detect_java()
        required = self.required_java()
        self.console.print()
        self.console.print(Panel(
            f"Wykryta wersja: {java.raw_version or 'BRAK'}\n"
            f"Java executable: {java.executable or 'BRAK'}\n"
            f"Wymagana: Java {required}\n"
            f"Status: {self.java_status(java, required)}\n"
            f"Auto-install: {'WŁĄCZONA' if self.auto_java else 'WYŁĄCZONA'}",
            title="JAVA CHECK", border_style="yellow",
        ))
        self.console.input("Naciśnij ENTER...")

    def validate(self):
        valid = True
        if not self.mod_name:
            self.console.print("[red]Podaj nazwę moda.[/red]")
            valid = False
        if not self.project_path:
            self.console.print("[red]Podaj lokalizację projektu.[/red]")
            valid = False
        return valid

    def create_project(self):
        if self.loader_index == 1:
            self.create_fabric_project()
            return
        if self.loader_index == 2:
            self.create_neoforge_project()
            return
        minecraft = self.minecraft_version
        try:
            self.console.clear()
            self.console.print(Panel("[bold cyan]FORGE — ANALIZA MDK[/bold cyan]", border_style="cyan"))
            self.console.print("Pobieranie informacji o wersjach Forge...")
            release = get_latest_release(minecraft)
            minecraft = release.minecraft
            self.minecraft_version = minecraft
            self.minecraft_display = minecraft
            required = required_java_for_minecraft(minecraft)
            java = detect_java()
            self.console.print(f"\nMinecraft: [bold]{minecraft}[/bold]")
            self.console.print(f"Forge:     [bold]{release.forge}[/bold]")
            self.console.print(f"Java:      {'[green]OK[/green]' if java_compatible(java, required) else '[red]NIEZGODNA[/red]'} (wymagana Java {required})")
            if not java_compatible(java, required):
                if self.auto_java:
                    self.console.print("\n[yellow]Automatyczna instalacja Java jest zaznaczona, ale instalator Javy zostanie dodany w kolejnym etapie bezpieczeństwa systemowego.[/yellow]")
                self.console.print("[red]Nie można bezpiecznie utworzyć projektu bez wymaganej wersji Java.[/red]")
                self.console.input("Naciśnij ENTER...")
                return
            base = Path(self.project_path).expanduser()
            target = base / self.mod_name
            if target.exists() and any(target.iterdir()):
                self.console.print(f"\n[red]Katalog już istnieje i nie jest pusty:[/red] {target}")
                self.console.input("Naciśnij ENTER...")
                return
            target.mkdir(parents=True, exist_ok=True)
            archive = target / f"forge-{release.minecraft}-{release.forge}-mdk.zip"
            self.download_release(release, archive)
            self.console.print("\nWeryfikacja MDK...")
            ok, message = verify_release(archive, release)
            if not ok:
                self.console.print(f"[red]✗ {message}[/red]")
                archive.unlink(missing_ok=True)
                self.console.input("Naciśnij ENTER...")
                return
            self.console.print(f"[green]✓ {message}[/green]")
            self.console.print("\nRozpakowywanie MDK...")
            extract_mdk(archive, target)
            archive.unlink(missing_ok=True)
            self.console.print(Panel(
                "[bold green]Projekt Forge został utworzony![/bold green]\n\n"
                f"Nazwa:       {self.mod_name}\nMinecraft:   {release.minecraft}\nForge:        {release.forge}\nLokalizacja: {target}\n\n"
                "[dim]MDK ZIP został usunięty po poprawnym rozpakowaniu.[/dim]",
                title="QUICK CREATE", border_style="green",
            ))
            self.console.input("\nNaciśnij ENTER, aby wrócić...")
        except (ForgeError, OSError) as exc:
            self.console.print(f"\n[red]BŁĄD:[/red] {exc}")
            self.console.input("Naciśnij ENTER...")

    def create_fabric_project(self):
        minecraft = self.minecraft_version
        try:
            self.console.clear()
            self.console.print(Panel("[bold cyan]FABRIC — ANALIZA TEMPLATE[/bold cyan]", border_style="cyan"))
            if minecraft == "latest":
                minecraft = get_fabric_minecraft_versions()[0]
                self.minecraft_version = minecraft
                self.minecraft_display = minecraft
            self.console.print(f"Pobieranie informacji o Fabric dla Minecraft [bold]{minecraft}[/bold]...")
            template = get_fabric_template(minecraft)
            self._fabric_template = template
            java = detect_java()
            required = required_java_for_minecraft(minecraft)
            self.console.print(f"\nMinecraft:   [bold]{template.minecraft}[/bold]")
            self.console.print(f"Fabric Loader: [bold]{template.loader}[/bold]")
            self.console.print(f"Loom:          [bold]{template.loom}[/bold]")
            self.console.print(f"Template:      [bold]{template.branch}[/bold]")
            self.console.print(f"Java:          {'[green]OK[/green]' if java_compatible(java, required) else '[red]NIEZGODNA[/red]'} (wymagana Java {required})")
            if not java_compatible(java, required):
                self.console.print("[red]Nie można bezpiecznie utworzyć projektu bez wymaganej wersji Java.[/red]")
                self.console.input("Naciśnij ENTER...")
                return
            base = Path(self.project_path).expanduser()
            target = base / self.mod_name
            create_fabric_project(template, target, self.mod_name)
            self.console.print(Panel(
                "[bold green]Projekt Fabric został utworzony![/bold green]\n\n"
                f"Nazwa:          {self.mod_name}\nMinecraft:      {template.minecraft}\nFabric Loader:  {template.loader}\n"
                f"Loom:            {template.loom}\nTemplate:        {template.branch}\nLokalizacja:     {target}",
                title="QUICK CREATE", border_style="green",
            ))
            self.console.input("\nNaciśnij ENTER, aby wrócić...")
        except (FabricError, OSError) as exc:
            self.console.print(f"\n[red]BŁĄD:[/red] {exc}")
            self.console.input("Naciśnij ENTER...")

    def create_neoforge_project(self):
        minecraft = self.minecraft_version
        try:
            self.console.clear()
            self.console.print(Panel("[bold cyan]NEOFORGE — ANALIZA MDK[/bold cyan]", border_style="cyan"))
            if minecraft == "latest":
                minecraft = get_neoforge_minecraft_versions()[0]
                self.minecraft_version = minecraft
                self.minecraft_display = minecraft
            self.console.print(f"Pobieranie informacji o NeoForge dla Minecraft [bold]{minecraft}[/bold]...")
            template = get_neoforge_template(minecraft)
            self._neoforge_template = template
            java = detect_java()
            required = required_java_for_minecraft(minecraft)
            self.console.print(f"\nMinecraft:    [bold]{template.minecraft}[/bold]")
            self.console.print(f"NeoForge:     [bold]{template.neoforge}[/bold]")
            self.console.print(f"Loader range: [bold]{template.loader_range}[/bold]")
            self.console.print(f"MDK:          [bold]{template.repository}[/bold]")
            self.console.print(f"Java:         {'[green]OK[/green]' if java_compatible(java, required) else '[red]NIEZGODNA[/red]'} (wymagana Java {required})")
            if not java_compatible(java, required):
                self.console.print("[red]Nie można bezpiecznie utworzyć projektu bez wymaganej wersji Java.[/red]")
                self.console.input("Naciśnij ENTER...")
                return
            base = Path(self.project_path).expanduser()
            target = base / self.mod_name
            create_neoforge_project(template, target, self.mod_name)
            self.console.print(Panel(
                "[bold green]Projekt NeoForge został utworzony![/bold green]\n\n"
                f"Nazwa:          {self.mod_name}\nMinecraft:      {template.minecraft}\nNeoForge:       {template.neoforge}\n"
                f"MDK:             {template.repository}\nLokalizacja:     {target}",
                title="QUICK CREATE", border_style="green",
            ))
            self.console.input("\nNaciśnij ENTER, aby wrócić...")
        except (NeoForgeError, OSError) as exc:
            self.console.print(f"\n[red]BŁĄD:[/red] {exc}")
            self.console.input("Naciśnij ENTER...")

    def download_release(self, release, archive: Path):
        progress = Progress(TextColumn("[bold]Pobieranie MDK[/bold]"), BarColumn(), "[progress.percentage]{task.percentage:>3.0f}%", DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn())
        with progress:
            task = progress.add_task("MDK", total=None)
            def update(downloaded: int, total: int, speed: float):
                if total > 0:
                    progress.update(task, total=total, completed=downloaded)
                else:
                    progress.update(task, total=None, completed=downloaded)
            retries = int(self.config.get("download_retries", 3))
            with_retry(lambda: download_file(release.mdk_url, archive, update), attempts=retries,
                       on_retry=lambda attempt, exc: self.console.print(f"[yellow]Ponowienie pobierania {attempt}/{retries - 1}...[/yellow]"))
            size = archive.stat().st_size
            progress.update(task, total=size, completed=size)
