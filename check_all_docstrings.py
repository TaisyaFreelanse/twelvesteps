#!/usr/bin/env python3
"""Check all docstrings in Python files for proper closure."""

import os
import ast
import re
from pathlib import Path


def find_all_docstrings(filepath: str) -> list:
    """Find all docstrings in a Python file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return [("error", f"Cannot read file: {e}")]
    
    lines = content.split('\n')
    docstrings = []
    
    # Find all triple-quoted strings
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for triple quotes
        if '"""' in line or "'''" in line:
            # Count occurrences
            triple_double = line.count('"""')
            triple_single = line.count("'''")
            
            # If odd number, it's an opening or closing
            if triple_double % 2 == 1 or triple_single % 2 == 1:
                # Check if it's a docstring (after def/class/async def)
                if i > 0:
                    prev_line = lines[i-1].strip()
                    if prev_line.endswith(':') and (prev_line.startswith('def ') or 
                                                     prev_line.startswith('async def ') or
                                                     prev_line.startswith('class ')):
                        # This is likely a docstring
                        quote_type = '"""' if '"""' in line else "'''"
                        # Check if it's closed on the same line
                        if line.count(quote_type) >= 2:
                            docstrings.append((i+1, "closed", line[:80]))
                        else:
                            # Check if it's closed on next lines
                            closed = False
                            for j in range(i+1, min(i+10, len(lines))):
                                if quote_type in lines[j]:
                                    closed = True
                                    break
                            if not closed:
                                docstrings.append((i+1, "unclosed", line[:80]))
        i += 1
    
    return docstrings


def check_file_syntax(filepath: str) -> tuple[bool, str]:
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def scan_directory(directory: str) -> dict:
    """Scan directory for Python files and check docstrings."""
    results = {
        'valid': [],
        'invalid_syntax': [],
        'unclosed_docstrings': [],
        'total_files': 0
    }
    
    for root, dirs, files in os.walk(directory):
        # Skip common directories
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.mypy_cache', 'alembic'}]
        
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = os.path.join(root, file)
            results['total_files'] += 1
            
            # Check syntax
            is_valid, error = check_file_syntax(filepath)
            
            if not is_valid:
                results['invalid_syntax'].append((filepath, error))
                continue
            
            # Check docstrings
            docstrings = find_all_docstrings(filepath)
            unclosed = [d for d in docstrings if d[1] == "unclosed"]
            
            if unclosed:
                results['unclosed_docstrings'].append((filepath, unclosed))
            else:
                results['valid'].append(filepath)
    
    return results


def main():
    directory = "twelvesteps"
    
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist!")
        return
    
    print("=" * 70)
    print("Checking all docstrings in backend (twelvesteps/)")
    print("=" * 70)
    print()
    
    results = scan_directory(directory)
    
    print(f"Total Python files: {results['total_files']}")
    print(f"Valid files: {len(results['valid'])}")
    print(f"Files with syntax errors: {len(results['invalid_syntax'])}")
    print(f"Files with unclosed docstrings: {len(results['unclosed_docstrings'])}")
    print()
    
    if results['invalid_syntax']:
        print("=" * 70)
        print("FILES WITH SYNTAX ERRORS:")
        print("=" * 70)
        for filepath, error in results['invalid_syntax']:
            print(f"\n[ERROR] {filepath}")
            print(f"  {error}")
    
    if results['unclosed_docstrings']:
        print("\n" + "=" * 70)
        print("FILES WITH UNCLOSED DOCSTRINGS:")
        print("=" * 70)
        for filepath, unclosed_list in results['unclosed_docstrings']:
            print(f"\n[WARNING] {filepath}")
            for line_num, status, line_preview in unclosed_list:
                print(f"  Line {line_num}: {line_preview}")
    
    if not results['invalid_syntax'] and not results['unclosed_docstrings']:
        print("=" * 70)
        print("ALL FILES ARE VALID!")
        print("=" * 70)
        print(f"All {len(results['valid'])} Python files have valid syntax")
        print("and all docstrings are properly closed.")


if __name__ == '__main__':
    main()

