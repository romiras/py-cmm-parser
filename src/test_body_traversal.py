import unittest
import os
from parser import TreeSitterParser

TEST_CODE = """
class MyClass:
    def my_method(self):
        self.helper()
        print("Debugging")
        
    def helper(self):
        other_func()

def global_func():
    MyClass()
"""


class TestBodyTraversal(unittest.TestCase):
    def setUp(self):
        self.test_file = "temp_test_code.py"
        with open(self.test_file, "w") as f:
            f.write(TEST_CODE)
        self.parser = TreeSitterParser()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_call_extraction(self):
        cmm = self.parser.scan_file(self.test_file)

        # Verify MyClass.my_method calls keys
        # Hierarchy: [MyClass, global_func]
        # MyClass methods: [my_method, helper]

        cls = next(e for e in cmm.entities if e["name"] == "MyClass")
        my_method = next(m for m in cls["methods"] if m["name"] == "my_method")

        deps = my_method.get("dependencies", [])
        # Expect 'helper' (print is filtered as builtin)
        call_names = [d["name"] for d in deps if d.get("rel_type") == "calls"]

        self.assertIn("helper", call_names)
        # print is now filtered as a builtin
        self.assertNotIn("print", call_names)
        self.assertNotIn("self", call_names)  # self is not a call

    def test_global_call_extraction(self):
        cmm = self.parser.scan_file(self.test_file)
        func = next(e for e in cmm.entities if e["name"] == "global_func")

        deps = func.get("dependencies", [])
        call_names = [d["name"] for d in deps if d.get("rel_type") == "calls"]

        self.assertIn("MyClass", call_names)


if __name__ == "__main__":
    unittest.main()
