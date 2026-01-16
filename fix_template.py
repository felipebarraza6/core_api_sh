#!/usr/bin/env python3
import re

# Read file
with open('/root/core_api_sh/templates/admin/dashboard.html', 'r') as f:
    lines = f.readlines()

# Join lines and fix multiline tags
i = 0
fixed_lines = []
while i < len(lines):
    line = lines[i]
    
    # Check if this line has an incomplete if/elif tag
    if re.search(r'{%\s+(if|elif)\s+.*\s+(or|and|==)\s*$', line):
        # Collect continuation lines
        full_tag = line.rstrip()
        i += 1
        while i < len(lines) and not '%}' in full_tag:
            full_tag += ' ' + lines[i].strip()
            i += 1
        # Clean up whitespace
        full_tag = re.sub(r'\s+', ' ', full_tag)
        fixed_lines.append(full_tag + '\n')
    else:
        fixed_lines.append(line)
        i += 1

# Write back
with open('/root/core_api_sh/templates/admin/dashboard.html', 'w') as f:
    f.writelines(fixed_lines)

print("Template fixed successfully")
