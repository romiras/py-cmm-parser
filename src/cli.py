import typer
import json
from pathlib import Path
from rich.tree import Tree
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from parser import TreeSitterParser
from domain import CMMEntity
from storage import SQLiteStorage

app = typer.Typer(help="Root CLI for CMM tools.")
parser_app = typer.Typer(help="Tools for parsing source code into CMM entities.")
app.add_typer(parser_app, name="parser")
console = Console()

@parser_app.command(name="scan-file")
def scan_file(
    path: str,
    json_output: bool = typer.Option(False, "--json", help="Output the raw CMMEntity structure to stdout."),
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
                class_tree = tree.add(f"[bold magenta]class[/bold magenta] {entity['name']}")
                if entity['docstring']:
                    class_tree.add(f"[green]'''{entity['docstring']}'''[/green]")
                for method in entity["methods"]:
                    method_tree = class_tree.add(f"[blue]def[/blue] {method['name']}")
                    if method['docstring']:
                        method_tree.add(f"[green]'''{method['docstring']}'''[/green]")
            elif entity["type"] == "function":
                function_tree = tree.add(f"[blue]def[/blue] {entity['name']}")
                if entity['docstring']:
                    function_tree.add(f"[green]'''{entity['docstring']}'''[/green]")

        console.print(tree)

@parser_app.command(name="scan")
def scan_directory(
    directory: str,
    db_path: str = typer.Option("./cmm.db", "--db-path", help="Path to SQLite database."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output."),
):
    """
    Scans a directory recursively for Python files and stores results in SQLite.
    """
    parser = TreeSitterParser()
    storage = SQLiteStorage(db_path)
    
    # Find all Python files
    directory_path = Path(directory)
    if not directory_path.exists():
        console.print(f"[red]Error: Directory '{directory}' does not exist.[/red]")
        raise typer.Exit(1)
    
    # Exclude common directories
    exclude_dirs = {'__pycache__', '.git', '.venv', 'venv', 'env', 'node_modules', '.tox'}
    
    python_files = []
    for py_file in directory_path.rglob("*.py"):
        # Check if any parent directory is in exclude list
        if not any(part in exclude_dirs for part in py_file.parts):
            python_files.append(py_file)
    
    if not python_files:
        console.print(f"[yellow]No Python files found in '{directory}'.[/yellow]")
        return
    
    console.print(f"[cyan]Found {len(python_files)} Python file(s) to scan.[/cyan]")
    
    # Process files with progress indicator
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning files...", total=len(python_files))
        
        scanned = 0
        errors = 0
        
        for py_file in python_files:
            file_path = str(py_file.absolute())
            
            try:
                if verbose:
                    progress.console.print(f"  Parsing: {py_file.relative_to(directory_path)}")
                
                cmm_entity = parser.scan_file(file_path)
                storage.upsert_file(file_path, cmm_entity)
                scanned += 1
                
            except Exception as e:
                errors += 1
                if verbose:
                    progress.console.print(f"  [red]Error parsing {py_file.name}: {e}[/red]")
            
            progress.advance(task)
    
    console.print(f"\n[green]✓ Scanned {scanned} file(s) successfully.[/green]")
    if errors > 0:
        console.print(f"[yellow]⚠ {errors} file(s) had errors.[/yellow]")
    console.print(f"[cyan]Database: {db_path}[/cyan]")

if __name__ == "__main__":
    app()
