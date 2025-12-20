"""
GraphML Adapter for exporting CMM entities to yEd-compatible format.

Uses the pyed library to generate hierarchical graphs with visual styling.
"""

from typing import Protocol, List, Dict, Any
import tempfile
import os
import pyed


class StructuralMapPort(Protocol):
    """Port for generating structural maps in GraphML format."""
    
    def generate(self, hierarchical_data: List[Dict[str, Any]], verified_only: bool = False) -> str:
        """Generates the formatted GraphML string from hierarchical data."""
        ...


class PyedGraphMLAdapter(StructuralMapPort):
    """
    Generates GraphML files using the pyed library.
    
    Implements visual styling based on Phase 8 specification:
    - Modules: Light blue groups (#A2C4C9)
    - Classes: Yellow rectangles (#FFD966)
    - Public Methods: Soft green rounded rectangles (#B6D7A8)
    - Private Methods: Soft red rounded rectangles (#EA9999)
    - Verified edges: Solid lines
    - Lazy edges: Dashed lines
    - Inheritance: Diamond arrows
    - Calls: Standard arrows
    """
    
    # Color palette (Phase 8 spec)
    COLOR_MODULE = "#A2C4C9"      # Light Blue
    COLOR_CLASS = "#FFD966"        # Yellow
    COLOR_PUBLIC = "#B6D7A8"       # Soft Green
    COLOR_PRIVATE = "#EA9999"      # Soft Red
    COLOR_VERIFIED = "#333333"     # Dark Gray
    COLOR_LAZY = "#999999"         # Light Gray
    
    def generate(self, hierarchical_data: List[Dict[str, Any]], verified_only: bool = False) -> str:
        """
        Generate GraphML using pyed library.
        
        Args:
            hierarchical_data: List of root entities with nested children and relations
            verified_only: If True, only include LSP-verified relations
            
        Returns:
            GraphML XML string
        """
        g = pyed.Graph()
        
        # Track node references for edge creation
        self.node_map: Dict[str, Any] = {}
        
        # Build hierarchical structure
        for root_entity in hierarchical_data:
            self._build_entity(g, root_entity, parent_node=None)
        
        # Add edges (relations)
        for root_entity in hierarchical_data:
            self._build_relations(g, root_entity, verified_only)
        
        # Write to temporary file and read back
        # (pyed only supports file output, not string)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.graphml', delete=False) as f:
            temp_path = f.name
        
        try:
            g.write_graph(temp_path)
            with open(temp_path, 'r') as gf:
                return gf.read()
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def _build_entity(self, graph: pyed.Graph, entity: Dict[str, Any], parent_node: Any) -> Any:
        """
        Recursively build entity nodes in the graph.
        
        Args:
            graph: pyed Graph instance
            entity: Entity dictionary with children
            parent_node: Parent node or group (None for root)
            
        Returns:
            Created node or group reference
        """
        entity_id = entity['id']
        entity_name = entity['name']
        entity_type = entity['type']
        visibility = entity.get('visibility', 'public')
        
        # Determine styling based on type and visibility
        if entity_type == 'module':
            # Modules are groups (containers)
            # Group takes 'background' not 'fill_color'
            node = graph.add_group(
                entity_name,
                shape="rectangle",
                background=self.COLOR_MODULE
            ) if parent_node is None else parent_node.add_group(
                entity_name,
                shape="rectangle",
                background=self.COLOR_MODULE
            )
        elif entity_type == 'class':
            # Classes are yellow rectangles (must be Groups to contain methods)
            node = (graph if parent_node is None else parent_node).add_group(
                entity_name,
                shape="rectangle",
                background=self.COLOR_CLASS
            )
        else:
            # Methods/Functions: color by visibility
            color = self.COLOR_PUBLIC if visibility == 'public' else self.COLOR_PRIVATE
            shape = "roundrectangle"
            
            # Add signature if available
            signature = entity.get('signature', '')
            label = f"{entity_name}\n{signature}" if signature else entity_name
            
            node = (graph if parent_node is None else parent_node).add_node(
                pyed.ShapeNode,
                label,
                shape=shape,
                background=color
            )
        
        # Store node reference for edge creation
        self.node_map[entity_id] = node
        
        # Recursively build children
        for child in entity.get('children', []):
            self._build_entity(graph, child, parent_node=node)
        
        return node
    
    def _build_relations(self, graph: pyed.Graph, entity: Dict[str, Any], verified_only: bool):
        """
        Recursively build edges (relations) in the graph.
        
        Args:
            graph: pyed Graph instance
            entity: Entity dictionary with relations
            verified_only: If True, skip unverified relations
        """
        entity_id = entity['id']
        
        # Add edges for this entity's relations
        for relation in entity.get('relations', []):
            # Skip unverified if filter is active
            if verified_only and not relation.get('is_verified'):
                continue
            
            from_id = entity_id
            to_id = relation.get('to_id')
            rel_type = relation.get('rel_type', 'calls')
            is_verified = relation.get('is_verified', False)
            
            # Only create edge if both nodes exist
            if from_id in self.node_map and to_id and to_id in self.node_map:
                from_node = self.node_map[from_id]
                to_node = self.node_map[to_id]
                
                # Determine edge styling
                line_type = "line" if is_verified else "dashed"
                color = self.COLOR_VERIFIED if is_verified else self.COLOR_LAZY
                
                # Determine arrow style based on relation type
                if rel_type == 'inherits':
                    arrowhead = "white_diamond"
                else:  # calls, depends_on, etc.
                    arrowhead = "standard"
                
                # Create edge
                graph.add_edge(
                    from_node,
                    to_node,
                    line_type=line_type,
                    color=color,
                    arrowhead=arrowhead
                )
        
        # Recursively process children
        for child in entity.get('children', []):
            self._build_relations(graph, child, verified_only)
