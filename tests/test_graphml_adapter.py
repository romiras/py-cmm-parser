import pytest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock
from graphml_adapter import PyedGraphMLAdapter


@pytest.fixture
def sample_hierarchical_data():
    return [
        {
            "id": "module_1",
            "name": "module_a",
            "type": "module",
            "visibility": "public",
            "children": [
                {
                    "id": "class_1",
                    "name": "MyClass",
                    "type": "class",
                    "visibility": "public",
                    "children": [
                        {
                            "id": "method_1",
                            "name": "my_method",
                            "type": "function",
                            "visibility": "public",
                            "children": [],
                            "relations": [
                                {
                                    "to_id": "method_2",
                                    "to_name": "other_method",
                                    "rel_type": "calls",
                                    "is_verified": 1
                                }
                            ]
                        },
                        {
                            "id": "method_2",
                            "name": "other_method",
                            "type": "function",
                            "visibility": "private",
                            "children": [],
                            "relations": []
                        }
                    ],
                    "relations": []
                }
            ],
            "relations": []
        }
    ]


def test_graphml_generation(sample_hierarchical_data):
    adapter = PyedGraphMLAdapter()
    xml_output = adapter.generate(sample_hierarchical_data)
    
    # Check if output is valid XML
    root = ET.fromstring(xml_output)
    assert root.tag.endswith("graphml")
    
    # Check if namespace is correct (pyed uses graphml)
    # Note: namespaces in ElementTree are in {}
    # We can check content more vaguely if namespaces are annoying
    
    # pyed generates internal IDs (e.g. ShapeNode_1), so we verify labels instead
    xml_str = xml_output
    assert '>module_a</y:NodeLabel>' in xml_str
    assert '>MyClass</y:NodeLabel>' in xml_str
    assert '>my_method</y:NodeLabel>' in xml_str
    
    # Check colors (styling)
    # Module color
    assert "#A2C4C9" in xml_str
    # Class color
    assert "#FFD966" in xml_str
    # Public method color
    assert "#B6D7A8" in xml_str
    # Private method color
    assert "#EA9999" in xml_str


def test_verified_only_filter(sample_hierarchical_data):
    # Add an unverified relation to sample data
    sample_hierarchical_data[0]['children'][0]['children'][1]['relations'].append({
        "to_id": "method_1",
        "to_name": "my_method",
        "rel_type": "calls",
        "is_verified": 0
    })
    
    adapter = PyedGraphMLAdapter()
    
    # 1. Without filter
    xml_full = adapter.generate(sample_hierarchical_data, verified_only=False)
    # Should have 2 edges (one verified, one unverified)
    # Edges in GraphML are <edge source="..." target="...">
    assert xml_full.count("<edge") == 2
    
    # 2. With filter
    xml_verified = adapter.generate(sample_hierarchical_data, verified_only=True)
    # Should have 1 edge
    assert xml_verified.count("<edge") == 1
    
    # Check styling of verified edge (solid line)
    # Note: pyed writes line_type as type="..." in PolyLineEdge
    # We'd have to check specific XML structure, but existence of edges is a good proxy.
