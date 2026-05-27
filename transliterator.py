import keyboard
import sys
import os
import threading
import tkinter as tk
import pystray
from PIL import Image, ImageDraw
import re
import urllib.request
import json
import subprocess

VERSION = "v1.0.0"
REPO_API_URL = "https://api.github.com/repos/xXxaccessionxXx/Phonetic-Keyboard/releases/latest"

# Dictionary mapping English phonetic strings to Cyrillic equivalents
MAPPING = {
    'shch': 'щ', 'yo': 'ё', 'zh': 'ж', 'ch': 'ч', 'sh': 'ш',
    'yu': 'ю', 'ya': 'я', 'ts': 'ц', 'eh': 'э', 'ye': 'е', 'a': 'а', 'b': 'б',
    'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е', 'z': 'з', 'i': 'и',
    'y': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о',
    'p': 'п', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'f': 'ф',
    'h': 'х', "'": "ь", "''": "ъ", 'bl': 'ы'
}

# Custom dictionary mapping specific full words
CUSTOM_EXCEPTIONS = {
    'pozhaluysta': 'пожалуйста'
}

# Orthographic Rules (Regex replacements to be applied to the Cyrillic output)
ORTHOGRAPHIC_RULES = [
    (re.compile(r'жы'), 'жи'),
    (re.compile(r'шы'), 'ши'),
    (re.compile(r'жй'), 'жи'),
    (re.compile(r'шй'), 'ши'),
    (re.compile(r'чя'), 'ча'),
    (re.compile(r'щя'), 'ща'),
    (re.compile(r'чю'), 'чу'),
    (re.compile(r'щю'), 'щу'),
    (re.compile(r'^ёга'), 'йога'), # Contextual yo example
]

# State
is_active = False
english_buffer = ""
produced_cyrillic = ""

# UI Globals
root = None
dot_root = None
status_label = None
tray_icon = None

def toggle_active():
    global is_active, english_buffer, produced_cyrillic
    is_active = not is_active
    english_buffer = ""
    produced_cyrillic = ""
    
    # Safely update UI from keyboard thread
    if root is not None:
        root.after(0, update_ui_state)

def transliterate_word(english_word):
    if not english_word:
        return ""
        
    lower_word = english_word.lower()
    
    # Stage 1: Custom Override
    if lower_word in CUSTOM_EXCEPTIONS:
        return CUSTOM_EXCEPTIONS[lower_word]
        
    # Stage 2: Greedy Transliteration
    cyrillic = ""
    i = 0
    while i < len(lower_word):
        match_found = False
        # Try matching up to 4 characters (max length in MAPPING)
        for length in [4, 3, 2, 1]:
            if i + length <= len(lower_word):
                chunk = lower_word[i:i+length]
                if chunk in MAPPING:
                    cyrillic += MAPPING[chunk]
                    i += length
                    match_found = True
                    break
        if not match_found:
            # If no mapping, just keep the original character
            cyrillic += lower_word[i]
            i += 1
            
    # Stage 3: Orthographic Rules
    for pattern, replacement in ORTHOGRAPHIC_RULES:
        cyrillic = pattern.sub(replacement, cyrillic)
        
    return cyrillic

def on_key_event(event):
    global is_active, english_buffer, produced_cyrillic

    if not is_active:
        return True # Let key through

    # Check for modifier keys to allow native hotkeys like Ctrl+Z to work
    if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt') or keyboard.is_pressed('windows'):
        english_buffer = ""
        produced_cyrillic = ""
        return True

    name = event.name

    if name in ['space', 'enter', 'tab', 'backspace', '.', ',', '!', '?']:
        english_buffer = ""
        produced_cyrillic = ""
        return True

    # Process alphabetical keys and apostrophe.
    # We strictly check 'a'-'z' so we don't accidentally intercept Cyrillic letters we inject.
    if len(name) == 1 and (('a' <= name.lower() <= 'z') or name == "'"):
        if event.event_type != keyboard.KEY_DOWN:
            return False
            
        char = name.lower()
        is_upper = name.isupper()
        
        char_to_add = char.upper() if is_upper else char
        english_buffer += char_to_add
        
        new_cyrillic = transliterate_word(english_buffer)
        
        if english_buffer and english_buffer[0].isupper():
            if len(new_cyrillic) > 1:
                new_cyrillic = new_cyrillic[0].upper() + new_cyrillic[1:]
            else:
                new_cyrillic = new_cyrillic.upper()
                
        # Find common prefix length
        prefix_len = 0
        for i in range(min(len(produced_cyrillic), len(new_cyrillic))):
            if produced_cyrillic[i] == new_cyrillic[i]:
                prefix_len += 1
            else:
                break
                
        chars_to_delete = len(produced_cyrillic) - prefix_len
        if chars_to_delete > 0:
            for _ in range(chars_to_delete):
                keyboard.send('backspace')
                
        chars_to_add = new_cyrillic[prefix_len:]
        if chars_to_add:
            keyboard.write(chars_to_add)
            
        produced_cyrillic = new_cyrillic
            
        return False

    return True

# --- UI Methods ---
def update_ui_state():
    if is_active:
        dot_root.deiconify()
        status_label.config(text="🟢 Transliterator: ON", fg="lime")
        show_cheat_sheet()
    else:
        dot_root.withdraw()
        status_label.config(text="🔴 Transliterator: OFF", fg="red")
        hide_cheat_sheet()

def show_cheat_sheet():
    w = 250
    h = 320
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = sw - w - 40
    y = sh - h - 60
    root.geometry(f'{w}x{h}+{x}+{y}')
    root.deiconify()
    
    # Optional: Steal focus so that <FocusOut> reliably works. 
    # But this interrupts typing. As a compromise, we just show it.
    # If the user clicks on it and then away, it will hide.

def hide_cheat_sheet(event=None):
    root.withdraw()

latest_download_url = None
latest_version_tag = None

def show_update_wizard():
    if latest_version_tag is None:
        # If manually checked and no update logic triggered, or failed
        return
        
    wizard = tk.Toplevel(root)
    wizard.title("Update Available")
    wizard.geometry("420x220")
    wizard.configure(bg="#1e1e1e")
    wizard.attributes('-topmost', True)
    
    # Sleek UI design
    tk.Label(wizard, text=f"🚀 New Update Available! ({latest_version_tag})", font=("Segoe UI", 16, "bold"), bg="#1e1e1e", fg="lime").pack(pady=(20, 10))
    tk.Label(wizard, text="A new version of Phonetic Keyboard is ready to install.\nIt includes bug fixes and performance improvements.", font=("Segoe UI", 10), bg="#1e1e1e", fg="#cccccc", justify="center").pack(pady=10)
    
    btn_frame = tk.Frame(wizard, bg="#1e1e1e")
    btn_frame.pack(pady=20)
    
    def on_install():
        install_btn.config(text="Downloading...", state="disabled")
        wizard.update()
        
        def download_and_install():
            try:
                if getattr(sys, 'frozen', False):
                    current_exe = sys.executable
                else:
                    import webbrowser
                    webbrowser.open("https://github.com/xXxaccessionxXx/Phonetic-Keyboard/releases/latest")
                    os._exit(0)
                    
                exe_dir = os.path.dirname(current_exe)
                new_exe_path = os.path.join(exe_dir, "PhoneticKeyboard_new.exe")
                old_exe_path = os.path.join(exe_dir, "PhoneticKeyboard.old.exe")
                bat_path = os.path.join(exe_dir, "update.bat")
                
                urllib.request.urlretrieve(latest_download_url, new_exe_path)
                
                with open(bat_path, "w") as f:
                    f.write("@echo off\n")
                    f.write("timeout /t 2 /nobreak > NUL\n")
                    f.write(f"del /f /q \"{old_exe_path}\" 2>NUL\n")
                    f.write(f"move /y \"{current_exe}\" \"{old_exe_path}\"\n")
                    f.write(f"move /y \"{new_exe_path}\" \"{current_exe}\"\n")
                    f.write(f"start \"\" \"{current_exe}\"\n")
                    f.write("del \"%~f0\"\n")
                
                subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
                os._exit(0)
            except Exception as e:
                print(f"Install failed: {e}")
                wizard.destroy()

        threading.Thread(target=download_and_install, daemon=True).start()
        
    install_btn = tk.Button(btn_frame, text="Install Now", font=("Segoe UI", 10, "bold"), bg="lime", fg="black", activebackground="#32cd32", relief="flat", padx=15, pady=5, cursor="hand2", command=on_install)
    install_btn.pack(side="left", padx=10)
    
    cancel_btn = tk.Button(btn_frame, text="Later", font=("Segoe UI", 10), bg="#444444", fg="white", activebackground="#555555", relief="flat", padx=15, pady=5, cursor="hand2", command=wizard.destroy)
    cancel_btn.pack(side="left", padx=10)

def check_for_updates():
    global latest_download_url, latest_version_tag
    try:
        req = urllib.request.Request(REPO_API_URL, headers={'User-Agent': 'PhoneticKeyboardUpdater'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest_version_tag = data.get('tag_name')
            assets = data.get('assets', [])
            for asset in assets:
                if asset.get('name', '').endswith('.exe'):
                    latest_download_url = asset.get('browser_download_url')
                    break
                    
        if latest_version_tag and latest_version_tag != VERSION and latest_download_url:
            root.after(0, show_update_wizard)
    except Exception as e:
        print(f"Update check failed: {e}")

# --- System Tray ---
def create_image():
    image = Image.new('RGB', (64, 64), color=(30, 30, 30))
    dc = ImageDraw.Draw(image)
    dc.rectangle([16, 16, 48, 48], fill="lime")
    return image

def on_quit(icon, item):
    if icon:
        icon.stop()
    keyboard.unhook_all()
    os._exit(0)

def on_toggle(icon, item):
    toggle_active()

def on_show_ui(icon, item):
    root.after(0, show_cheat_sheet)

def setup_tray():
    global tray_icon
    image = create_image()
    menu = pystray.Menu(
        pystray.MenuItem('Show Cheat Sheet', on_show_ui),
        pystray.MenuItem('Check for Updates', lambda icon, item: root.after(0, show_update_wizard)),
        pystray.MenuItem('Toggle Keyboard', on_toggle),
        pystray.MenuItem('Exit', on_quit)
    )
    tray_icon = pystray.Icon("PhoneticKeyboard", image, "Phonetic Keyboard", menu)
    tray_icon.run_detached()

# --- Main App Initialization ---
def main():
    global root, dot_root, status_label
    
    # 1. Setup Tkinter Roots
    root = tk.Tk()
    root.title("Phonetic Keyboard Overlay")
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-alpha', 0.9)
    root.configure(bg='#2b2b2b')
    root.withdraw()

    root.bind('<FocusOut>', hide_cheat_sheet)

    # UI Content
    status_label = tk.Label(root, text="🔴 Transliterator: OFF", font=("Segoe UI", 12, "bold"), bg='#2b2b2b', fg="red")
    status_label.pack(pady=(15, 5))

    tk.Label(root, text="Cheat Sheet", font=("Segoe UI", 11, "underline"), bg='#2b2b2b', fg="white").pack(pady=(10, 5))

    cheat_text = (
        "shch = щ\n"
        "ts   = ц\n"
        "ya   = я\n"
        "yu   = ю\n"
        "zh   = ж\n"
        "ch   = ч\n"
        "sh   = ш\n"
        "ye   = е\n"
        "eh   = э\n"
        "bl   = ы\n"
        " '   = ь (soft sign)\n"
        " ''  = ъ (hard sign)\n"
    )
    
    tk.Label(root, text=cheat_text, font=("Consolas", 11), bg='#2b2b2b', fg="#cccccc", justify="left").pack(padx=20, pady=5)
    
    tk.Label(root, text="Hotkey: F9 to toggle", font=("Segoe UI", 9, "italic"), bg='#2b2b2b', fg="#888888").pack(side="bottom", pady=10)

    # Dot window
    dot_root = tk.Toplevel(root)
    dot_root.overrideredirect(True)
    dot_root.attributes('-topmost', True)
    dot_root.attributes('-transparentcolor', 'black')
    dot_root.configure(bg='black')
    
    dot_canvas = tk.Canvas(dot_root, width=12, height=12, bg='black', highlightthickness=0)
    dot_canvas.pack()
    dot_canvas.create_oval(1, 1, 11, 11, fill='lime', outline='#00ff00')
    dot_root.geometry(f"+{root.winfo_screenwidth() - 25}+{root.winfo_screenheight() - 55}")
    dot_root.withdraw()

    # 2. Setup Hooks
    keyboard.add_hotkey('f9', toggle_active)
    keyboard.add_hotkey('ctrl+esc', lambda: on_quit(tray_icon, None))
    keyboard.hook(on_key_event, suppress=True)

    # Start update checker in background
    threading.Thread(target=check_for_updates, daemon=True).start()

    # 3. Start Tray
    setup_tray()

    # 4. Start Mainloop
    root.mainloop()

if __name__ == '__main__':
    main()
