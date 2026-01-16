
import re
import os

FILE_PATH = 'templates/admin/dashboard.html'
BACKUP_PATH = 'templates/admin/dashboard.html.bak_operators'

def fix_operators(content):
    # Function to process content inside {% ... %} blocks
    def fix_block_content(match):
        block_content = match.group(0)
        # Normalize == spacing
        # This regex looks for == that might not have spaces around it
        # We replace any sequence of whitespace check whitespace with " == "
        block_content = re.sub(r'\s*==\s*', ' == ', block_content)
        block_content = re.sub(r'\s*!=\s*', ' != ', block_content)
        block_content = re.sub(r'\s*>=\s*', ' >= ', block_content)
        block_content = re.sub(r'\s*<=\s*', ' <= ', block_content)
        # Also fix > and < if they are surrounded by variables/values (careful not to break other syntax)
        # But generally Django requires spaces around operators.
        
        # Clean up double spaces we might have introduced
        block_content = re.sub(r'\s+', ' ', block_content)
        
        # Restore the {% and %} which might have lost their internal spacing in the cleanup
        # actually re.sub('\s+', ' ') creates {% if ... %} which is fine.
        # But let's ensure the block start/end are clean.
        block_content = block_content.replace('{ %', '{%').replace('% }', '%}')
        
        return block_content

    # Regex to find {% ... %} blocks
    # We apply the fix ONLY inside these blocks to avoid messing up HTML attributes or text
    content = re.sub(r'\{%.*?%\}', fix_block_content, content, flags=re.DOTALL)
    
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

    fixed_content = fix_operators(original_content)
    
    # Check if changes were made
    if fixed_content == original_content:
        print("No operator spacing issues found.")
    else:
        print("Applying operator spacing fixes...")
        with open(FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print("Done! Operator spacing normalized.")

if __name__ == "__main__":
    main()
