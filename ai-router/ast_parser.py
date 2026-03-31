"""Costa AST — Tree-sitter parsing engine.

Provides incremental AST parsing, symbol extraction, scope resolution,
complexity analysis, and change classification. Consumed by ast_daemon.py
via the D-Bus service.

All public functions accept file paths or source bytes and return plain
dicts/lists suitable for JSON serialization over D-Bus.
"""

import os
import re
from pathlib import Path
from typing import Optional

from tree_sitter import Node
from tree_sitter_language_pack import get_language, get_parser

# ── Language Detection ──────────────────────────────────────────────

EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".lua": "lua",
    ".md": "markdown",
    ".css": "css",
    ".scss": "css",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".sql": "sql",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".zig": "zig",
    ".nim": "nim",
    ".ex": "elixir",
    ".exs": "elixir",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".r": "r",
    ".R": "r",
    ".pl": "perl",
    ".pm": "perl",
    ".dockerfile": "dockerfile",
    ".tf": "hcl",
    ".hcl": "hcl",
    ".proto": "proto",
    ".graphql": "graphql",
    ".gql": "graphql",
}

# Basename overrides (no extension or special names)
BASENAME_MAP: dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "make",
    "CMakeLists.txt": "cmake",
    "Cargo.toml": "toml",
    "pyproject.toml": "toml",
    "tsconfig.json": "json",
    "package.json": "json",
    ".bashrc": "bash",
    ".zshrc": "bash",
    ".profile": "bash",
}

# Node types that represent symbol definitions per language
SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "function_definition", "class_definition", "decorated_definition",
    },
    "javascript": {
        "function_declaration", "class_declaration", "method_definition",
        "arrow_function", "variable_declarator", "export_statement",
    },
    "typescript": {
        "function_declaration", "class_declaration", "method_definition",
        "arrow_function", "variable_declarator", "export_statement",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
    },
    "tsx": {
        "function_declaration", "class_declaration", "method_definition",
        "arrow_function", "variable_declarator", "export_statement",
        "interface_declaration", "type_alias_declaration", "enum_declaration",
    },
    "rust": {
        "function_item", "struct_item", "enum_item", "impl_item",
        "trait_item", "type_item", "const_item", "static_item",
        "mod_item", "macro_definition",
    },
    "go": {
        "function_declaration", "method_declaration", "type_declaration",
        "const_declaration", "var_declaration",
    },
    "bash": {
        "function_definition",
    },
    "c": {
        "function_definition", "struct_specifier", "enum_specifier",
        "type_definition", "declaration",
    },
    "cpp": {
        "function_definition", "class_specifier", "struct_specifier",
        "enum_specifier", "type_definition", "namespace_definition",
        "template_declaration",
    },
    "java": {
        "class_declaration", "method_declaration", "interface_declaration",
        "enum_declaration", "constructor_declaration",
    },
}

# Scope-defining node types (blocks that create a new scope)
SCOPE_NODE_TYPES: set[str] = {
    # Python
    "function_definition", "class_definition", "for_statement",
    "while_statement", "if_statement", "with_statement", "try_statement",
    # JS/TS
    "function_declaration", "class_declaration", "method_definition",
    "arrow_function", "for_statement", "for_in_statement",
    "while_statement", "if_statement", "try_statement", "switch_statement",
    # Rust
    "function_item", "impl_item", "trait_item", "mod_item",
    "for_expression", "while_expression", "if_expression", "match_expression",
    "block", "closure_expression",
    # Go
    "function_declaration", "method_declaration", "for_statement",
    "if_statement", "switch_statement",
    # General
    "block", "statement_block",
}

# Complexity-adding node types (branches, loops, boolean operators)
COMPLEXITY_NODES: set[str] = {
    "if_statement", "if_expression", "elif_clause", "else_clause",
    "for_statement", "for_expression", "for_in_statement",
    "while_statement", "while_expression",
    "try_statement", "except_clause", "catch_clause",
    "switch_statement", "match_expression", "switch_case",
    "conditional_expression", "ternary_expression",
    "boolean_operator", "binary_expression",  # && and ||
    "pattern_list",  # match arms
}


def detect_language(filepath: str) -> Optional[str]:
    """Detect tree-sitter language from file path."""
    p = Path(filepath)

    # Check basename first
    if p.name in BASENAME_MAP:
        return BASENAME_MAP[p.name]

    # Check extension
    ext = p.suffix.lower()
    return EXTENSION_MAP.get(ext)


def get_supported_languages() -> list[str]:
    """Return list of languages we can parse."""
    return sorted(set(EXTENSION_MAP.values()))


# ── Parser Cache ────────────────────────────────────────────────────

_parser_cache: dict[str, object] = {}


def _get_parser(lang: str):
    """Get or create a cached parser for a language."""
    if lang not in _parser_cache:
        try:
            _parser_cache[lang] = get_parser(lang)
        except Exception:
            return None
    return _parser_cache[lang]


# ── AST Cache (incremental) ────────────────────────────────────────

class ParsedFile:
    """Cached parse result for a single file."""
    __slots__ = ("path", "language", "tree", "source", "mtime", "symbols")

    def __init__(self, path: str, language: str, tree, source: bytes, mtime: float):
        self.path = path
        self.language = language
        self.tree = tree
        self.source = source
        self.mtime = mtime
        self.symbols: Optional[list[dict]] = None  # lazy-computed


# path → ParsedFile
_file_cache: dict[str, ParsedFile] = {}

# Maximum cached files (LRU eviction)
MAX_CACHE = 2000


def parse_file(filepath: str, force: bool = False) -> Optional[ParsedFile]:
    """Parse a file, using cache if unchanged. Returns None if unsupported."""
    filepath = os.path.realpath(filepath)

    lang = detect_language(filepath)
    if not lang:
        return None

    parser = _get_parser(lang)
    if not parser:
        return None

    try:
        stat = os.stat(filepath)
        mtime = stat.st_mtime

        # Skip files > 2MB
        if stat.st_size > 2 * 1024 * 1024:
            return None
    except OSError:
        # File gone — remove from cache
        _file_cache.pop(filepath, None)
        return None

    # Check cache
    cached = _file_cache.get(filepath)
    if cached and not force and cached.mtime >= mtime and cached.language == lang:
        return cached

    try:
        with open(filepath, "rb") as f:
            source = f.read()
    except (OSError, PermissionError):
        return None

    # Incremental parse if we have a previous tree for the same language
    old_tree = cached.tree if (cached and cached.language == lang) else None
    tree = parser.parse(source, old_tree=old_tree) if old_tree else parser.parse(source)

    pf = ParsedFile(filepath, lang, tree, source, mtime)

    # LRU eviction
    if len(_file_cache) >= MAX_CACHE and filepath not in _file_cache:
        oldest_key = next(iter(_file_cache))
        del _file_cache[oldest_key]

    _file_cache[filepath] = pf
    return pf


def invalidate_file(filepath: str):
    """Remove a file from the cache (e.g. after deletion)."""
    filepath = os.path.realpath(filepath)
    _file_cache.pop(filepath, None)


def get_cache_stats() -> dict:
    """Return cache statistics."""
    langs = {}
    for pf in _file_cache.values():
        langs[pf.language] = langs.get(pf.language, 0) + 1
    return {
        "cached_files": len(_file_cache),
        "max_cache": MAX_CACHE,
        "languages": langs,
    }


# ── Symbol Extraction ───────────────────────────────────────────────

def _extract_name(node: Node, source: bytes) -> str:
    """Extract the name from a definition node."""
    # Look for name/identifier child
    for child in node.children:
        if child.type in ("identifier", "name", "property_identifier",
                          "type_identifier", "field_identifier"):
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

    # For decorated definitions, recurse into the actual definition
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in SYMBOL_NODE_TYPES.get("python", set()):
                return _extract_name(child, source)

    # For variable_declarator (JS/TS), look for the name
    if node.type == "variable_declarator":
        if node.children:
            return source[node.children[0].start_byte:node.children[0].end_byte].decode(
                "utf-8", errors="replace"
            )

    # For export_statement, recurse
    if node.type == "export_statement":
        for child in node.children:
            name = _extract_name(child, source)
            if name:
                return name

    return ""


def _symbol_kind(node: Node) -> str:
    """Map tree-sitter node type to a human-readable symbol kind."""
    t = node.type
    if "function" in t or "method" in t or t == "arrow_function":
        return "function"
    if "class" in t:
        return "class"
    if "struct" in t:
        return "struct"
    if "enum" in t:
        return "enum"
    if "interface" in t:
        return "interface"
    if "type" in t and "alias" in t:
        return "type"
    if "trait" in t:
        return "trait"
    if "impl" in t:
        return "impl"
    if "mod" in t or "namespace" in t:
        return "module"
    if "const" in t or "static" in t:
        return "constant"
    if t == "variable_declarator":
        return "variable"
    if t == "decorated_definition":
        for child in node.children:
            k = _symbol_kind(child)
            if k != "unknown":
                return k
    if t == "export_statement":
        for child in node.children:
            k = _symbol_kind(child)
            if k != "unknown":
                return k
    return "unknown"


def _count_lines(node: Node) -> int:
    """Count the lines spanned by a node."""
    return node.end_point[0] - node.start_point[0] + 1


def get_symbols(filepath: str) -> list[dict]:
    """Extract top-level and nested symbols from a file.

    Returns list of dicts: {name, kind, line, end_line, lines, children}
    """
    pf = parse_file(filepath)
    if not pf:
        return []

    # Return cached symbols if available
    if pf.symbols is not None:
        return pf.symbols

    lang_symbols = SYMBOL_NODE_TYPES.get(pf.language, set())
    if not lang_symbols:
        # Fallback: collect any identifiable definitions
        lang_symbols = set()
        for syms in SYMBOL_NODE_TYPES.values():
            lang_symbols |= syms

    def _walk(node: Node, depth: int = 0) -> list[dict]:
        results = []
        for child in node.children:
            if child.type in lang_symbols:
                name = _extract_name(child, pf.source)
                if not name:
                    continue
                sym = {
                    "name": name,
                    "kind": _symbol_kind(child),
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "lines": _count_lines(child),
                }
                # Recurse for nested symbols (methods in classes, etc.)
                if depth < 3:
                    children = _walk(child, depth + 1)
                    if children:
                        sym["children"] = children
                results.append(sym)
            elif depth < 3:
                # Continue walking into non-symbol nodes (e.g. module body)
                results.extend(_walk(child, depth))
        return results

    symbols = _walk(pf.tree.root_node)
    pf.symbols = symbols
    return symbols


# ── Scope Resolution ────────────────────────────────────────────────

def get_scope(filepath: str, line: int, col: int) -> dict:
    """Get the scope chain at a given position (1-indexed line, 0-indexed col).

    Returns: {scopes: [{type, name, line, end_line}], language, path}
    """
    pf = parse_file(filepath)
    if not pf:
        return {"scopes": [], "language": None, "path": filepath}

    # Convert to 0-indexed
    row = line - 1
    point = (row, col)

    scopes = []
    node = pf.tree.root_node

    # Walk down to the deepest node containing the point
    def _find_scopes(n: Node):
        for child in n.children:
            if (child.start_point[0] < row or
                (child.start_point[0] == row and child.start_point[1] <= col)):
                if (child.end_point[0] > row or
                    (child.end_point[0] == row and child.end_point[1] >= col)):
                    if child.type in SCOPE_NODE_TYPES:
                        name = _extract_name(child, pf.source) or ""
                        scopes.append({
                            "type": child.type,
                            "name": name,
                            "line": child.start_point[0] + 1,
                            "end_line": child.end_point[0] + 1,
                        })
                    _find_scopes(child)

    _find_scopes(node)

    return {
        "scopes": scopes,
        "language": pf.language,
        "path": filepath,
        "line": line,
        "col": col,
    }


# ── Dependency / Reference Search ──────────────────────────────────

def get_dependents(filepath: str, symbol_name: str,
                   search_dirs: Optional[list[str]] = None) -> list[dict]:
    """Find files that reference a symbol.

    Searches files in the same directory (and search_dirs if provided)
    for references to the given symbol name. Uses AST-aware matching
    where possible, falling back to text search.

    Returns list of: {path, line, context, kind}
    """
    filepath = os.path.realpath(filepath)
    base_dir = os.path.dirname(filepath)
    lang = detect_language(filepath)

    dirs_to_search = [base_dir]
    if search_dirs:
        dirs_to_search.extend(search_dirs)

    results = []
    seen_files: set[str] = set()

    for search_dir in dirs_to_search:
        search_dir = os.path.realpath(search_dir)
        try:
            entries = os.listdir(search_dir)
        except OSError:
            continue

        for entry in entries:
            fp = os.path.join(search_dir, entry)
            if not os.path.isfile(fp):
                continue
            fp = os.path.realpath(fp)
            if fp == filepath or fp in seen_files:
                continue
            seen_files.add(fp)

            # Only search files with supported languages
            entry_lang = detect_language(fp)
            if not entry_lang:
                continue

            pf = parse_file(fp)
            if not pf:
                continue

            # Search for identifier references in the AST
            _find_references(pf, symbol_name, results)

    # Cap results
    return results[:100]


def _find_references(pf: ParsedFile, symbol_name: str, results: list[dict]):
    """Find references to a symbol in a parsed file's AST."""
    def _walk(node: Node):
        if node.type in ("identifier", "name", "property_identifier",
                          "type_identifier", "field_identifier"):
            text = pf.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            if text == symbol_name:
                # Get the parent context
                parent = node.parent
                context_node = parent if parent else node
                context = pf.source[context_node.start_byte:context_node.end_byte].decode(
                    "utf-8", errors="replace"
                )[:120]
                kind = "reference"
                if parent and parent.type in ("call_expression", "call"):
                    kind = "call"
                elif parent and "import" in parent.type:
                    kind = "import"

                results.append({
                    "path": pf.path,
                    "line": node.start_point[0] + 1,
                    "context": context.strip(),
                    "kind": kind,
                })
        for child in node.children:
            _walk(child)

    _walk(pf.tree.root_node)


# ── Complexity Analysis ─────────────────────────────────────────────

def get_complexity(filepath: str) -> dict:
    """Compute cyclomatic complexity for each function in a file.

    Returns: {path, language, functions: [{name, line, end_line, lines, complexity}],
              total_complexity, avg_complexity}
    """
    pf = parse_file(filepath)
    if not pf:
        return {"path": filepath, "language": None, "functions": [],
                "total_complexity": 0, "avg_complexity": 0.0}

    lang_symbols = SYMBOL_NODE_TYPES.get(pf.language, set())
    func_types = {t for t in lang_symbols if "function" in t or "method" in t}
    if not func_types:
        func_types = {"function_definition", "function_declaration",
                      "method_definition", "function_item"}

    functions = []

    def _complexity_of(node: Node) -> int:
        """Count complexity-adding nodes within a subtree."""
        count = 0
        if node.type in COMPLEXITY_NODES:
            count = 1
            # For boolean_operator/binary_expression, only count && and ||
            if node.type in ("boolean_operator", "binary_expression"):
                op_text = ""
                for child in node.children:
                    if child.type in ("and", "or", "&&", "||"):
                        op_text = pf.source[child.start_byte:child.end_byte].decode()
                if op_text not in ("and", "or", "&&", "||"):
                    count = 0
        for child in node.children:
            count += _complexity_of(child)
        return count

    def _find_functions(node: Node):
        for child in node.children:
            if child.type in func_types:
                name = _extract_name(child, pf.source)
                if name:
                    complexity = 1 + _complexity_of(child)  # base complexity = 1
                    functions.append({
                        "name": name,
                        "line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "lines": _count_lines(child),
                        "complexity": complexity,
                    })
            # Also check decorated definitions
            if child.type == "decorated_definition":
                _find_functions(child)
            # Recurse into classes/modules for methods
            elif child.type in ("class_definition", "class_declaration",
                                "class_specifier", "impl_item", "class_body",
                                "module"):
                _find_functions(child)
            # Continue into blocks
            elif child.type in ("block", "statement_block", "declaration_list"):
                _find_functions(child)

    _find_functions(pf.tree.root_node)

    total = sum(f["complexity"] for f in functions)
    avg = total / len(functions) if functions else 0.0

    return {
        "path": filepath,
        "language": pf.language,
        "functions": functions,
        "total_complexity": total,
        "avg_complexity": round(avg, 2),
    }


# ── Change Classification ──────────────────────────────────────────

def is_additive_change(diff_text: str, filepath: str) -> dict:
    """Analyze a unified diff to determine if changes are additive.

    An additive change only adds new symbols/lines without modifying
    or removing existing ones. Useful for routing decisions (additive
    changes are lower risk → can route to faster/cheaper model).

    Returns: {additive: bool, added_lines, removed_lines, modified_symbols,
              new_symbols, removed_symbols}
    """
    added_lines = 0
    removed_lines = 0
    added_symbols: list[str] = []
    removed_symbols: list[str] = []

    # Parse diff hunks
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            added_lines += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed_lines += 1

    # Parse the file to get current symbols
    pf = parse_file(filepath)
    current_symbols = set()
    if pf:
        for sym in get_symbols(filepath):
            current_symbols.add(sym["name"])

    # Extract symbol-like patterns from diff lines
    symbol_pattern = re.compile(
        r"(?:def |class |function |fn |func |pub fn |async fn |export )"
        r"(\w+)"
    )

    for line in diff_text.split("\n"):
        m = symbol_pattern.search(line)
        if not m:
            continue
        sym_name = m.group(1)
        if line.startswith("+") and not line.startswith("+++"):
            added_symbols.append(sym_name)
        elif line.startswith("-") and not line.startswith("---"):
            removed_symbols.append(sym_name)

    # Determine additive-ness
    modified = [s for s in removed_symbols if s in set(added_symbols)]
    purely_removed = [s for s in removed_symbols if s not in set(added_symbols)]
    purely_added = [s for s in added_symbols if s not in set(removed_symbols)]

    additive = removed_lines == 0 or (
        len(purely_removed) == 0 and removed_lines <= 2  # allow minor whitespace
    )

    return {
        "additive": additive,
        "added_lines": added_lines,
        "removed_lines": removed_lines,
        "new_symbols": purely_added,
        "removed_symbols": purely_removed,
        "modified_symbols": modified,
    }


# ── Quick Summary ───────────────────────────────────────────────────

def get_file_summary(filepath: str) -> dict:
    """Get a quick structural summary of a file.

    Useful for AI router context injection — gives the LLM structural
    understanding without sending the whole file.
    """
    pf = parse_file(filepath)
    if not pf:
        return {"path": filepath, "language": None, "parseable": False}

    symbols = get_symbols(filepath)
    total_lines = pf.source.count(b"\n") + 1

    # Count by kind
    kind_counts: dict[str, int] = {}
    total_symbol_lines = 0

    def _count(syms: list[dict]):
        nonlocal total_symbol_lines
        for s in syms:
            kind = s["kind"]
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            total_symbol_lines += s["lines"]
            if "children" in s:
                _count(s["children"])

    _count(symbols)

    # Get imports
    imports = []
    if pf.language in ("python", "javascript", "typescript", "tsx"):
        for child in pf.tree.root_node.children:
            if "import" in child.type:
                imp_text = pf.source[child.start_byte:child.end_byte].decode(
                    "utf-8", errors="replace"
                ).strip()
                imports.append(imp_text)

    return {
        "path": filepath,
        "language": pf.language,
        "parseable": True,
        "total_lines": total_lines,
        "symbols": kind_counts,
        "symbol_count": sum(kind_counts.values()),
        "imports": imports[:30],  # cap imports list
        "top_level": [
            {"name": s["name"], "kind": s["kind"], "lines": s["lines"]}
            for s in symbols[:50]
        ],
    }
