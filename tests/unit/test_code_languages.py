"""Tests for language registry (P2-602)."""

from __future__ import annotations

from app.core.extensions import CODE_EXTENSIONS
from app.infrastructure.document_intelligence.code.languages import (
    _EXTENSION_TO_LANGUAGE,
    language_from_filename,
)


class TestLanguageFromFilename:
    def test_python(self) -> None:
        assert language_from_filename("main.py") == "python"

    def test_javascript(self) -> None:
        assert language_from_filename("app.js") == "javascript"

    def test_typescript(self) -> None:
        assert language_from_filename("index.ts") == "typescript"

    def test_jsx_maps_to_javascript(self) -> None:
        assert language_from_filename("Component.jsx") == "javascript"

    def test_tsx_maps_to_typescript(self) -> None:
        assert language_from_filename("Component.tsx") == "typescript"

    def test_java(self) -> None:
        assert language_from_filename("Main.java") == "java"

    def test_c(self) -> None:
        assert language_from_filename("utils.c") == "c"

    def test_cpp(self) -> None:
        assert language_from_filename("engine.cpp") == "c++"

    def test_csharp(self) -> None:
        assert language_from_filename("Program.cs") == "c#"

    def test_go(self) -> None:
        assert language_from_filename("server.go") == "go"

    def test_ruby(self) -> None:
        assert language_from_filename("app.rb") == "ruby"

    def test_rust(self) -> None:
        assert language_from_filename("lib.rs") == "rust"

    def test_php(self) -> None:
        assert language_from_filename("index.php") == "php"

    def test_shell_sh(self) -> None:
        assert language_from_filename("run.sh") == "shell"

    def test_shell_bash(self) -> None:
        assert language_from_filename("run.bash") == "shell"

    def test_kotlin(self) -> None:
        assert language_from_filename("App.kt") == "kotlin"

    def test_swift(self) -> None:
        assert language_from_filename("main.swift") == "swift"

    def test_dart(self) -> None:
        assert language_from_filename("app.dart") == "dart"

    def test_scala(self) -> None:
        assert language_from_filename("Main.scala") == "scala"

    def test_r(self) -> None:
        assert language_from_filename("analysis.r") == "r"

    def test_objective_c(self) -> None:
        assert language_from_filename("ios.m") == "objective-c"

    def test_powershell(self) -> None:
        assert language_from_filename("script.ps1") == "powershell"

    def test_sql(self) -> None:
        assert language_from_filename("query.sql") == "sql"

    def test_css(self) -> None:
        assert language_from_filename("style.css") == "css"

    def test_scss(self) -> None:
        assert language_from_filename("style.scss") == "scss"

    def test_less(self) -> None:
        assert language_from_filename("style.less") == "less"

    def test_vue(self) -> None:
        assert language_from_filename("App.vue") == "vue"

    def test_svelte(self) -> None:
        assert language_from_filename("App.svelte") == "svelte"

    def test_unknown_extension_returns_generic(self) -> None:
        assert language_from_filename("file.xyz") == "generic"

    def test_no_extension_returns_generic(self) -> None:
        assert language_from_filename("Makefile") == "generic"

    def test_case_insensitive(self) -> None:
        assert language_from_filename("Main.PY") == "python"
        assert language_from_filename("APP.JS") == "javascript"
        assert language_from_filename("style.CSS") == "css"

    def test_path_with_directories(self) -> None:
        assert language_from_filename("src/utils/helpers.py") == "python"
        assert language_from_filename("lib/index.ts") == "typescript"

    def test_all_code_extensions_mapped(self) -> None:
        """Every extension in CODE_EXTENSIONS has a mapping."""
        unmapped = CODE_EXTENSIONS - set(_EXTENSION_TO_LANGUAGE)
        assert unmapped == set(), f"Unmapped extensions: {unmapped}"

    def test_no_orphan_mappings(self) -> None:
        """No mapping references an extension absent from CODE_EXTENSIONS."""
        orphans = set(_EXTENSION_TO_LANGUAGE) - CODE_EXTENSIONS
        assert orphans == set(), f"Orphan mappings: {orphans}"
