#!/usr/bin/env python3
import re

file_path = '/root/core_api_sh/templates/admin/dashboard.html'

# Read entire file
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Count before
before_count = len(re.findall(r'{%\s+(if|elif)\s+[^%]*\s+(or|and)\s*\n', content))
print(f"Found {before_count} multiline tags before fixing")

# Fix all multiline if/elif tags
# This regex finds {% if/elif ... or/and\n and joins them
content = re.sub(
    r'({%\s+(?:if|elif)\s+[^%]+?)\s+(or|and)\s*\n\s*([^%]+?%})',
    r'\1 \2 \3',
    content,
    flags=re.MULTILINE
)

# Do it multiple times to catch nested cases
for _ in range(5):
    content = re.sub(
        r'({%\s+(?:if|elif)\s+[^%]+?)\s+(or|and)\s*\n\s*([^%]+?%})',
        r'\1 \2 \3',
        content,
        flags=re.MULTILINE
    )

# Count after
after_count = len(re.findall(r'{%\s+(if|elif)\s+[^%]*\s+(or|and)\s*\n', content))
print(f"Found {after_count} multiline tags after fixing")

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Fixed {before_count - after_count} multiline tags")
print("Done!")
