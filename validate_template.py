#!/usr/bin/env python3
"""
Simple Django template syntax validator
"""
import re
import sys

def validate_template(filepath):
    """Validate Django template for common syntax errors"""
    errors = []
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Check for multi-line if/elif/else conditions
    for i, line in enumerate(lines, 1):
        # Check if an if/elif statement ends with an incomplete condition
        if re.search(r'{%\s*(if|elif)\s+.*==\s*$', line):
            errors.append(f"Line {i}: Multi-line condition detected - Django templates require conditions on a single line")
        
        # Check for unmatched template tags
        if '{% elif' in line:
            # Look backwards to find the matching if
            found_if = False
            for j in range(i-2, max(0, i-100), -1):
                if '{% if' in lines[j]:
                    found_if = True
                    break
                elif '{% endfor' in lines[j] or '{% endblock' in lines[j]:
                    break
            if not found_if:
                errors.append(f"Line {i}: 'elif' without matching 'if'")
    
    return errors

if __name__ == '__main__':
    filepath = '/root/core_api_sh/templates/admin/dashboard.html'
    errors = validate_template(filepath)
    
    if errors:
        print("Template validation errors found:")
        for error in errors:
            print(f"  ❌ {error}")
        sys.exit(1)
    else:
        print("✅ Template validation passed - no multi-line conditions found")
        sys.exit(0)
