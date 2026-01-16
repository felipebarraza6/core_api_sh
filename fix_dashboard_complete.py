
import re
import os

file_path = '/root/core_api_sh/templates/admin/dashboard.html'

def fix_file(path):
    print(f"Reading {path}...")
    with open(path, 'r') as f:
        content = f.read()

    # 1. Fix Block Tags {% ... %}
    # Identifies any {% ... %} tag containing a newline
    block_pattern = r"\{%.*?%\}"
    
    def replace_block_newlines(match):
        tag_content = match.group(0)
        if '\n' in tag_content:
            cleaned_content = re.sub(r'\s+', ' ', tag_content)
            # print(f"Fixed Block: {cleaned_content}")
            return cleaned_content
        return tag_content

    # 2. Fix Variable Tags {{ ... }}
    # Identifies any {{ ... }} tag containing a newline
    var_pattern = r"\{\{.*?\}\}"
    
    def replace_var_newlines(match):
        tag_content = match.group(0)
        if '\n' in tag_content:
            cleaned_content = re.sub(r'\s+', ' ', tag_content)
            # print(f"Fixed Var: {cleaned_content}")
            return cleaned_content
        return tag_content

    # Apply fixes
    new_content, block_count = re.subn(block_pattern, replace_block_newlines, content, flags=re.DOTALL)
    new_content, var_count = re.subn(var_pattern, replace_var_newlines, new_content, flags=re.DOTALL)
    
    print(f"Fixed {block_count} multi-line block tags.")
    print(f"Fixed {var_count} multi-line variable tags.")

    if new_content != content:
        with open(path, 'w') as f:
            f.write(new_content)
        print("Changes saved to file.")
    else:
        print("No multi-line tags found (File is already clean).")

if __name__ == "__main__":
    fix_file(file_path)
