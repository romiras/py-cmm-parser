import typer
import json
import shutil
import os
from pathlib import Path
from rich.tree import Tree
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from parser import TreeSitterParser
from storage import SQLiteStorage
from resolver import DependencyResolver

app = typer.Typer(help="Root CLI for CMM tools.")
parser_app = typer.Typer(help="Tools for parsing source code into CMM entities.")
app.add_typer(parser_app, name="parser")
console = Console(width=120)


@parser_app.command(name="scan-file")
def scan_file(
    path: str,
    json_output: bool = typer.Option(
        False, "--json", help="Output the raw CMMEntity structure to stdout."
    ),
):
    """
    Scans a single file and outputs its CMM representation.
    """
    parser = TreeSitterParser()
    cmm_entity = parser.scan_file(path)

    if json_output:
        # Convert CMMEntity to a dictionary before serializing
        print(json.dumps(cmm_entity.__dict__, indent=2))
    else:
        tree = Tree(f"File: {path}")
        for entity in cmm_entity.entities:
            if entity["type"] == "class":
                class_tree = tree.add(
                    f"[bold magenta]class[/bold magenta] {entity['name']}"
                )
                if entity["docstring"]:
                    class_tree.add(f"[green]'''{entity['docstring']}'''[/green]")
                for method in entity["methods"]:
                    method_tree = class_tree.add(f"[blue]def[/blue] {method['name']}")
                    if method["docstring"]:
                        method_tree.add(f"[green]'''{method['docstring']}'''[/green]")
            elif entity["type"] == "function":
                function_tree = tree.add(f"[blue]def[/blue] {entity['name']}")
                if entity["docstring"]:
                    function_tree.add(f"[green]'''{entity['docstring']}'''[/green]")

        console.print(tree)


@parser_app.command(name="scan")
def scan_directory(
    directory: str,
    db_path: str = typer.Option(
        "./cmm.db", "--db-path", help="Path to SQLite database."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed output."
    ),
    enable_lsp: bool = typer.Option(
        False, "--enable-lsp", help="Enable LSP-based resolution (requires Pyright)."
    ),
):
    """
    Scans a directory recursively for Python files and stores results in SQLite.

    Two-Pass Strategy (when --enable-lsp is active):
    - Pass 1: Tree-sitter syntax scan (upsert entities)
    - Pass 2: LSP semantic resolution (verify relations)
    """
    parser = TreeSitterParser()
    storage = SQLiteStorage(db_path)

    # Find all Python files
    directory_path = Path(directory)
    if not directory_path.exists():
        console.print(f"[red]Error: Directory '{directory}' does not exist.[/red]")
        raise typer.Exit(1)

    # Exclude common directories
    exclude_dirs = {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".tox",
    }

    python_files = []
    for py_file in directory_path.rglob("*.py"):
        # Check if any parent directory is in exclude list
        if not any(part in exclude_dirs for part in py_file.parts):
            python_files.append(py_file)

    if not python_files:
        console.print(f"[yellow]No Python files found in '{directory}'.[/yellow]")
        return

    console.print(f"[cyan]Found {len(python_files)} Python file(s) to scan.[/cyan]")

    # ========== PASS 1: Syntax Scan ==========
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Pass 1: Scanning syntax...", total=len(python_files))

        scanned = 0
        errors = 0

        for py_file in python_files:
            file_path = str(py_file.absolute())

            try:
                if verbose:
                    progress.console.print(
                        f"  Parsing: {py_file.relative_to(directory_path)}"
                    )

                cmm_entity = parser.scan_file(file_path)
                storage.upsert_file(file_path, cmm_entity)
                scanned += 1

            except Exception as e:
                errors += 1
                if verbose:
                    progress.console.print(
                        f"  [red]Error parsing {py_file.name}: {e}[/red]"
                    )

            progress.advance(task)

    console.print(f"\n[green]✓ Pass 1 complete: {scanned} file(s) scanned.[/green]")
    if errors > 0:
        console.print(f"[yellow]⚠ {errors} file(s) had errors.[/yellow]")

    # ========== PASS 2: LSP Resolution ==========
    if enable_lsp:
        from lsp_client import LSPClient
        from symbol_mapper import SymbolMapper
        import time

        console.print("\n[cyan]Starting Pass 2: LSP semantic resolution...[/cyan]")

        workspace_root = str(directory_path.absolute())
        lsp = LSPClient(workspace_root)

        if not lsp.is_available():
            console.print(
                "[yellow]Pyright not available. Skipping LSP resolution.[/yellow]"
            )
            console.print(f"[cyan]Database: {db_path}[/cyan]")
            return

        if not lsp.start():
            console.print(
                "[yellow]Failed to start LSP server. Skipping resolution.[/yellow]"
            )
            console.print(f"[cyan]Database: {db_path}[/cyan]")
            return

        # Allow Pyright to index workspace
        console.print("[dim]Waiting for Pyright to index workspace (3s)...[/dim]")
        time.sleep(3)

        symbol_mapper = SymbolMapper(storage)
        stats = {"resolved": 0, "failed": 0, "external": 0}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Pass 2: Resolving calls...", total=len(python_files)
            )

            for py_file in python_files:
                file_path = str(py_file.absolute())
                file_uri = f"file://{file_path}"

                try:
                    # Open document in LSP
                    with open(file_path, "r") as f:
                        lsp.open_document(file_uri, f.read())

                    # Extract call sites
                    call_sites = parser.extract_call_sites(file_path)

                    for site in call_sites:
                        # 1. Who is calling?
                        from_id = symbol_mapper.find_enclosing_entity(
                            file_path, site.line
                        )
                        if not from_id:
                            continue  # Call outside any entity (module-level)

                        # 2. What is defined there? (LSP)
                        def_loc = lsp.get_definition(
                            site.file_uri, site.line, site.character
                        )
                        if not def_loc:
                            stats["failed"] += 1
                            if verbose:
                                progress.console.print(
                                    f"  [yellow]LSP failed: {site.name} at {site.line}[/yellow]"
                                )
                            continue

                        # 3. What UUID is that?
                        to_id = symbol_mapper.find_by_location(def_loc)
                        if not to_id:
                            stats["external"] += 1  # Definition outside scanned files
                            continue

                        # 4. Record verified relation
                        storage.save_verified_relation(
                            from_id, to_id, "calls", is_verified=True
                        )
                        stats["resolved"] += 1

                except Exception as e:
                    if verbose:
                        progress.console.print(
                            f"  [red]Error resolving {py_file.name}: {e}[/red]"
                        )

                progress.advance(task)

        lsp.shutdown()

        console.print("\n[green]✓ Pass 2 complete[/green]")
        console.print("[cyan]LSP Resolution Statistics:[/cyan]")
        console.print(f"  • {stats['resolved']} relations verified")
        console.print(f"  • {stats['failed']} lookups failed")
        console.print(f"  • {stats['external']} external references")

    console.print(f"[cyan]Database: {db_path}[/cyan]")


@parser_app.command(name="resolve")
def resolve_dependencies(
    file_path: str,
    db_path: str = typer.Option(
        "./cmm.db", "--db-path", help="Path to SQLite database."
    ),
    entity: str = typer.Option(
        None, "--entity", help="Filter by specific entity name."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """
    Resolve cross-file dependencies for a given file.
    """
    resolver = DependencyResolver(db_path)

    # Check if file exists in database
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        console.print(f"[red]Error: File '{file_path}' does not exist.[/red]")
        raise typer.Exit(1)

    # Get absolute path
    abs_file_path = str(file_path_obj.absolute())

    # Resolve dependencies
    dependencies = resolver.resolve_dependencies(abs_file_path)

    if not dependencies:
        console.print(
            f"[yellow]No external dependencies found for '{file_path}'.[/yellow]"
        )
        return

    # Filter by entity if specified
    if entity:
        if entity in dependencies:
            dependencies = {entity: dependencies[entity]}
        else:
            console.print(
                f"[yellow]Entity '{entity}' not found in '{file_path}'.[/yellow]"
            )
            return

    if json_output:
        # Output as JSON
        graph = resolver.get_dependency_graph(abs_file_path)
        print(json.dumps(graph, indent=2))
    else:
        # Display as rich table
        console.print(f"\n[cyan]Dependencies for: {file_path}[/cyan]\n")

        for entity_name, resolved_deps in dependencies.items():
            table = Table(title=f"Entity: {entity_name}", show_header=True)
            table.add_column("Dependency", style="cyan")
            table.add_column("Rel Type", style="bold yellow")  # New column
            table.add_column("Type", style="magenta")
            table.add_column("CMM Type", style="blue")
            table.add_column("Visibility", style="green")
            table.add_column("File", style="yellow")

            for dep in resolved_deps:
                table.add_row(
                    dep.entity_name,
                    dep.rel_type,
                    dep.entity_type,
                    dep.cmm_type,
                    dep.visibility,
                    dep.file_path,
                )

            console.print(table)
            console.print()


@parser_app.command(name="migrate")
def migrate_database(
    from_version: str = typer.Option("v0.2", "--from", help="Current schema version."),
    to_version: str = typer.Option("v0.3", "--to", help="Target schema version."),
    db_path: str = typer.Option(
        "./cmm.db", "--db-path", help="Path to SQLite database."
    ),
    scan_path: str = typer.Option(
        ".", "--scan-path", help="Path to re-scan after migration."
    ),
):
    """
    Migrates the database to a new schema version.
    Current implementation: Backs up DB and performs a full re-scan.
    """
    console.print(
        f"[bold]Migrating database from {from_version} to {to_version}...[/bold]"
    )

    db_file = Path(db_path)
    if not db_file.exists():
        console.print(
            f"[yellow]Database file {db_path} does not exist. Creating new.[/yellow]"
        )
    else:
        # 1. Backup
        backup_path = f"{db_path}.{from_version}.backup"
        console.print(f"Creating backup at {backup_path}...")
        try:
            shutil.copy2(db_path, backup_path)
            console.print("[green]Backup created successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to create backup: {e}[/red]")
            raise typer.Exit(1)

        # 2. Delete old DB (to allow fresh creation of v0.3 schema)
        console.print("Removing old database...")
        os.remove(db_path)

    # 3. Re-scan
    console.print(f"Initializing {to_version} schema and re-scanning {scan_path}...")
    scan_directory(scan_path, db_path=db_path, verbose=False)

    console.print("[bold green]Migration complete![/bold green]")


@parser_app.command(name="migrate-lsp")
def migrate_to_lsp(
    db_path: str = typer.Option(
        "./cmm.db", "--db-path", help="Path to SQLite database."
    ),
):
    """
    Migrates v0.3 database to v0.3.1 with LSP-ready schema enhancements.
    Adds columns: symbol_hash, type_hint, is_verified.
    """
    console.print("[bold]Migrating database to v0.3.1 (LSP-ready)...[/bold]")

    db_file = Path(db_path)
    if not db_file.exists():
        console.print(f"[red]Error: Database file {db_path} does not exist.[/red]")
        raise typer.Exit(1)

    # 1. Backup
    backup_path = f"{db_path}.v0.3.backup"
    console.print(f"Creating backup at {backup_path}...")
    try:
        shutil.copy2(db_path, backup_path)
        console.print("[green]Backup created successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to create backup: {e}[/red]")
        raise typer.Exit(1)

    # 2. Apply migration SQL
    migration_sql_path = Path(__file__).parent / "migration_v0.3.1.sql"
    if not migration_sql_path.exists():
        console.print(
            f"[red]Error: Migration script not found at {migration_sql_path}[/red]"
        )
        raise typer.Exit(1)

    console.print("Applying schema changes...")
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        with open(migration_sql_path, "r") as f:
            migration_sql = f.read()

        # Execute migration
        cursor.executescript(migration_sql)
        conn.commit()
        conn.close()

        console.print("[green]✓ Schema updated to v0.3.1[/green]")
        console.print("\nNew columns added:")
        console.print("  • entities_v3.symbol_hash (for LSP correlation)")
        console.print("  • metadata.type_hint (for type information)")
        console.print("  • relations.is_verified (for LSP validation)")
        console.print("\n[bold green]Migration complete![/bold green]")
        console.print(
            "[yellow]Note: Re-scan with --enable-lsp to populate new columns.[/yellow]"
        )

    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        console.print("[yellow]Restoring from backup...[/yellow]")
        shutil.copy2(backup_path, db_path)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
