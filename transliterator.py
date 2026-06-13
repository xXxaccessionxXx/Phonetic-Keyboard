import keyboard
import sys
import os
import threading
import time
import tkinter as tk
import pystray
from PIL import Image, ImageDraw
import re
import urllib.request
import json
import subprocess

VERSION = "v1.2.2"
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
is_game_mode = False
is_chat_active = False
english_buffer = ""
produced_cyrillic = ""
pressed_keys = set()

def delayed_injection(chars_to_delete, chars_to_add):
    time.sleep(0.01)
    if chars_to_delete > 0:
        for _ in range(chars_to_delete):
            keyboard.send('backspace')
    if chars_to_add:
        keyboard.write(chars_to_add)

# UI Globals
root = None
dot_root = None
status_label = None
tray_icon = None

def toggle_active():
    global is_active, english_buffer, produced_cyrillic, pressed_keys, is_chat_active
    is_active = not is_active
    english_buffer = ""
    produced_cyrillic = ""
    pressed_keys.clear()
    is_chat_active = False
    
    # Safely update UI from keyboard thread
    if root is not None:
        root.after(0, update_ui_state)

def toggle_game_mode():
    global is_game_mode, is_chat_active, english_buffer, produced_cyrillic, pressed_keys
    is_game_mode = not is_game_mode
    is_chat_active = False
    english_buffer = ""
    produced_cyrillic = ""
    pressed_keys.clear()
    
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
    global is_active, is_game_mode, is_chat_active, english_buffer, produced_cyrillic, pressed_keys

    if not is_active:
        return True # Let key through

    name = event.name

    if is_game_mode:
        if name in ['enter', 'esc', '/']:
            if event.event_type == keyboard.KEY_DOWN and name not in pressed_keys:
                if name == 'enter':
                    is_chat_active = not is_chat_active
                elif name == 'esc':
                    is_chat_active = False
                elif name == '/':
                    is_chat_active = True
                    
            if event.event_type == keyboard.KEY_DOWN:
                pressed_keys.add(name)
            else:
                pressed_keys.discard(name)
                
            english_buffer = ""
            produced_cyrillic = ""
            if root is not None:
                root.after(0, update_ui_state)
            return True
            
        if not is_chat_active:
            return True

    # Check for modifier keys to allow native hotkeys like Ctrl+Z to work
    if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt') or keyboard.is_pressed('windows'):
        english_buffer = ""
        produced_cyrillic = ""
        return True

    if name in ['space', 'enter', 'tab', 'backspace', '.', ',', '!', '?']:
        english_buffer = ""
        produced_cyrillic = ""
        return True

    # Process alphabetical keys and apostrophe.
    # We strictly check 'a'-'z' so we don't accidentally intercept Cyrillic letters we inject.
    if len(name) == 1 and (('a' <= name.lower() <= 'z') or name == "'"):
        if event.event_type != keyboard.KEY_DOWN:
            pressed_keys.discard(name)
            return True
            
        if name in pressed_keys:
            return True
        pressed_keys.add(name)
        
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
                
        chars_to_delete = len(produced_cyrillic) - prefix_len + 1
        chars_to_add = new_cyrillic[prefix_len:]
        
        threading.Thread(target=delayed_injection, args=(chars_to_delete, chars_to_add), daemon=True).start()
            
        produced_cyrillic = new_cyrillic
            
        return True

    return True

# --- UI Methods ---
is_cheat_sheet_visible = False

def update_ui_state():
    if is_active:
        dot_root.deiconify()
        if is_game_mode:
            state_text = "🟢 Game Mode: " + ("CHAT ACTIVE" if is_chat_active else "IDLE")
            color = "#3fb950" if is_chat_active else "#58a6ff"
            status_label.config(text=state_text, fg=color)
        else:
            status_label.config(text="🟢 Transliterator: ON", fg="#3fb950")
    else:
        dot_root.withdraw()
        if is_game_mode:
            status_label.config(text="🔴 Game Mode: OFF", fg="#ff7b72")
        else:
            status_label.config(text="🔴 Transliterator: OFF", fg="#ff7b72")

def toggle_cheat_sheet():
    global is_cheat_sheet_visible
    is_cheat_sheet_visible = not is_cheat_sheet_visible
    if root is not None:
        if is_cheat_sheet_visible:
            root.after(0, root.deiconify)
        else:
            root.after(0, root.withdraw)

latest_download_url = None
latest_version_tag = None
latest_release_notes = ""

def parse_ver(v):
    return [int(x) for x in re.findall(r'\d+', str(v))]

def show_update_wizard():
    if latest_version_tag is None:
        # If manually checked and no update logic triggered, or failed
        return
        
    current_ver = parse_ver(VERSION)
    fetched_ver = parse_ver(latest_version_tag)
    is_new_update = fetched_ver > current_ver and latest_download_url
        
    wizard = tk.Toplevel(root)
    wizard.title("Phonetic Keyboard Updater")
    wizard.configure(bg="#0d1117")
    wizard.attributes('-topmost', True)
    
    # Window persistence
    config_path = "updater_config.json"
    w, h = (500, 420) if is_new_update else (350, 180)
    pos = ""
    try:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                conf = json.load(f)
                x, y = conf.get("x"), conf.get("y")
                if x is not None and y is not None:
                    pos = f"+{x}+{y}"
    except Exception:
        pass
        
    wizard.geometry(f"{w}x{h}{pos}")
    
    def on_close():
        try:
            with open(config_path, "w") as f:
                json.dump({"x": wizard.winfo_x(), "y": wizard.winfo_y()}, f)
        except Exception:
            pass
        wizard.destroy()
        
    wizard.protocol("WM_DELETE_WINDOW", on_close)
    
    if not is_new_update:
        tk.Label(wizard, text="✅ Up to Date", font=("Segoe UI", 16, "bold"), bg="#0d1117", fg="#3fb950").pack(pady=(35, 10))
        tk.Label(wizard, text=f"You are running the latest version ({VERSION}).", font=("Segoe UI", 11), bg="#0d1117", fg="#c9d1d9").pack(pady=5)
        tk.Button(wizard, text="Awesome!", font=("Segoe UI", 10, "bold"), bg="#21262d", fg="#c9d1d9", activebackground="#30363d", activeforeground="white", relief="flat", padx=25, pady=8, cursor="hand2", command=on_close).pack(pady=15)
        return
    
    # --- Sleek UI design ---
    header_frame = tk.Frame(wizard, bg="#0d1117")
    header_frame.pack(fill="x", pady=(20, 10))
    
    tk.Label(header_frame, text="✨ Update Available", font=("Segoe UI", 18, "bold"), bg="#0d1117", fg="#58a6ff").pack()
    tk.Label(header_frame, text=f"Version {latest_version_tag} is ready to be installed.", font=("Segoe UI", 11), bg="#0d1117", fg="#8b949e").pack(pady=2)
    
    # Pack the buttons AT THE BOTTOM first
    btn_frame = tk.Frame(wizard, bg="#0d1117")
    btn_frame.pack(side="bottom", fill="x", pady=20)
    
    btn_inner = tk.Frame(btn_frame, bg="#0d1117")
    btn_inner.pack(anchor="center")
    
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
                    f.write("set _MEIPASS2=\n")
                    f.write("set _MEIPASS=\n")
                    f.write(f"start \"\" \"{current_exe}\"\n")
                    f.write("del \"%~f0\"\n")
                
                # Strip PyInstaller env vars from the subprocess environment just to be safe
                env = os.environ.copy()
                env.pop('_MEIPASS2', None)
                env.pop('_MEIPASS', None)
                
                subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=subprocess.CREATE_NO_WINDOW, env=env)
                os._exit(0)
            except Exception as e:
                print(f"Install failed: {e}")
                on_close()

        threading.Thread(target=download_and_install, daemon=True).start()
        
    cancel_btn = tk.Button(btn_inner, text="Not Now", font=("Segoe UI", 10, "bold"), bg="#21262d", fg="#c9d1d9", activebackground="#30363d", activeforeground="white", relief="flat", padx=20, pady=8, cursor="hand2", command=on_close)
    cancel_btn.pack(side="left", padx=10)
    
    install_btn = tk.Button(btn_inner, text="Install Update", font=("Segoe UI", 10, "bold"), bg="#238636", fg="white", activebackground="#2ea043", activeforeground="white", relief="flat", padx=20, pady=8, cursor="hand2", command=on_install)
    install_btn.pack(side="left", padx=10)

    # Release Notes frame packed with expand=True, so it takes the REMAINING space
    content_frame = tk.Frame(wizard, bg="#0d1117")
    content_frame.pack(fill="both", expand=True, padx=25, pady=0)
    
    tk.Label(content_frame, text="What's new:", font=("Segoe UI", 10, "bold"), bg="#0d1117", fg="#c9d1d9").pack(anchor="w", pady=(0, 5))
    
    text_container = tk.Frame(content_frame, bg="#161b22", highlightbackground="#30363d", highlightthickness=1)
    text_container.pack(fill="both", expand=True)
    
    notes_text = tk.Text(text_container, font=("Consolas", 10), bg="#161b22", fg="#c9d1d9", wrap="word", relief="flat", padx=10, pady=10)
    notes_text.insert("1.0", latest_release_notes)
    notes_text.config(state="disabled")
    notes_text.pack(side="left", fill="both", expand=True)
    
    scrollbar = tk.Scrollbar(text_container, command=notes_text.yview, bg="#161b22", troughcolor="#0d1117")
    notes_text.config(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")

def check_for_updates():
    global latest_download_url, latest_version_tag, latest_release_notes
    try:
        req = urllib.request.Request(REPO_API_URL, headers={'User-Agent': 'PhoneticKeyboardUpdater'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest_version_tag = data.get('tag_name')
            latest_release_notes = data.get('body', 'No release notes provided.')
            assets = data.get('assets', [])
            for asset in assets:
                if asset.get('name', '').endswith('.exe'):
                    latest_download_url = asset.get('browser_download_url')
                    break
                    
        current_ver = parse_ver(VERSION)
        fetched_ver = parse_ver(latest_version_tag)
        
        if fetched_ver > current_ver and latest_download_url:
            root.after(0, show_update_wizard)
    except Exception as e:
        print(f"Update check failed: {e}")

# --- System Tray ---
def create_image():
    image = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # A clean green circle matching the ON state color
    dc.ellipse([12, 12, 52, 52], fill="#3fb950")
    return image

def on_quit(icon, item):
    if icon:
        icon.stop()
    keyboard.unhook_all()
    os._exit(0)

def on_toggle(icon, item):
    toggle_active()

def on_toggle_ui(icon, item):
    toggle_cheat_sheet()

def setup_tray():
    global tray_icon
    image = create_image()
    menu = pystray.Menu(
        pystray.MenuItem('Toggle Cheat Sheet', on_toggle_ui),
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
    root.attributes('-alpha', 0.95)
    root.configure(bg='#0d1117')
    
    w = 280
    h = 400
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = sw - w - 40
    y = sh - h - 60
    root.geometry(f'{w}x{h}+{x}+{y}')
    root.withdraw()

    # Custom Header for dragging
    header_frame = tk.Frame(root, bg="#161b22", cursor="fleur")
    header_frame.pack(fill="x")
    
    title_label = tk.Label(header_frame, text="Phonetic Keyboard", font=("Segoe UI", 10, "bold"), bg="#161b22", fg="#c9d1d9")
    title_label.pack(side="left", padx=10, pady=5)
    
    close_btn = tk.Label(header_frame, text="✕", font=("Segoe UI", 10, "bold"), bg="#161b22", fg="#8b949e", cursor="hand2")
    close_btn.pack(side="right", padx=10)
    close_btn.bind("<Button-1>", lambda e: toggle_cheat_sheet())
    
    def start_move(event):
        root.x = event.x
        root.y = event.y

    def do_move(event):
        deltax = event.x - root.x
        deltay = event.y - root.y
        x = root.winfo_x() + deltax
        y = root.winfo_y() + deltay
        root.geometry(f"+{x}+{y}")

    header_frame.bind("<ButtonPress-1>", start_move)
    header_frame.bind("<B1-Motion>", do_move)
    title_label.bind("<ButtonPress-1>", start_move)
    title_label.bind("<B1-Motion>", do_move)

    # UI Content
    content_frame = tk.Frame(root, bg="#0d1117")
    content_frame.pack(fill="both", expand=True, padx=15, pady=5)
    
    status_label = tk.Label(content_frame, text="🔴 Transliterator: OFF", font=("Segoe UI", 12, "bold"), bg='#0d1117', fg="#ff7b72")
    status_label.pack(pady=(5, 10))

    tk.Label(content_frame, text="Cheat Sheet", font=("Segoe UI", 11, "bold"), bg='#0d1117', fg="#58a6ff").pack(anchor="w", pady=(0, 5))
    
    cheat_container = tk.Frame(content_frame, bg="#21262d", highlightthickness=1, highlightbackground="#30363d")
    cheat_container.pack(fill="both", expand=True)

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
    
    tk.Label(cheat_container, text=cheat_text, font=("Consolas", 11), bg='#21262d', fg="#e6edf3", justify="left").pack(padx=15, pady=10)
    
    footer_frame = tk.Frame(root, bg="#0d1117")
    footer_frame.pack(fill="x", side="bottom", pady=10)
    tk.Label(footer_frame, text="F8: Game Mode | F9: ON/OFF | F10: Toggle UI", font=("Segoe UI", 9, "italic"), bg='#0d1117', fg="#8b949e").pack()

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
    keyboard.add_hotkey('f8', toggle_game_mode)
    keyboard.add_hotkey('f9', toggle_active)
    keyboard.add_hotkey('f10', toggle_cheat_sheet)
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
