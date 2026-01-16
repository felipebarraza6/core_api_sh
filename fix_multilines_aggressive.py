
import re
import os

FILE_PATH = "/root/core_api_sh/templates/admin/dashboard.html"

def flatten_tags(text):
    # Pattern for {{ ... }} that might span lines
    # dotall=True allows . to match newlines
    
    def replacer(match):
        content = match.group(0)
        # Check if it has a newline
        if '\n' in content:
            # Replace newlines and extra spaces inside the tag
            flat = re.sub(r'\s+', ' ', content)
            return flat
        return content

    # Regex for {{ ... }}
    # We use non-greedy matching .*?
    variable_pattern = re.compile(r'\{\{.*?\}\}', re.DOTALL)
    text = variable_pattern.sub(replacer, text)

    # Regex for {% ... %}
    block_pattern = re.compile(r'\{%.*?%\}', re.DOTALL)
    text = block_pattern.sub(replacer, text)
    
    return text

def main():
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return

    print(f"Reading {FILE_PATH}...")
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    new_content = flatten_tags(content)

    if original_content != new_content:
        print("Differences found. Writing fixed content...")
        with open(FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Success! Multi-line tags flattened.")
    else:
        print("No multi-line tags found to fix.")

if __name__ == "__main__":
    main()
