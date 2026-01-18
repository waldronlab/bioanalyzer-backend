#!/usr/bin/env python3
"""
Code Analysis Script for BioAnalyzer Backend
Identifies unused code, imports, and potential dead code paths.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# Project root
PROJECT_ROOT = Path(__file__).parent
APP_DIR = PROJECT_ROOT / "app"

# Files that are entry points (should not be marked as unused)
ENTRY_POINTS = {
    "main.py",
    "cli.py",
    "app/api/app.py",
    "app/__init__.py",
}

# Files that are likely used (tests, configs, etc.)
LIKELY_USED = {
    "setup.py",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
}

# Track imports and usage
imports_map: Dict[str, Set[str]] = defaultdict(set)  # file -> set of imports
usage_map: Dict[str, Set[str]] = defaultdict(set)  # module -> set of files using it
all_files: Set[str] = set()


def get_python_files(directory: Path) -> List[Path]:
    """Get all Python files in directory."""
    files = []
    for path in directory.rglob("*.py"):
        # Skip __pycache__ and build directories
        if "__pycache__" not in str(path) and "build" not in str(path):
            files.append(path)
    return files


def extract_imports(file_path: Path) -> Set[str]:
    """Extract all imports from a Python file."""
    imports = set()
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # Match: from app.xxx import yyy
        from_pattern = r"from\s+(app\.[\w.]+)\s+import"
        for match in re.finditer(from_pattern, content):
            imports.add(match.group(1))
        
        # Match: import app.xxx
        import_pattern = r"import\s+(app\.[\w.]+)"
        for match in re.finditer(import_pattern, content):
            imports.add(match.group(1))
            
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return imports


def file_to_module(file_path: Path) -> str:
    """Convert file path to module name."""
    rel_path = file_path.relative_to(PROJECT_ROOT)
    parts = rel_path.parts
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts = parts[:-1] + (parts[-1].replace(".py", ""),)
    return ".".join(parts)


def module_to_file(module: str) -> Path:
    """Convert module name to file path."""
    parts = module.split(".")
    if parts[0] != "app":
        return None
    
    # Try as file first
    file_path = PROJECT_ROOT / "/".join(parts) + ".py"
    if file_path.exists():
        return file_path
    
    # Try as package
    file_path = PROJECT_ROOT / "/".join(parts) / "__init__.py"
    if file_path.exists():
        return file_path
    
    return None


def analyze_codebase():
    """Analyze the codebase for unused code."""
    print("🔍 Analyzing BioAnalyzer Backend codebase...")
    print("=" * 80)
    
    # Get all Python files
    python_files = get_python_files(PROJECT_ROOT)
    print(f"\n📁 Found {len(python_files)} Python files")
    
    # Extract imports from all files
    print("\n📥 Extracting imports...")
    for file_path in python_files:
        rel_path = str(file_path.relative_to(PROJECT_ROOT))
        all_files.add(rel_path)
        imports = extract_imports(file_path)
        imports_map[rel_path] = imports
        
        # Track usage
        for imp in imports:
            usage_map[imp].add(rel_path)
    
    # Find unused modules
    print("\n🔎 Finding unused modules...")
    unused_modules = []
    potentially_unused = []
    
    for file_path in python_files:
        rel_path = str(file_path.relative_to(PROJECT_ROOT))
        
        # Skip entry points and likely used files
        if any(ep in rel_path for ep in ENTRY_POINTS):
            continue
        if any(lu in rel_path for lu in LIKELY_USED):
            continue
        
        # Convert to module
        module = file_to_module(file_path)
        if not module:
            continue
        
        # Check if module is imported anywhere
        is_used = False
        for imp, files in usage_map.items():
            if imp.startswith(module) or module.startswith(imp):
                # Check if it's used in actual code (not just tests)
                for f in files:
                    if "test" not in f.lower():
                        is_used = True
                        break
                if is_used:
                    break
        
        if not is_used:
            # Check if it's a test file
            if "test" in rel_path.lower():
                continue
            
            # Check if it's imported in __init__.py (might be exported)
            init_file = file_path.parent / "__init__.py"
            if init_file.exists():
                init_content = init_file.read_text()
                if module.split(".")[-1] in init_content:
                    continue
            
            unused_modules.append((rel_path, module))
    
    # Find duplicate/overlapping functionality
    print("\n🔄 Checking for duplicate functionality...")
    duplicates = []
    
    # Check for similar service files
    services = [f for f in all_files if "services" in f and f.endswith(".py")]
    for service in services:
        service_name = Path(service).stem
        # Check for similar names
        similar = [s for s in services if service_name in Path(s).stem and s != service]
        if similar:
            duplicates.append((service, similar))
    
    # Generate report
    print("\n" + "=" * 80)
    print("📊 ANALYSIS REPORT")
    print("=" * 80)
    
    print(f"\n✅ Total files analyzed: {len(python_files)}")
    print(f"📦 Total modules: {len(set(file_to_module(f) for f in python_files))}")
    
    if unused_modules:
        print(f"\n⚠️  POTENTIALLY UNUSED MODULES ({len(unused_modules)}):")
        print("-" * 80)
        for rel_path, module in sorted(unused_modules):
            print(f"  • {rel_path}")
            print(f"    Module: {module}")
            print()
    else:
        print("\n✅ No obviously unused modules found")
    
    if duplicates:
        print(f"\n🔄 POTENTIAL DUPLICATES ({len(duplicates)}):")
        print("-" * 80)
        for main, similar in duplicates:
            print(f"  • {main}")
            for s in similar:
                print(f"    - {s}")
            print()
    
    # Check for unused imports
    print("\n📋 Checking for unused imports in key files...")
    key_files = [
        "app/api/app.py",
        "app/services/bugsigdb_analyzer.py",
        "app/api/routers/system.py",
    ]
    
    for key_file in key_files:
        file_path = PROJECT_ROOT / key_file
        if file_path.exists():
            imports = imports_map.get(key_file, set())
            print(f"\n  {key_file}:")
            for imp in sorted(imports):
                # Check if import is actually used
                content = file_path.read_text()
                module_name = imp.split(".")[-1]
                if module_name not in content.replace(imp, ""):
                    print(f"    ⚠️  {imp} (might be unused)")
    
    # Specific findings
    print("\n" + "=" * 80)
    print("🎯 SPECIFIC FINDINGS")
    print("=" * 80)
    
    findings = []
    
    # Check pubmed_retrieval_service vs standalone_pubmed_retriever
    pubmed_service_usage = len([f for f in usage_map.get("app.services.pubmed_retrieval_service", []) if "test" not in f])
    standalone_usage = len([f for f in usage_map.get("app.services.standalone_pubmed_retriever", []) if "test" not in f])
    
    if pubmed_service_usage == 0:
        findings.append("❌ app/services/pubmed_retrieval_service.py - Not used in production code (only CLI)")
    if standalone_usage == 0:
        findings.append("❌ app/services/standalone_pubmed_retriever.py - Not used in production code (only CLI)")
    
    # Check utility files
    utils_to_check = [
        ("app/utils/data_processor.py", "data_processor"),
        ("app/utils/fallback_extractor.py", "fallback_extractor"),
        ("app/utils/methods_scorer.py", "methods_scorer"),
        ("app/utils/text_processing.py", "text_processing"),
    ]
    
    for file_path, module_name in utils_to_check:
        usage = len([f for f in usage_map.get(f"app.utils.{module_name}", []) if "test" not in f])
        if usage == 0:
            findings.append(f"❌ {file_path} - Not used in production code")
    
    # Check model files
    models_to_check = [
        ("app/models/config.py", "config"),
    ]
    
    for file_path, module_name in models_to_check:
        usage = len([f for f in usage_map.get(f"app.models.{module_name}", []) if "test" not in f])
        if usage == 0:
            findings.append(f"❌ {file_path} - Not used in production code")
    
    if findings:
        print("\n".join(findings))
    else:
        print("\n✅ No specific unused files identified")
    
    # Summary
    print("\n" + "=" * 80)
    print("💡 RECOMMENDATIONS")
    print("=" * 80)
    print("""
1. Review potentially unused modules - they might be:
   - Used dynamically (importlib)
   - Used in tests only
   - Planned for future use
   - CLI-only utilities

2. Consider consolidating duplicate functionality

3. Remove truly unused code to reduce:
   - Package size
   - Maintenance burden
   - Import time
   - Confusion

4. Document why certain modules exist if they're intentionally unused
    """)
    
    return {
        "unused_modules": unused_modules,
        "duplicates": duplicates,
        "findings": findings,
    }


if __name__ == "__main__":
    results = analyze_codebase()
    
    # Save results to file
    report_file = PROJECT_ROOT / "unused_code_analysis.txt"
    with open(report_file, "w") as f:
        f.write("BioAnalyzer Backend - Unused Code Analysis\n")
        f.write("=" * 80 + "\n\n")
        
        if results["unused_modules"]:
            f.write("POTENTIALLY UNUSED MODULES:\n")
            f.write("-" * 80 + "\n")
            for rel_path, module in results["unused_modules"]:
                f.write(f"{rel_path} ({module})\n")
            f.write("\n")
        
        if results["findings"]:
            f.write("SPECIFIC FINDINGS:\n")
            f.write("-" * 80 + "\n")
            for finding in results["findings"]:
                f.write(f"{finding}\n")
            f.write("\n")
    
    print(f"\n📄 Full report saved to: {report_file}")
