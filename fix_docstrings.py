#!/usr/bin/env python3
"""Script to fix unclosed docstrings in Python files."""

import os
import re
import ast
import sys
from pathlib import Path


def check_syntax(code: str) -> tuple[bool, str]:
    """Check if Python code has valid syntax."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def find_unclosed_docstrings(content: str) -> list[tuple[int, str]]:
    """Find lines with unclosed docstrings after function/method definitions."""
    lines = content.split('\n')
    issues = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check if this is a function/method definition ending with :
        if (stripped.startswith('def ') or stripped.startswith('async def ')) and stripped.endswith(':'):
            # Check next line for unclosed docstring
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                
                # Pattern: just """ without closing on same line
                if next_stripped == '"""':
                    # Check if the line after that looks like code (not docstring continuation)
                    if i + 2 < len(lines):
                        after_line = lines[i + 2].strip()
                        # If it looks like code (has = or starts with keywords), it's unclosed
                        if (after_line and 
                            not after_line.startswith('#') and
                            not after_line == '"""' and
                            (re.match(r'^[a-zA-Z_]', after_line) or 
                             after_line.startswith('if ') or
                             after_line.startswith('for ') or
                             after_line.startswith('while ') or
                             after_line.startswith('try:') or
                             after_line.startswith('return ') or
                             after_line.startswith('await ') or
                             '=' in after_line)):
                            issues.append((i + 1, next_line))  # i+1 is the line with """
        i += 1
    
    return issues


def fix_unclosed_docstring(lines: list[str], line_idx: int, func_name: str = "") -> list[str]:
    """Fix an unclosed docstring at the given line index."""
    # Get the indentation of the docstring line
    docstring_line = lines[line_idx]
    indent = len(docstring_line) - len(docstring_line.lstrip())
    indent_str = docstring_line[:indent]
    
    # Replace the lone """ with a proper closed docstring
    lines[line_idx] = f'{indent_str}"""Function docstring."""'
    
    return lines


def fix_file(filepath: str, dry_run: bool = False) -> tuple[bool, str]:
    """Fix unclosed docstrings in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, f"Error reading file: {e}"
    
    # First check if file has syntax errors
    is_valid, error = check_syntax(content)
    if is_valid:
        return True, "File already valid"
    
    lines = content.split('\n')
    original_lines = lines.copy()
    
    # Find and fix unclosed docstrings
    issues = find_unclosed_docstrings(content)
    
    if not issues:
        return False, f"Syntax error but no unclosed docstrings found: {error}"
    
    # Fix issues (process in reverse order to preserve line numbers)
    for line_idx, _ in reversed(issues):
        lines = fix_unclosed_docstring(lines, line_idx)
    
    new_content = '\n'.join(lines)
    
    # Verify fix worked
    is_valid, new_error = check_syntax(new_content)
    
    if not is_valid:
        # Try alternative fixes
        return False, f"Fix did not resolve syntax error: {new_error}"
    
    if dry_run:
        print(f"Would fix {len(issues)} issues in {filepath}")
        for line_idx, line in issues:
            print(f"  Line {line_idx + 1}: {line.strip()}")
        return True, f"Would fix {len(issues)} issues"
    
    # Write fixed content
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True, f"Fixed {len(issues)} unclosed docstrings"
    except Exception as e:
        return False, f"Error writing file: {e}"


def scan_and_fix_directory(directory: str, dry_run: bool = False) -> dict:
    """Scan directory and fix all Python files with syntax errors."""
    results = {
        'fixed': [],
        'already_valid': [],
        'failed': [],
        'skipped': []
    }
    
    for root, dirs, files in os.walk(directory):
        # Skip common directories
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.mypy_cache'}]
        
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = os.path.join(root, file)
            
            # Check current syntax
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                results['skipped'].append((filepath, str(e)))
                continue
            
            is_valid, _ = check_syntax(content)
            
            if is_valid:
                results['already_valid'].append(filepath)
                continue
            
            # Try to fix
            success, message = fix_file(filepath, dry_run)
            
            if success and "Fixed" in message:
                results['fixed'].append((filepath, message))
            elif success:
                results['already_valid'].append(filepath)
            else:
                results['failed'].append((filepath, message))
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix unclosed docstrings in Python files')
    parser.add_argument('directories', nargs='*', default=['twelvesteps', 'twelvesteps_tgbot'],
                        help='Directories to scan (default: twelvesteps, twelvesteps_tgbot)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
    parser.add_argument('--file', type=str, help='Fix a specific file instead of scanning directories')
    
    args = parser.parse_args()
    
    if args.file:
        success, message = fix_file(args.file, args.dry_run)
        print(f"{args.file}: {message}")
        sys.exit(0 if success else 1)
    
    print("=" * 60)
    print("Scanning for Python files with unclosed docstrings...")
    print("=" * 60)
    
    all_results = {
        'fixed': [],
        'already_valid': [],
        'failed': [],
        'skipped': []
    }
    
    for directory in args.directories:
        if not os.path.exists(directory):
            print(f"Warning: Directory {directory} does not exist, skipping")
            continue
        
        print(f"\nScanning {directory}...")
        results = scan_and_fix_directory(directory, args.dry_run)
        
        for key in all_results:
            all_results[key].extend(results[key])
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if all_results['fixed']:
        print(f"\nFixed ({len(all_results['fixed'])} files):")
        for filepath, message in all_results['fixed']:
            print(f"  [OK] {filepath}: {message}")
    
    if all_results['failed']:
        print(f"\nFailed ({len(all_results['failed'])} files):")
        for filepath, message in all_results['failed']:
            print(f"  [X] {filepath}: {message}")
    
    if all_results['skipped']:
        print(f"\nSkipped ({len(all_results['skipped'])} files):")
        for filepath, message in all_results['skipped']:
            print(f"  [?] {filepath}: {message}")
    
    print(f"\nSummary:")
    print(f"  Already valid: {len(all_results['already_valid'])}")
    print(f"  Fixed: {len(all_results['fixed'])}")
    print(f"  Failed: {len(all_results['failed'])}")
    print(f"  Skipped: {len(all_results['skipped'])}")
    
    if args.dry_run:
        print("\n(Dry run - no changes were made)")
    
    # Exit with error if there are failures
    sys.exit(1 if all_results['failed'] else 0)


if __name__ == '__main__':
    main()

