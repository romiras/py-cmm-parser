"""
Basic integration test for LSP client.

Tests Pyright communication and fallback behavior.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from lsp_client import LSPClient, Location, TypeInfo


def test_lsp_availability():
    """Test if Pyright is available."""
    client = LSPClient(workspace_root=os.getcwd())
    
    is_available = client.is_available()
    print(f"✓ Pyright available: {is_available}")
    
    if not is_available:
        print("  Note: Install Pyright with: uv pip install pyright")
    
    return is_available


def test_lsp_lifecycle():
    """Test LSP client start/shutdown."""
    workspace_root = str(Path(__file__).parent.parent)
    client = LSPClient(workspace_root=workspace_root)
    
    if not client.is_available():
        print("⊘ Skipping lifecycle test (Pyright not available)")
        return
    
    # Test start
    started = client.start()
    print(f"✓ LSP client started: {started}")
    
    if started:
        # Test shutdown
        client.shutdown()
        print("✓ LSP client shutdown successful")


def test_lsp_context_manager():
    """Test LSP client as context manager."""
    workspace_root = str(Path(__file__).parent.parent)
    
    with LSPClient(workspace_root=workspace_root) as client:
        if client._initialized:
            print("✓ LSP client context manager works")
        else:
            print("⊘ LSP client not initialized (Pyright may not be available)")


def test_location_parsing():
    """Test Location dataclass parsing."""
    # Test single location
    lsp_response = {
        'uri': 'file:///path/to/file.py',
        'range': {
            'start': {'line': 42, 'character': 5},
            'end': {'line': 42, 'character': 20}
        }
    }
    
    location = Location.from_lsp_response(lsp_response)
    assert location is not None
    assert location.uri == 'file:///path/to/file.py'
    assert location.line == 42
    assert location.character == 5
    print("✓ Location parsing works")
    
    # Test list of locations
    lsp_response_list = [lsp_response]
    location = Location.from_lsp_response(lsp_response_list)
    assert location is not None
    print("✓ Location list parsing works")


def test_type_info_parsing():
    """Test TypeInfo dataclass parsing."""
    # Test markdown string
    lsp_response = {
        'contents': {
            'kind': 'markdown',
            'value': '(file_path: str) -> CMMEntity'
        }
    }
    
    type_info = TypeInfo.from_lsp_response(lsp_response)
    assert type_info is not None
    assert type_info.signature == '(file_path: str) -> CMMEntity'
    print("✓ TypeInfo parsing works")


if __name__ == '__main__':
    print("=" * 60)
    print("LSP Client Integration Tests")
    print("=" * 60)
    
    try:
        test_lsp_availability()
        test_location_parsing()
        test_type_info_parsing()
        test_lsp_lifecycle()
        test_lsp_context_manager()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
