import typer
import json
from rich.tree import Tree
from rich.console import Console
from parser import TreeSitterParser
from domain import CMMEntity

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

if __name__ == "__main__":
    app()
