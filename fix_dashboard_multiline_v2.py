
import re
import os

FILE_PATH = 'templates/admin/dashboard.html'
BACKUP_PATH = 'templates/admin/dashboard.html.bak'

def flatten_django_tags(content):
    # Pattern to find {% ... %} tags that span multiple lines
    # dotall is not strictly needed if we match [\s\S] or similar, but let's use a specific approach.
    # We want to match {% followed by anything until %} where the content contains a newline.
    
    def replacer(match):
        text = match.group(0)
        # Replace newlines and multiple spaces with a single space
        return re.sub(r'\s+', ' ', text)

    # Regex for block tags {% ... %}
    # We use non-greedy matching .*? and DOTALL (s flag) to let . match newlines
    content = re.sub(r'\{%.*?%\}', replacer, content, flags=re.DOTALL)
    
    # Regex for variable tags {{ ... }}
    content = re.sub(r'\{\{.*?\}\}', replacer, content, flags=re.DOTALL)
    
    return content

def main():
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return

    print(f"Reading {FILE_PATH}...")
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        original_content = f.read()

    # Create backup
    with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
        f.write(original_content)
    print(f"Backup created at {BACKUP_PATH}")

    formatted_content = flatten_django_tags(original_content)
    
    # Check if changes were made
    if formatted_content == original_content:
        print("No multi-line tags found to fix.")
    else:
        print("Applying fixes...")
        with open(FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        print("Done! All multi-line tags have been flattened.")

if __name__ == "__main__":
    main()
