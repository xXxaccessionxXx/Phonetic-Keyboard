import os
import re
import sys
import subprocess

# Ensure Git and GitHub CLI are in the system path for this script
os.environ["PATH"] += r";C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI"

def main():
    print("=== Phonetic Keyboard Release Publisher ===")
    
    # 1. Read current version
    transliterator_path = "transliterator.py"
    with open(transliterator_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    match = re.search(r'VERSION\s*=\s*"v([^"]+)"', content)
    if not match:
        print("Could not find VERSION in transliterator.py")
        sys.exit(1)
        
    current_version = match.group(1)
    print(f"Current version: {current_version}")
    
    new_version = input("Enter new version (e.g. 1.0.1): ").strip()
    if new_version.lower().startswith('v'):
        new_version = new_version[1:]
    if not new_version:
        print("Version cannot be empty.")
        sys.exit(1)
        
    # Replace version in transliterator.py
    new_content = re.sub(r'VERSION\s*=\s*"v[^"]+"', f'VERSION = "v{new_version}"', content)
    with open(transliterator_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Updated transliterator.py")
    
    # Ask for release notes
    print("\nEnter release notes (Press Enter twice to finish):")
    lines = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
        
    notes = "\n".join(lines)
    
    # 2. Generate version_info.txt
    parts = [p for p in re.split(r'\D+', new_version) if p]
    while len(parts) < 4:
        parts.append('0')
    v_tuple = f"({parts[0]}, {parts[1]}, {parts[2]}, {parts[3]})"
    
    version_info_content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v_tuple},
    prodvers={v_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Kasey'),
        StringStruct('FileDescription', 'Phonetic Keyboard Transliterator'),
        StringStruct('FileVersion', '{new_version}'),
        StringStruct('InternalName', 'PhoneticKeyboard'),
        StringStruct('LegalCopyright', 'Copyright (c) Kasey'),
        StringStruct('OriginalFilename', 'PhoneticKeyboard.exe'),
        StringStruct('ProductName', 'Phonetic Keyboard'),
        StringStruct('ProductVersion', '{new_version}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open("version_info.txt", "w", encoding="utf-8") as f:
        f.write(version_info_content)
        
    print("Generated version_info.txt")
    
    # 3. Build executable
    print("Building executable...")
    # Modify spec to use version='version_info.txt' if not already
    spec_path = "PhoneticKeyboard.spec"
    with open(spec_path, "r", encoding="utf-8") as f:
        spec_content = f.read()
    if "version='version_info.txt'" not in spec_content:
        spec_content = spec_content.replace("icon='icon.ico',", "icon='icon.ico',\n    version='version_info.txt',")
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(spec_content)
            
    res = subprocess.run(["build.bat"], shell=True)
    if res.returncode != 0:
        print("Build failed!")
        sys.exit(1)
        
    # 4. Git commit and push
    print("Committing to Git...")
    subprocess.run("git add .", shell=True, check=True)
    subprocess.run(f'git commit -m "Release v{new_version}"', shell=True, check=True)
    subprocess.run("git push", shell=True, check=True)
    
    # 5. GitHub Release
    print("Creating GitHub Release...")
    notes_file = "temp_notes.txt"
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write(notes)
        
    try:
        subprocess.run(f'gh release create v{new_version} "dist/PhoneticKeyboard.exe" --title "v{new_version}" --notes-file "{notes_file}"', shell=True, check=True)
        print("Successfully published release!")
    except Exception as e:
        print(f"Failed to create release via gh: {e}")
    finally:
        if os.path.exists(notes_file):
            os.remove(notes_file)

if __name__ == "__main__":
    main()
