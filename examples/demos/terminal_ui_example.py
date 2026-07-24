import asyncio
from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import HSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import Frame, TextArea, Label
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

# --- Timer State ---
timer_state = {
    "seconds": 0,
    "running": False,
    "paused": False
}

# --- Key Bindings ---
kb = KeyBindings()

@kb.add('c-c')
@kb.add('q')
def exit_(event):
    """Exit the application."""
    event.app.exit()

# --- UI Components & Logic ---
def get_title_text():
    return [('class:title', ' Microdrop Terminal UI v2.0 ')]

def get_status_text():
    ts = timer_state["seconds"]
    mins, secs = divmod(ts, 60)
    timer_display = f"{mins:02d}:{secs:02d}"
    
    if not timer_state["running"]:
        status = "STOPPED"
    elif timer_state["paused"]:
        status = "PAUSED"
    else:
        status = "RUNNING"
        
    return [
        ('class:status', f' Status: Idle | Device: MockDropBot | Timer: [{status}] {timer_display} ')
    ]

title_window = Window(
    content=FormattedTextControl(get_title_text),
    height=1,
    align=WindowAlign.CENTER,
    style='class:title-bar'
)

status_bar = Window(
    content=FormattedTextControl(get_status_text),
    height=1,
    style='class:status-bar'
)

output_area = TextArea(
    text="Welcome to Microdrop TUI\nType 'help' for commands.\nReady...",
    read_only=True,
    scrollbar=True
)

command_input = TextArea(
    height=1,
    prompt='microdrop> ',
    multiline=False,
    wrap_lines=False
)

def accept_command(buffer):
    """Handle command entry."""
    full_cmd = command_input.text.strip().lower()
    if not full_cmd:
        return

    output_area.text += f"\n> {full_cmd}"
    parts = full_cmd.split()
    cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []

    if cmd == "help":
        output_area.text += "\nAvailable commands:\n  timer start  - Start/Resume the timer\n  timer pause  - Pause the timer\n  timer stop   - Stop and reset timer\n  timer reset  - Reset timer to 0\n  clear        - Clear logs\n  exit/q       - Quit application"
    
    elif cmd == "timer":
        sub = args[0] if args else ""
        if sub == "start":
            timer_state["running"] = True
            timer_state["paused"] = False
            output_area.text += "\n[Timer] Started."
        elif sub == "pause":
            timer_state["paused"] = True
            output_area.text += "\n[Timer] Paused."
        elif sub == "stop":
            timer_state["running"] = False
            timer_state["paused"] = False
            timer_state["seconds"] = 0
            output_area.text += "\n[Timer] Stopped and reset."
        elif sub == "reset":
            timer_state["seconds"] = 0
            output_area.text += "\n[Timer] Reset to 0."
        else:
            output_area.text += f"\n[Error] Unknown timer command: {sub}"
            
    elif cmd == "clear":
        output_area.text = "Output cleared."
    elif cmd in ("exit", "quit"):
        Application.get_current().exit()
    else:
        output_area.text += f"\n[Error] Unknown command: {cmd}"
        
    command_input.text = ""

command_input.accept_handler = accept_command

# --- Layout Definition ---
root_container = HSplit([
    title_window,
    Frame(output_area, title="Logs/Output"),
    status_bar,
    Frame(command_input, title="Command Input"),
    Label(text=" (Press 'q' or Ctrl-C to exit) ", style='class:footer')
])

# --- Styling ---
style = Style.from_dict({
    'title-bar': 'bg:#4444ff #ffffff bold',
    'status-bar': 'bg:#222222 #00ff00',
    'title': 'bold',
    'status': 'italic',
    'footer': '#888888',
    'frame.border': '#555555',
})

layout = Layout(root_container, focused_element=command_input)

# --- Background Task ---
async def timer_counter(app):
    """Background task to increment the timer every second."""
    while True:
        await asyncio.sleep(1)
        if timer_state["running"] and not timer_state["paused"]:
            timer_state["seconds"] += 1
            # Trigger a redraw of the UI
            app.invalidate()

# --- Application Entry Point ---
async def main():
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True
    )
    
    # Start background timer task
    timer_task = asyncio.create_task(timer_counter(app))
    
    try:
        await app.run_async()
    finally:
        timer_task.cancel()

if __name__ == '__main__':
    print("Starting Terminal UI...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
