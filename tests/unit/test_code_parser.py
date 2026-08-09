"""Tests for the code parsers — AST (P2-603) and heuristic fallback (P2-604)."""

from __future__ import annotations

import logging

from app.domain.document_intelligence import CodeStructure
from app.infrastructure.document_intelligence.code import parse_code
from app.infrastructure.document_intelligence.code import parser as parser_module
from app.infrastructure.document_intelligence.code.parser import _AstCodeParser


class TestLanguages:
    def test_ast_parser_languages(self) -> None:
        assert _AstCodeParser.languages == frozenset({"python"})


class TestImports:
    def test_parse_simple_imports(self) -> None:
        cs = parse_code("import os\nfrom typing import List\n", "mod.py")
        assert len(cs.imports) == 2
        assert cs.imports[0].module == "os"
        assert cs.imports[0].names == []
        assert cs.imports[0].level == 0
        assert cs.imports[1].module == "typing"
        assert cs.imports[1].names == ["List"]
        assert cs.imports[1].level == 0

    def test_import_forms(self) -> None:
        cs = parse_code(
            "import os.path as path\nfrom . import sibling\nfrom .utils import helper as h\n",
            "mod.py",
        )
        assert len(cs.imports) == 3
        assert cs.imports[0].module == "os.path"
        assert cs.imports[0].names == ["path"]
        assert cs.imports[1].module == "."
        assert cs.imports[1].names == ["sibling"]
        assert cs.imports[1].level == 1
        assert cs.imports[2].module == "utils"
        assert cs.imports[2].names == ["h"]
        assert cs.imports[2].level == 1


class TestFunctions:
    def test_parse_functions_with_docstring(self) -> None:
        cs = parse_code(
            'def greet(name):\n    """Say hi."""\n    return f"hi {name}"\n',
            "greet.py",
        )
        assert len(cs.functions) == 1
        fn = cs.functions[0]
        assert fn.name == "greet"
        assert fn.docstring == "Say hi."

    def test_parse_async_function(self) -> None:
        cs = parse_code('async def fetch():\n    """Fetch data."""\n    return 1\n', "fetch.py")
        assert len(cs.functions) == 1
        assert cs.functions[0].name == "fetch"
        assert cs.functions[0].docstring == "Fetch data."

    def test_parse_nested_functions(self) -> None:
        text = (
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
            "    return inner\n"
            "\n"
            "def top():\n"
            "    pass\n"
        )
        cs = parse_code(text, "nested.py")
        assert [fn.name for fn in cs.functions] == ["outer", "top"]

    def test_function_args(self) -> None:
        cs = parse_code("def f(a, b=1, *args, c, **kw):\n    pass\n", "f.py")
        assert cs.functions[0].args == ["a", "b", "args", "c", "kw"]


class TestClasses:
    def test_parse_class_with_methods(self) -> None:
        text = (
            'class Greeter:\n'
            '    """Greet people."""\n'
            '\n'
            '    def greet(self, name):\n'
            '        """Say hi."""\n'
            '        return f"hi {name}"\n'
            '\n'
            '    def farewell(self):\n'
            '        pass\n'
        )
        cs = parse_code(text, "greeter.py")
        assert len(cs.classes) == 1
        cls = cs.classes[0]
        assert cls.name == "Greeter"
        assert cls.docstring == "Greet people."
        assert len(cls.methods) == 2
        assert [m.name for m in cls.methods] == ["greet", "farewell"]

    def test_class_with_bases(self) -> None:
        cs = parse_code("class Greeter(Base, mixins.Speaker):\n    pass\n", "g.py")
        assert cs.classes[0].bases == ["Base", "mixins.Speaker"]


class TestOffsets:
    def test_offsets_are_accurate(self) -> None:
        text = 'import os\n\ndef greet(name):\n    """Say hi."""\n    return f"hi {name}"\n'
        cs = parse_code(text, "greet.py")
        fn = cs.functions[0]
        span = text[fn.start_char : fn.end_char]
        assert span == 'def greet(name):\n    """Say hi."""\n    return f"hi {name}"'

    def test_offsets_with_crlf(self) -> None:
        text = "import os\r\n\r\ndef greet(name):\r\n    pass\r\n"
        cs = parse_code(text, "greet.py")
        fn = cs.functions[0]
        assert text[fn.start_char : fn.end_char] == "def greet(name):\r\n    pass"

    def test_structure_char_range_covers_file(self) -> None:
        text = 'def f():\n    """Doc."""\n    return 1\n'
        cs = parse_code(text, "f.py")
        assert cs.char_start == 0
        assert cs.char_end == len(text)


class TestDocstrings:
    def test_docstrings_collected_in_order(self) -> None:
        text = (
            '"""Module doc."""\n'
            '\n'
            'def greet(name):\n'
            '    """Function doc."""\n'
            '    return name\n'
            '\n'
            'class Foo:\n'
            '    """Class doc."""\n'
            '\n'
            '    def method(self):\n'
            '        """Method doc."""\n'
        )
        cs = parse_code(text, "mod.py")
        assert cs.docstrings == ["Module doc.", "Function doc.", "Class doc.", "Method doc."]

    def test_no_docstrings_when_absent(self) -> None:
        cs = parse_code("def f():\n    return 1\n", "f.py")
        assert cs.docstrings == []
        assert cs.functions[0].docstring is None


class TestRobustness:
    def test_empty_file(self) -> None:
        cs = parse_code("", "empty.py")
        assert cs.language == "python"
        assert cs.imports == []
        assert cs.functions == []
        assert cs.classes == []
        assert cs.docstrings == []
        assert cs.char_start == 0
        assert cs.char_end == 0

    def test_syntax_error_returns_heuristic(self) -> None:
        cs = parse_code("def foo(:\n    return 1\n", "bad.py")
        assert isinstance(cs, CodeStructure)
        assert cs.language == "python"
        assert cs.imports == []
        assert cs.functions == []
        assert cs.classes == []

    def test_large_file_truncation(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(parser_module, "_MAX_CODE_CHARS", 10)
        text = "import os\n" * 20
        with caplog.at_level(logging.WARNING):
            cs = parse_code(text, "big.py")
        assert cs.char_end == 10
        assert len(cs.imports) == 1
        assert "Truncating big.py" in caplog.text

    def test_max_chars_parameter_overrides_default(self) -> None:
        cs = parse_code("import os\nimport sys\n", "big.py", max_chars=10)
        assert cs.char_end == 10
        assert [imp.module for imp in cs.imports] == ["os"]

    def test_non_python_returns_generic_structure(self) -> None:
        cs = parse_code("const x = 1;", "app.js")
        assert isinstance(cs, CodeStructure)
        assert cs.language == "javascript"
        assert cs.imports == []
        assert cs.functions == []
        assert cs.classes == []


class TestHeuristicParser:
    def test_heuristic_javascript_functions(self) -> None:
        text = (
            "export function foo() {\n"
            "  return 1;\n"
            "}\n"
            "\n"
            "async function bar() {\n"
            "  return 2;\n"
            "}\n"
        )
        cs = parse_code(text, "app.js")
        assert [fn.name for fn in cs.functions] == ["foo", "bar"]

    def test_heuristic_class_detection(self) -> None:
        text = "export class Bar {\n  method() {}\n}\n"
        cs = parse_code(text, "x.js")
        assert [cls.name for cls in cs.classes] == ["Bar"]

    def test_heuristic_import_extraction(self) -> None:
        text = "import React from 'react'\nimport { useState } from 'react'\n"
        cs = parse_code(text, "app.js")
        assert len(cs.imports) == 1
        assert cs.imports[0].module == "React"

    def test_heuristic_from_import(self) -> None:
        cs = parse_code("from typing import List\n", "x.js")
        assert cs.imports[0].module == "typing"

    def test_heuristic_never_raises(self) -> None:
        cs = parse_code("\x00\x01\x02 not code at all ###\n", "weird.xyz")
        assert isinstance(cs, CodeStructure)
        assert cs.language == "generic"
        assert cs.imports == []
        assert cs.functions == []
        assert cs.classes == []
        assert cs.docstrings == []

    def test_heuristic_offsets_are_approximate(self) -> None:
        text = "import React\n\nfunction foo() {\n  return 1;\n}\n"
        cs = parse_code(text, "app.jsx")
        fn = cs.functions[0]
        assert fn.start_line == 3
        assert fn.end_line == 3
        assert text[fn.start_char : fn.end_char] == "function foo() {\n"

    def test_heuristic_fallback_for_invalid_python(self) -> None:
        cs = parse_code("def foo(:\n  return 1\n", "broken.py")
        assert isinstance(cs, CodeStructure)
        assert cs.language == "python"
        assert cs.functions == []

    def test_heuristic_docstring_extraction(self) -> None:
        text = "function foo() {\n  return 1;\n}\n\"\"\"Module doc\"\"\"\n"
        cs = parse_code(text, "app.js")
        assert cs.docstrings == ["Module doc"]

    def test_non_python_file_dispatch(self) -> None:
        cs = parse_code("function foo() {\n  return 1;\n}\n", "app.js")
        assert cs.language == "javascript"
        assert [fn.name for fn in cs.functions] == ["foo"]
