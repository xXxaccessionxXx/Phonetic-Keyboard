import keyboard
import time

def on_key(event):
    if event.name == 'a' and event.event_type == keyboard.KEY_DOWN:
        keyboard.send('backspace')
        keyboard.write('x')
        return True
    return True

keyboard.hook(on_key, suppress=True)
print("Press 'a', should print 'x'. Press 'q' to quit.")
keyboard.wait('q')
