"""
LSP Client for communicating with Pyright language server.

Provides semantic analysis capabilities for deterministic dependency linking.
"""

import json
import subprocess
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class Location:
    """Represents a source code location returned by LSP."""
    uri: str
    line: int
    character: int
    
    @classmethod
    def from_lsp_response(cls, result: Dict[str, Any]) -> Optional['Location']:
        """Parse LSP textDocument/definition response."""
        if not result:
            return None
        
        # Handle single location or list of locations
        if isinstance(result, list):
            if not result:
                return None
            result = result[0]  # Take first match
        
        uri = result.get('uri', '')
        range_data = result.get('range', {})
        start = range_data.get('start', {})
        
        return cls(
            uri=uri,
            line=start.get('line', 0),
            character=start.get('character', 0)
        )


@dataclass
class TypeInfo:
    """Represents type information from LSP hover."""
    signature: Optional[str] = None
    documentation: Optional[str] = None
    
    @classmethod
    def from_lsp_response(cls, result: Dict[str, Any]) -> Optional['TypeInfo']:
        """Parse LSP textDocument/hover response."""
        if not result:
            return None
        
        contents = result.get('contents', {})
        
        # Handle markdown string or object
        if isinstance(contents, str):
            return cls(signature=contents)
        elif isinstance(contents, dict):
            value = contents.get('value', '')
            return cls(signature=value)
        elif isinstance(contents, list) and contents:
            # Take first item
            first = contents[0]
            if isinstance(first, str):
                return cls(signature=first)
            elif isinstance(first, dict):
                return cls(signature=first.get('value', ''))
        
        return None


class LSPClient:
    """Client for communicating with Pyright LSP server."""
    
    def __init__(self, workspace_root: str):
        """
        Initialize LSP client.
        
        Args:
            workspace_root: Absolute path to project root
        """
        self.workspace_root = workspace_root
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self._initialized = False
        
    def is_available(self) -> bool:
        """Check if Pyright is installed and available."""
        try:
            result = subprocess.run(
                ['python', '-m', 'pyright', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def start(self) -> bool:
        """
        Start Pyright language server process.
        
        Returns:
            True if started successfully, False otherwise
        """
        if not self.is_available():
            print("[LSP] Pyright not available, falling back to Lazy Linker")
            return False
        
        try:
            # Start pyright langserver via Python module
            self.process = subprocess.Popen(
                ['python', '-m', 'pyright', '--langserver'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0
            )
            
            # Send initialize request
            if self._initialize():
                self._initialized = True
                return True
            else:
                self.shutdown()
                return False
                
        except Exception as e:
            print(f"[LSP] Failed to start Pyright: {e}")
            return False
    
    def _initialize(self) -> bool:
        """Send LSP initialize request."""
        init_request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "processId": os.getpid(),
                "rootUri": f"file://{self.workspace_root}",
                "capabilities": {}
            }
        }
        
        response = self._send_request(init_request)
        if response and 'result' in response:
            # Send initialized notification
            self._send_notification({
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {}
            })
            return True
        return False
    
    def get_definition(self, file_uri: str, line: int, character: int) -> Optional[Location]:
        """
        Get definition location for symbol at position.
        
        Args:
            file_uri: File URI (e.g., "file:///path/to/file.py")
            line: Zero-based line number
            character: Zero-based character offset
            
        Returns:
            Location of definition or None if not found
        """
        if not self._initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": character}
            }
        }
        
        response = self._send_request(request)
        if response and 'result' in response:
            return Location.from_lsp_response(response['result'])
        return None
    
    def get_hover(self, file_uri: str, line: int, character: int) -> Optional[TypeInfo]:
        """
        Get type information for symbol at position.
        
        Args:
            file_uri: File URI (e.g., "file:///path/to/file.py")
            line: Zero-based line number
            character: Zero-based character offset
            
        Returns:
            TypeInfo with signature or None if not found
        """
        if not self._initialized:
            return None
        
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": file_uri},
                "position": {"line": line, "character": character}
            }
        }
        
        response = self._send_request(request)
        if response and 'result' in response:
            return TypeInfo.from_lsp_response(response['result'])
        return None
    
    def shutdown(self):
        """Shutdown the LSP server gracefully."""
        if self.process and self._initialized:
            try:
                shutdown_request = {
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "shutdown",
                    "params": None
                }
                self._send_request(shutdown_request)
                
                # Send exit notification
                self._send_notification({
                    "jsonrpc": "2.0",
                    "method": "exit",
                    "params": None
                })
                
                self.process.wait(timeout=5)
            except Exception as e:
                print(f"[LSP] Error during shutdown: {e}")
                if self.process:
                    self.process.kill()
            finally:
                self.process = None
                self._initialized = False
    
    def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send JSON-RPC request and wait for response."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None
        
        try:
            message = json.dumps(request)
            content = f"Content-Length: {len(message)}\r\n\r\n{message}"
            
            self.process.stdin.write(content)
            self.process.stdin.flush()
            
            # Read response
            return self._read_response()
            
        except Exception as e:
            print(f"[LSP] Request failed: {e}")
            return None
    
    def _send_notification(self, notification: Dict[str, Any]):
        """Send JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            return
        
        try:
            message = json.dumps(notification)
            content = f"Content-Length: {len(message)}\r\n\r\n{message}"
            
            self.process.stdin.write(content)
            self.process.stdin.flush()
        except Exception as e:
            print(f"[LSP] Notification failed: {e}")
    
    def _read_response(self) -> Optional[Dict[str, Any]]:
        """Read JSON-RPC response from stdout."""
        if not self.process or not self.process.stdout:
            return None
        
        try:
            # Read Content-Length header
            while True:
                line = self.process.stdout.readline()
                if line.startswith('Content-Length:'):
                    length = int(line.split(':')[1].strip())
                    break
            
            # Read blank line
            self.process.stdout.readline()
            
            # Read message body
            message = self.process.stdout.read(length)
            return json.loads(message)
            
        except Exception as e:
            print(f"[LSP] Failed to read response: {e}")
            return None
    
    def _next_id(self) -> int:
        """Generate next request ID."""
        self.request_id += 1
        return self.request_id
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
