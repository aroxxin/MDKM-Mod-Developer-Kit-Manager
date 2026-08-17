# MDKM - Mod Developer Kit Manager

> A terminal-based Minecraft mod development project manager for **Forge, Fabric and NeoForge**.

MDKM is designed to make the repetitive parts of starting and maintaining a Minecraft mod project simpler: choose a loader, choose a Minecraft version, let MDKM find the appropriate development kit/template, and create the project without manually hunting through MDK downloads.

The project also includes a dedicated **Configure Projects** workflow for safely changing an existing mod's Mod ID across the project, with a preview, automatic backup and post-change verification.

---

## ✨ Features

### 🚀 Quick Create

Create a new Minecraft mod project from one terminal workflow:

- **Forge**
- **Fabric**
- **NeoForge**
- Minecraft version selection
- automatic lookup of the appropriate loader/template information
- project directory selection
- Java environment check
- download and extraction of the selected development kit

MDKM is intended to keep the process consistent across different mod loaders instead of forcing every project to be created manually from a different set of instructions.

### 🔧 Configure Projects

Existing projects can be detected and configured from the same application.

The current configuration workflow includes **Mod ID migration**. When a Mod ID is changed, MDKM does not simply edit one property and leave the rest of the project inconsistent.

The migration workflow:

1. detects the current loader and Mod ID;
2. validates the new Mod ID against loader-specific rules;
3. scans the project for references to the old ID;
4. shows a **MOD ID CHANGE** preview before applying anything;
5. creates a backup before modification;
6. updates matching text files;
7. renames matching files and directories;
8. verifies that relevant references to the old ID are gone;
9. displays exactly which files and paths were changed.

This is particularly useful for resources and metadata such as `assets/<modid>`, `data/<modid>`, loader metadata and source/configuration references.

### ⚡ Cache

Version information can be cached locally to reduce repeated network requests.

Cache settings include:

- enable/disable cache;
- configurable cache lifetime;
- manual cache clearing.

### 🔁 Automatic download retries

Network operations can be retried automatically when a request fails. The retry count is configurable from Settings.

### 📝 Logging

Optional application logs are stored under:

```text
~/.config/mdk-manager/logs/mdk-manager.log
```

Logging can be enabled or disabled from Settings.

### ⚙️ Configuration

MDKM stores its user configuration under:

```text
~/.config/mdk-manager/config.json
```

Current settings include the default project directory, cache behavior, cache lifetime, retry count and logging.

---

## 🖥️ Interface

MDKM intentionally uses a consistent terminal UI built with **Rich**.

The application uses panels, tables, clear status messages and a small, predictable menu structure instead of mixing multiple UI styles between loaders.

Main menu:

```text
╭────────────────────────────── MENU ─────────────────────────────────╮
│  [1] QUICK CREATE                                                   │
│  [2] CONFIGURE PROJECTS                                             │
│  [3] SETTINGS                                                       │
│  [4] ABOUT                                                          │
│  [0] EXIT                                                           │
╰────────────────────────────────────────────────────────────────────╯
```

---

## 🧩 Architecture

The project is split into a few focused layers:

```text
MDKM
├── core/
│   ├── app.py              # configuration, cache and logging
│   ├── fabric.py           # Fabric API/template handling
│   ├── forge.py            # Forge MDK handling
│   ├── neoforge.py         # NeoForge MDK handling
│   ├── java.py             # Java detection/compatibility
│   ├── project_config.py   # project detection + Mod ID migration
│   └── retry.py            # retry mechanism
│
├── loaders/
│   ├── base.py
│   ├── fabric.py
│   ├── forge.py
│   └── neoforge.py
│
├── ui/
│   ├── main_menu.py
│   ├── quick_create.py
│   ├── configure_projects.py
│   └── settings.py
│
├── main.py
└── requirements.txt
```

The goal is to keep loader-specific logic separate from the terminal interface so additional functionality can be added without turning the application into one large script.

---

## 📋 Requirements

- **Python 3.10+**
- Internet connection for retrieving current loader/MDK information
- A compatible Java installation for the selected Minecraft version when creating projects
- `pip` for installing Python dependencies

Python dependencies are intentionally minimal:

```text
rich>=14.0.0
```

---

## 🚀 Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/aroxxin/MDKM-Mod-Developer-Kit-Manager.git
cd MDKM-Mod-Developer-Kit-Manager
```

Create a virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start MDKM:

```bash
python3 main.py
```

---

## 🧪 Project status

MDKM is an **active development project**.

The core project-generation workflow for Forge, Fabric and NeoForge is already implemented, together with caching, retry handling, configuration, logging and project configuration tools.

Some areas are intentionally left for later development rather than being added prematurely. The project follows a staged development plan so each feature can be tested before the next one is introduced.

---

## 🗺️ Roadmap

The roadmap is intentionally incremental. Current and planned areas include:

- [x] Forge project creation
- [x] Fabric project creation
- [x] NeoForge project creation
- [x] Minecraft version selection
- [x] Cache
- [x] Error handling
- [x] Configurable retries
- [x] Application logging
- [x] Settings
- [x] Quick Create
- [x] Configure Projects
- [x] Mod ID migration preview
- [x] Automatic Mod ID migration backup
- [x] Changed-file reporting after Mod ID migration
- [ ] Further project metadata configuration
- [ ] Additional project-management features

---

## ⚠️ Important notes

### Mod ID changes

Changing a Mod ID is a project-wide operation. MDKM creates a backup before attempting the migration, but you should still keep your normal source-control history and project backups.

Generated build directories and other ignored/generated locations are intentionally excluded from the migration scan.

### Java

Minecraft versions can require different Java versions. MDKM checks the local Java environment before project creation, but automatic Java installation is not currently performed by the application.

---

## 🤝 Contributing

Issues, suggestions and pull requests are welcome.

If you find a problem:

1. check whether it is reproducible with the latest project version;
2. include the Minecraft version and mod loader;
3. include the relevant MDKM log when possible;
4. describe the expected behavior and what happened instead.
