"""Robot Voice Study V6 - full-screen emoji and minimal glass-inspired questionnaire.
Requires: pip install pyserial pygame
Pico runs saved main.py, sending BUTTON_A/B/C over USB CDC serial.
Keyboard A/B/C is available for software testing (no Pico required).
"""
import csv
import itertools
import math
import queue
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import pygame
import serial
from serial.tools import list_ports

PORT = "COM7"
BAUD = 115200
BASE = Path(__file__).resolve().parent
AUDIO_DIR = BASE / "Audio_Files"
DATA_DIR = BASE / "Research_Data"
RESULTS = DATA_DIR / "voice_ratings_v9_study.csv"
ROUNDS = [
    ("Welcome", "Pitch", ("W_P1", "W_V0", "W_P2")),
    ("Welcome", "Loudness", ("W_L1", "W_V0", "W_L2")),
    ("Welcome", "Intonation", ("W_I1", "W_V0", "W_I2")),
    ("Wayfinding", "Pitch", ("D_P1", "D_V0", "D_P2")),
    ("Wayfinding", "Loudness", ("D_L1", "D_V0", "D_L2")),
    ("Wayfinding", "Intonation", ("D_I1", "D_V0", "D_I2")),
]
QUESTIONS = ("Naturalness", "Appropriateness", "Comfort")
FIELDS = ("session_id", "timestamp", "round", "task", "parameter", "button",
          "audio_code", "naturalness", "appropriateness", "comfort", "clarity",
          "preferred", "replay_count", "participant_number", "task_order", "parameter_order", "voice_position_order")
BG = "#F4F7FD"
CARD = "#FFFFFF"
INK = "#233350"
MUTED = "#697C98"
BLUE = "#4385EC"
FACE_BG = "#090C13"
FACE_CYAN = "#83EBF5"
FACE_PINK = "#F7A7C6"

class VoiceStudy:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Robot Voice Study - V7 Touch Pilot")
        self.root.geometry("800x480")
        self.root.minsize(760, 450)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.session = uuid.uuid4().hex[:8]
        self.index = 0
        self.rounds = list(ROUNDS)
        self.participant_number = 0
        self.task_order = ""
        self.parameter_order = ""
        self.mode = "start"
        self.sounds = {}
        self.finished = set()
        self.current_voice = None
        self.replays = {v: 0 for v in "ABC"}
        self.rating_vars = {}
        self.rating_touched = set()
        self.active_rating_voice = "A"
        self.rating_labels = {}
        self.preference_buttons = {}
        self.rating_buttons = {}
        self.preference = None
        self.port_choice = tk.StringVar(value=PORT)
        self.port_menu = None
        self.channel = None
        self.audio_ready = False
        self.ser = None
        self.running = True
        self.messages = queue.Queue()
        self.serial_state = "Not connected"
        self.raw_count = 0
        self.screen_status = None
        self.port_status = None
        self.debug_status = None
        self.connect_button = None
        self.face_canvas = None
        self.face_start = time.monotonic()
        self._init_audio()
        self.show_start()
        self.root.bind("<KeyPress>", self.on_key)
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.root.after(70, self.tick)

    def _init_audio(self):
        try:
            pygame.mixer.init()
            self.channel = pygame.mixer.Channel(0)
            self.audio_ready = True
        except pygame.error as exc:
            self.audio_ready = False
            messagebox.showerror("Audio error", str(exc))

    def connect(self):
        if self.ser is not None:
            return
        try:
            port = self.port_choice.get().strip() or PORT
            self.ser = serial.Serial(port, BAUD, timeout=0.25)
            self.serial_state = f"Connected: {port}"
            # Do not send Ctrl+C, Ctrl+D, or exec(main.py): Pico already boots on its own.
            # The reader thread receives full lines without blocking the GUI.
            threading.Thread(target=self.serial_reader, args=(self.ser,), daemon=True).start()
            print(f"[SERIAL] Connected to {port}", flush=True)
        except (serial.SerialException, OSError) as exc:
            self.serial_state = f"Unavailable: {self.port_choice.get()}"
            print(f"[SERIAL] {exc}", flush=True)
            messagebox.showwarning("Pico not connected",
                f"Cannot open {self.port_choice.get()}. If Access denied, close all other serial tools and Python processes.\nYou can still test with keyboard A/B/C.\n\n{exc}")
        self.update_diagnostics()

    def refresh_ports(self):
        ports = list(list_ports.comports())
        choices = [p.device for p in ports]
        if not choices:
            choices = [PORT]
        pico_ports = [p.device for p in ports if p.vid == 0x2E8A]
        if self.ser is None and pico_ports:
            self.port_choice.set(pico_ports[0])
        elif self.port_choice.get() not in choices and self.ser is None:
            self.port_choice.set(choices[0])
        if self.port_menu is not None and self.port_menu.winfo_exists():
            self.port_menu.configure(values=choices)
        print("[PORTS]", [(p.device, p.description) for p in ports], flush=True)

    def serial_reader(self, connection):
        # A read-only daemon: tkinter updates happen in tick(), on the main thread.
        try:
            while self.running and self.ser is connection:
                line = connection.readline()
                if line:
                    message = line.decode("utf-8", errors="replace").strip()
                    if message:
                        self.messages.put(("line", message))
        except (serial.SerialException, OSError) as exc:
            if self.running and self.ser is connection:
                self.messages.put(("error", str(exc)))

    def disconnect(self):
        old = self.ser
        self.ser = None
        if old is not None:
            try:
                old.close()
            except (OSError, serial.SerialException):
                pass
        self.serial_state = "Not connected"
        self.update_diagnostics()

    def clear(self):
        self.face_canvas = None
        for child in self.root.winfo_children():
            child.destroy()
        titlebar = tk.Frame(self.root, bg=BG)
        titlebar.pack(fill="x", padx=28, pady=(12, 0))
        self.port_status = tk.Label(titlebar, bg=BG, fg="#455568", font=("Arial", 10))
        self.port_status.pack(side="left")
        self.debug_status = tk.Label(titlebar, bg=BG, fg="#455568", font=("Arial", 10))
        self.debug_status.pack(side="right")
        self.update_diagnostics()

    def update_diagnostics(self):
        if self.port_status is not None and self.port_status.winfo_exists():
            self.port_status.config(text=f"Pico: {self.serial_state}  |  Keyboard test: A/B/C")
        if self.debug_status is not None and self.debug_status.winfo_exists():
            self.debug_status.config(text=f"Serial lines received: {self.raw_count}")

    def title(self, value):
        tk.Label(self.root, text=value, bg=BG, font=("Arial", 23, "bold")).pack(pady=(24, 12))

    def text(self, value, size=15, pady=8):
        tk.Label(self.root, text=value, bg=BG, font=("Arial", size),
                 justify="center", wraplength=850).pack(pady=pady)

    def show_start(self):
        self.mode = "start"
        self.clear()
        self.title("Robot Voice Study")
        self.text("Six short rounds: Welcome and Wayfinding")
        self.text("Each round: listen to A, B, C, then complete a short evaluation.", 14)
        self.text("Use the physical buttons, or A/B/C on the keyboard for software testing.", 12)
        port_row = tk.Frame(self.root, bg=BG)
        port_row.pack(pady=8)
        tk.Label(port_row, text="Pico port:", bg=BG).pack(side="left", padx=5)
        self.port_menu = ttk.Combobox(port_row, textvariable=self.port_choice, width=10)
        self.port_menu.pack(side="left", padx=5)
        tk.Button(port_row, text="Refresh ports", command=self.refresh_ports).pack(side="left", padx=5)
        tk.Button(self.root, text="Connect Pico", command=self.connect,
                  font=("Arial", 14), padx=18, pady=8).pack(pady=7)
        self.refresh_ports()
        tk.Button(self.root, text="Start Study", command=self.start,
                  font=("Arial", 16, "bold"), bg="#D9E9F4", padx=36, pady=13).pack(pady=15)
        self.text("Pilot only: keyboard inputs are for testing, not participant data collection.", 11)

    def audio_file(self, task, code):
        for ext in (".wav", ".mp3"):
            candidate = AUDIO_DIR / task / (code + ext)
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(f"Missing {task}/{code}.wav or .mp3")

    def load_round(self):
        if not self.audio_ready:
            raise RuntimeError("Audio mixer did not initialise")
        task, parameter, codes = self.rounds[self.index]
        new_sounds = {}
        for letter, code in zip("ABC", codes):
            new_sounds[letter] = pygame.mixer.Sound(str(self.audio_file(task, code)))
        self.sounds = new_sounds
        self.channel.stop()
        self.current_voice = None
        self.finished = set()
        self.replays = {v: 0 for v in "ABC"}
        print(f"[ROUND] {self.index+1}/6 {task} / {parameter}", flush=True)

    def start(self):
        try:
            self.load_round()
        except (OSError, pygame.error, RuntimeError) as exc:
            messagebox.showerror("Unable to load round", str(exc))
            return
        self.show_listening()

    def show_listening(self):
        self.mode = "listening"
        self.clear()
        self.title(f"Round {self.index+1} / 6")
        self.text("Press physical buttons A, B and C to listen to each voice.", 13, 3)
        self.face_canvas = tk.Canvas(self.root, bg=FACE_BG, highlightthickness=0,
                                     height=310)
        self.face_canvas.pack(fill="x", padx=55, pady=(10, 8))
        self.screen_status = tk.Label(self.root, bg=BG, font=("Arial", 16),
                                      text="Completed: none / A, B, C")
        self.screen_status.pack(pady=16)
        tk.Button(self.root, text="Connect / Reconnect Pico", command=self.reconnect,
                  font=("Arial", 11)).pack(pady=5)
        self.text("Pilot: keyboard A/B/C is also available for software testing.", 10)
        self.draw_face()

    def draw_face(self):
        """Smooth V3 face; same visuals for all six rounds and voice variants."""
        c = self.face_canvas
        if self.mode != "listening" or c is None or not c.winfo_exists():
            return
        c.delete("all")
        w = max(c.winfo_width(), 1)
        h = max(c.winfo_height(), 1)
        scale = min(w / 880, h / 390)
        cx, cy = w / 2, h / 2 - 16 * scale
        t = time.monotonic() - self.face_start
        speaking = self.current_voice is not None and self.channel.get_busy()
        phase = t % 4.5
        blink = max(0.10, abs(phase-0.11)/0.11) if phase < 0.22 else 1.0
        shift = (1.2 * math.sin(t*3.5) if speaking else 0) * scale
        eye_color = FACE_CYAN if not speaking or math.sin(t*5) > -0.75 else "#9CF4FB"
        for dx in (-113, 113):
            x, y = cx + dx*scale, cy - 25*scale + shift
            ew, eh = 48*scale, 70*scale*blink
            c.create_oval(x-ew/2, y-eh/2, x+ew/2, y+eh/2,
                          fill=eye_color, outline="")
        for dx in (-195, 195):
            x, y = cx+dx*scale, cy+42*scale
            c.create_oval(x-26*scale, y-12*scale, x+26*scale, y+12*scale,
                          fill=FACE_PINK, outline="")
        mouth = [cx-24*scale,cy+25*scale, cx-23*scale,cy+43*scale,
                 cx-11*scale,cy+48*scale, cx,cy+34*scale,
                 cx+11*scale,cy+48*scale, cx+23*scale,cy+43*scale,
                 cx+24*scale,cy+25*scale]
        c.create_line(*mouth, fill=FACE_CYAN, width=max(2,5*scale),
                      smooth=True, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        if speaking:
            for sx in (-1, 1):
                x, y = cx + sx*275*scale, cy - 100*scale
                c.create_line(x,y,x+sx*10*scale,y-12*scale,
                              fill=FACE_CYAN, width=max(2,4*scale), capstyle=tk.ROUND)
                c.create_line(x+sx*16*scale,y+12*scale,
                              x+sx*30*scale,y+6*scale,
                              fill=FACE_CYAN, width=max(2,4*scale), capstyle=tk.ROUND)
        c.create_text(cx, h-25*scale,
                      text="Speaking..." if speaking else "Ready to help",
                      fill="#E8FAFF", font=("Arial", max(10,int(16*scale))))

    def reconnect(self):
        self.disconnect()
        self.connect()

    def play(self, letter, replay=False):
        if self.mode not in ("listening", "questionnaire"):
            return
        if letter not in self.sounds or self.channel.get_busy():
            return
        if self.mode == "questionnaire":
            self.replays[letter] += 1
        self.channel.play(self.sounds[letter])
        self.current_voice = letter
        print(f"[PLAY] {letter} (round {self.index+1})", flush=True)
        if self.mode == "listening" and self.screen_status is not None:
            self.screen_status.config(text=f"Playing {letter} ...  Completed: " +
                                      (", ".join(sorted(self.finished)) or "none"))

    def on_key(self, event):
        # Available only for desktop debugging. Prevent keyboard triggers while answering questions.
        if self.mode != "listening" or isinstance(event.widget, (ttk.Combobox, tk.Entry)):
            return
        letter = (event.char or "").upper()
        if letter in "ABC":
            self.play(letter)

    def tick(self):
        if not self.running:
            return
        try:
            for _ in range(100):
                try:
                    kind, content = self.messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "error":
                    print("[SERIAL ERROR]", content, flush=True)
                    self.disconnect()
                    messagebox.showwarning("Serial connection lost", content)
                    continue
                self.raw_count += 1
                print(f"[RECEIVED] {content!r}", flush=True)
                self.update_diagnostics()
                if self.mode == "listening" and content in ("BUTTON_A", "BUTTON_B", "BUTTON_C"):
                    self.play(content[-1])
            if self.current_voice is not None and not self.channel.get_busy():
                if self.mode == "listening":
                    self.finished.add(self.current_voice)
                    print(f"[COMPLETE] {self.current_voice}", flush=True)
                    self.screen_status.config(text="Completed: " + ", ".join(sorted(self.finished)) + " / A, B, C")
                    if self.finished == set("ABC"):
                        self.current_voice = None
                        self.show_questionnaire()
                self.current_voice = None
            self.draw_face()
        except (OSError, pygame.error) as exc:
            print("[ERROR]", repr(exc), flush=True)
            messagebox.showerror("Runtime error", str(exc))
        self.root.after(70, self.tick)

    def toggle_fullscreen(self):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    def exit_fullscreen(self):
        self.root.attributes("-fullscreen", False)

    def pill_button(self, parent, label, command, active=False, width=14):
        return tk.Button(parent, text=label, command=command,
                         bg=BLUE if active else "#EAF0FA",
                         fg="white" if active else INK,
                         activebackground="#3172D7", activeforeground="white",
                         relief="flat", bd=0, cursor="hand2", padx=14, pady=10,
                         font=("Arial", 12, "bold"), width=width)

    def show_questionnaire(self):
        # Ratings are created once and preserved when switching A/B/C tabs.
        self.mode = "questionnaire"
        self.rating_vars = {(v,q): tk.IntVar(value=4) for v in "ABC" for q in QUESTIONS}
        self.rating_touched = set()
        self.active_rating_voice = "A"
        self.preference = tk.StringVar(value="")
        self.render_questionnaire()

    def render_questionnaire(self):
        self.clear()
        task, parameter, _ = self.rounds[self.index]
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=42, pady=(14, 14))
        tk.Label(header, text="Robot Voice Study", bg=BG, fg=INK,
                 font=("Arial", 22, "bold")).pack(side="left")
        tk.Label(header, text=f"Round {self.index+1} / 6   •   {task}",
                 bg=BG, fg=MUTED, font=("Arial", 14)).pack(side="right")

        pane = tk.Frame(self.root, bg=CARD, highlightbackground="#DFE7F5",
                        highlightthickness=1, padx=28, pady=18)
        pane.pack(fill="both", expand=True, padx=42, pady=(0, 12))
        tk.Label(pane, text="Voice Evaluation", bg=CARD, fg=INK,
                 font=("Arial", 20, "bold")).pack(anchor="w")
        tk.Label(pane, text="Rate each voice for this task. Select A, B or C to switch voices.",
                 bg=CARD, fg=MUTED, font=("Arial", 11)).pack(anchor="w", pady=(3, 12))

        tabs = tk.Frame(pane, bg=CARD)
        tabs.pack(fill="x", pady=(0, 12))
        self.rating_buttons = {}
        for v in "ABC":
            b = self.pill_button(tabs, f"Voice {v}", lambda x=v: self.select_rating_voice(x),
                                 active=(v == self.active_rating_voice), width=13)
            b.pack(side="left", padx=(0, 10))
            self.rating_buttons[v] = b

        self.rating_panel = tk.Frame(pane, bg="#F7F9FD", padx=24, pady=15)
        self.rating_panel.pack(fill="x")
        self.render_rating_sliders()

        lower = tk.Frame(pane, bg=CARD)
        lower.pack(fill="x", pady=(14, 4))
        tk.Label(lower, text="Which voice would you prefer for this task?",
                 bg=CARD, fg=INK, font=("Arial", 13, "bold")).pack(anchor="w", pady=(0, 7))
        options = tk.Frame(lower, bg=CARD)
        options.pack(anchor="w")
        self.preference_buttons = {}
        for v in "ABC":
            canvas = tk.Canvas(options, width=150, height=54, bg=CARD,
                               bd=0, highlightthickness=0, cursor="hand2")
            canvas.pack(side="left", padx=(0, 12))
            canvas.bind("<Button-1>", lambda event, choice=v: self.choose_preference(choice))
            self.preference_buttons[v] = canvas
        self.draw_preferences()

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=42, pady=(3, 17))
        self.pill_button(footer, "Replay selected voice", self.replay_selected, width=21).pack(side="left")
        tk.Button(footer, text="Submit & Continue  →", command=self.submit,
                  font=("Arial", 14, "bold"), bg=BLUE, fg="white",
                  activebackground="#3273D7", activeforeground="white",
                  padx=28, pady=12, relief="flat", cursor="hand2").pack(side="right")
        tk.Label(footer, text="1 = low     7 = high  •  All 9 ratings require a deliberate selection",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(side="right", padx=18)

    @staticmethod
    def rounded_rect(canvas, x1, y1, x2, y2, radius, fill, outline="", width=1):
        """Draw a rounded shape using Tk's polygon smoothing."""
        r = min(radius, (x2-x1)/2, (y2-y1)/2)
        points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
                  x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
                  x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return canvas.create_polygon(points, smooth=True, splinesteps=16,
                                     fill=fill, outline=outline, width=width)

    def choose_preference(self, voice):
        self.preference.set(voice)
        self.draw_preferences()

    def draw_preferences(self):
        selected = self.preference.get()
        for voice, canvas in self.preference_buttons.items():
            canvas.delete("all")
            active = (voice == selected)
            # Light-blue capsule with a subtle border and visible selected state.
            self.rounded_rect(canvas, 4, 4, 146, 50, 23,
                              "#D9ECFF" if active else "#EFF5FC",
                              "#6FA6F4" if active else "#D5E3F2", 2)
            canvas.create_oval(23, 20, 37, 34, outline="#2F7DE1" if active else "#9DB2CC", width=2,
                               fill="#2F7DE1" if active else "#EFF5FC")
            if active:
                canvas.create_oval(27, 24, 33, 30, fill="white", outline="")
            canvas.create_text(87, 27, text="Voice " + voice,
                               fill="#175DAA" if active else INK,
                               font=("Arial", 13, "bold" if active else "normal"))

    def select_rating_voice(self, v):
        self.active_rating_voice = v
        for letter, button in self.rating_buttons.items():
            active = letter == v
            button.configure(bg=BLUE if active else "#EAF0FA", fg="white" if active else INK)
        self.render_rating_sliders()

    def render_rating_sliders(self):
        for child in self.rating_panel.winfo_children():
            child.destroy()
        voice = self.active_rating_voice
        for q in QUESTIONS:
            row = tk.Frame(self.rating_panel, bg="#F7F9FD")
            row.pack(fill="x", pady=(8, 12))
            top = tk.Frame(row, bg="#F7F9FD")
            top.pack(fill="x")
            tk.Label(top, text=q, bg="#F7F9FD", fg=INK,
                     font=("Arial", 13, "bold")).pack(side="left")
            score = tk.Label(top, bg="#F7F9FD", fg="#2B74D6",
                             text=f"{self.rating_vars[(voice,q)].get()} / 7",
                             font=("Arial", 14, "bold"))
            score.pack(side="right")

            slider = tk.Canvas(row, bg="#F7F9FD", height=51,
                               highlightthickness=0, bd=0, cursor="hand2")
            slider.pack(fill="x", pady=(6, 0))

            def draw(event=None, canvas=slider, v=voice, item=q):
                canvas.delete("all")
                w = max(200, canvas.winfo_width())
                left, right, cy = 21, w-21, 21
                fraction = (self.rating_vars[(v,item)].get()-1)/6
                x = left + (right-left)*fraction
                self.rounded_rect(canvas, left, cy-5, right, cy+5, 5,
                                  "#D8E6F7")
                if x > left+2:
                    self.rounded_rect(canvas, left, cy-5, x, cy+5, 5,
                                      "#6AA8F4")
                for n in range(7):
                    px = left+(right-left)*n/6
                    canvas.create_oval(px-2,cy-2,px+2,cy+2,
                                      fill="#B1C6E1" if px > x else "#EAF5FF", outline="")
                # Touch-friendly thumb: subtle halo, blue outline, white center.
                canvas.create_oval(x-18,cy-18,x+18,cy+18,fill="#D3E7FF",outline="")
                canvas.create_oval(x-13,cy-13,x+13,cy+13,fill="#FFFFFF",
                                  outline="#4C91E9",width=2)
                canvas.create_oval(x-4,cy-4,x+4,cy+4,fill="#79B1FA",outline="")

            def change(event, canvas=slider, v=voice, item=q, label=score, redraw=draw):
                w = max(200, canvas.winfo_width())
                ratio = max(0.0, min(1.0, (event.x-21)/(w-42)))
                value = max(1, min(7, 1+round(6*ratio)))
                self.rating_vars[(v,item)].set(value)
                self.rating_touched.add((v,item))
                label.configure(text=f"{value} / 7")
                redraw()

            slider.bind("<Configure>", draw)
            slider.bind("<Button-1>", change)
            slider.bind("<B1-Motion>", change)
            edge = tk.Frame(row, bg="#F7F9FD")
            edge.pack(fill="x", padx=10)
            tk.Label(edge, text="1 · Very low", bg="#F7F9FD", fg=MUTED,
                     font=("Arial", 9)).pack(side="left")
            tk.Label(edge, text="7 · Very high", bg="#F7F9FD", fg=MUTED,
                     font=("Arial", 9)).pack(side="right")

    def replay_selected(self):
        self.play(self.active_rating_voice, replay=True)

    def submit(self):
        if self.channel.get_busy():
            messagebox.showinfo("Please wait", "Please wait until the voice finishes playing.")
            return
        missing = [(v,q) for v in "ABC" for q in QUESTIONS if (v,q) not in self.rating_touched]
        if missing:
            first, question = missing[0]
            self.select_rating_voice(first)
            messagebox.showwarning("Incomplete", f"Please rate {question} for Voice {first}.")
            return
        if self.preference.get() not in ("A", "B", "C"):
            messagebox.showwarning("Incomplete", "Please choose the most suitable voice.")
            return
        task, parameter, codes = self.rounds[self.index]
        stamp = datetime.now().isoformat(timespec="seconds")
        rows = []
        for letter, code in zip("ABC", codes):
            rows.append({
                "session_id": self.session, "timestamp": stamp,
                "round": self.index+1, "task": task, "parameter": parameter,
                "button": letter, "audio_code": code,
                "naturalness": self.rating_vars[(letter, "Naturalness")].get(),
                "appropriateness": self.rating_vars[(letter, "Appropriateness")].get(),
                "comfort": self.rating_vars[(letter, "Comfort")].get(),
                "clarity": "",
                "preferred": 1 if self.preference.get() == letter else 0,
                "replay_count": self.replays[letter],
                "participant_number": self.participant_number,
                "task_order": self.task_order,
                "parameter_order": self.parameter_order,
                "voice_position_order": "/".join(codes),
            })
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            new = not RESULTS.exists() or RESULTS.stat().st_size == 0
            with RESULTS.open("a", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                if new:
                    writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            messagebox.showerror("Save error", str(exc))
            return
        print(f"[SAVED] Round {self.index+1} -> {RESULTS}", flush=True)
        self.index += 1
        if self.index == len(self.rounds):
            self.show_finish()
        else:
            if self.index in (3,):
                self.show_scenario()
            else:
                try:
                    self.load_round()
                except (OSError, pygame.error, RuntimeError) as exc:
                    messagebox.showerror("Audio error", str(exc))
                    self.show_finish(error=True)
                    return
                self.show_listening()

    def show_finish(self, error=False):
        self.mode = "finished"
        self.clear()
        self.title("Study stopped" if error else "Thank you!")
        self.text("Previous submitted ratings were saved." if error else
                  "All six rounds are completed. Your responses were saved.", 16)
        self.text(f"Saved file: {RESULTS}", 11)

    def close(self):
        self.running = False
        self.disconnect()
        if self.audio_ready:
            pygame.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()



# V7 5-inch layout: only interface methods are overridden.
# Hardware, serial reader, round order, waveform playback and CSV remain inherited.
class VoiceStudyV7(VoiceStudy):
    GLASS = "#F7FAFF"
    PALE = "#E8F1FD"
    SOFT_BLUE = "#A6C9FA"
    DEEP_BLUE = "#5E99E9"

    def clear(self):
        self.face_canvas = None
        for child in self.root.winfo_children():
            child.destroy()
        # Diagnostics are available in PowerShell. No status strip on 5-inch screen.
        self.port_status = None
        self.debug_status = None

    def round_header(self, parent, include_task=True):
        task = self.rounds[self.index][0]
        bar = tk.Frame(parent, bg=BG, height=42)
        bar.pack(fill="x", padx=19, pady=(10, 6))
        bar.pack_propagate(False)
        tk.Label(bar, text=f"Round {self.index+1} / 6" + (f"  ·  {task}" if include_task else ""),
                 bg=BG, fg=INK, font=("Arial", 15, "bold")).pack(side="left", pady=7)
        dots = tk.Frame(bar, bg=BG)
        dots.pack(side="right", pady=14)
        for i in range(6):
            tk.Label(dots, text="●", font=("Arial", 11), bg=BG,
                     fg=self.DEEP_BLUE if i==self.index else "#CAD8EA").pack(side="left", padx=2)

    def flat_button(self, parent, title, callback, active=False, w=130, h=44):
        canvas = tk.Canvas(parent, width=w, height=h, bd=0, highlightthickness=0, bg=BG, cursor="hand2")
        self.rounded_rect(canvas, 2,2,w-2,h-2,h/2-2,
                          "#BBD7FC" if active else "#F8FBFF",
                          "#91B9F1" if active else "#DDE8F7",1)
        canvas.create_text(w/2,h/2,text=title, font=("Arial",12,"bold"),
                           fill="#21598D" if active else INK)
        canvas.bind("<Button-1>",lambda e: callback())
        return canvas

    def show_start(self):
        self.mode="start"
        self.clear()
        tk.Label(self.root, text="Robot Voice Study", bg=BG,fg=INK,
                 font=("Arial",23,"bold")).pack(pady=(26,10))
        tk.Label(self.root, text="Six short rounds · Welcome & Wayfinding",bg=BG,fg=MUTED,
                 font=("Arial",13)).pack(pady=5)
        tk.Label(self.root, text="Listen to A, B and C. Rate each voice after the round.",bg=BG,fg=INK,
                 font=("Arial",12),wraplength=690).pack(pady=(8,18))
        row=tk.Frame(self.root,bg=BG)
        row.pack(pady=4)
        tk.Label(row,text="Pico port",bg=BG,fg=MUTED,font=("Arial",11)).pack(side="left",padx=6)
        self.port_menu=ttk.Combobox(row,textvariable=self.port_choice,state="readonly",width=10,font=("Arial",11))
        self.port_menu.pack(side="left",padx=6)
        self.flat_button(row,"Refresh",self.refresh_ports,w=105,h=40).pack(side="left",padx=5)
        self.flat_button(row,"Connect Pico",self.reconnect,w=150,h=40).pack(side="left",padx=5)
        self.refresh_ports()
        self.connection_label=tk.Label(self.root,text=f"Pico: {self.serial_state}",bg=BG,fg=MUTED,font=("Arial",10))
        self.connection_label.pack(pady=9)
        self.flat_button(self.root,"Start Study  →",self.start,active=True,w=260,h=52).pack(pady=(10,12))
        tk.Label(self.root,text="Pilot mode · Keyboard A/B/C available for desktop testing",bg=BG,fg=MUTED,
                 font=("Arial",10)).pack()

    def update_diagnostics(self):
        super().update_diagnostics()
        if hasattr(self,"connection_label") and self.connection_label.winfo_exists():
            self.connection_label.config(text=f"Pico: {self.serial_state}")

    def show_listening(self):
        self.mode="listening"
        self.clear()
        self.round_header(self.root)
        self.face_canvas=tk.Canvas(self.root,bg=FACE_BG,highlightthickness=0,height=288)
        self.face_canvas.pack(fill="both",expand=True,padx=19,pady=(0,8))
        bottom=tk.Frame(self.root,bg=BG,height=55)
        bottom.pack(fill="x",padx=19,pady=(0,8))
        self.screen_status=tk.Label(bottom,text="Listen: A  ·  B  ·  C",bg=BG,fg=INK,font=("Arial",13,"bold"))
        self.screen_status.pack(side="left",pady=12)
        self.flat_button(bottom,"Connect Pico",self.reconnect,w=130,h=38).pack(side="right",padx=4,pady=5)
        self.draw_face()

    def render_questionnaire(self):
        self.clear()
        self.round_header(self.root)
        panel=tk.Frame(self.root,bg="#FDFEFF",highlightthickness=1,highlightbackground="#E6EDF7")
        panel.pack(fill="both",expand=True,padx=18,pady=(0,10))
        tabs=tk.Frame(panel,bg="#FDFEFF")
        tabs.pack(fill="x",padx=14,pady=(10,8))
        # Three equal-width columns prevent Voice C from being pushed off a 5-inch screen.
        self.rating_buttons = {}
        for column, voice in enumerate("ABC"):
            tabs.grid_columnconfigure(column, weight=1, uniform="voice_tabs")
            c = tk.Canvas(tabs, bg="#FDFEFF", bd=0, highlightthickness=0,
                          height=40, width=1, cursor="hand2")
            c.grid(row=0, column=column, sticky="ew", padx=3)
            c.bind("<Button-1>", lambda e, v=voice: self.select_rating_voice(v))
            c.bind("<Configure>", lambda e: self.draw_rating_tabs())
            self.rating_buttons[voice] = c
        self.root.after_idle(self.draw_rating_tabs)
        self.rating_panel=tk.Frame(panel,bg="#F7FAFF")
        self.rating_panel.pack(fill="x",padx=15,pady=(0,8))
        self.render_rating_sliders()
        preference_row=tk.Frame(panel,bg="#FDFEFF")
        preference_row.pack(fill="x",padx=18,pady=(1,8))
        tk.Label(preference_row,text="Preferred voice",bg="#FDFEFF",fg=INK,
                 font=("Arial",12,"bold")).pack(side="left",padx=(3,15))
        self.preference_buttons={}
        for v in "ABC":
            c=tk.Canvas(preference_row,width=95,height=40,bg="#FDFEFF",highlightthickness=0,cursor="hand2")
            c.pack(side="left",padx=5)
            c.bind("<Button-1>",lambda e,v=v:self.choose_preference(v))
            self.preference_buttons[v]=c
        self.draw_preferences()
        foot=tk.Frame(panel,bg="#FDFEFF")
        foot.pack(fill="x",padx=18,pady=(0,10))
        self.flat_button(foot,"↻  Replay",self.replay_selected,w=170,h=43).pack(side="left",padx=3)
        self.flat_button(foot,"Submit & Continue  →",self.submit,active=True,w=240,h=43).pack(side="right",padx=3)

    def draw_rating_tabs(self):
        for v,c in self.rating_buttons.items():
            c.delete("all")
            w=max(25,c.winfo_width())
            active=v==self.active_rating_voice
            self.rounded_rect(c,2,2,w-2,38,17,
                              "#BBD7FC" if active else "#F0F5FC",
                              "#91BAF2" if active else "#E3EBF6",1)
            c.create_text(w/2,20,text=f"Voice {v}",font=("Arial",12,"bold"),
                          fill="#20548B" if active else INK)

    def select_rating_voice(self,v):
        self.active_rating_voice=v
        self.draw_rating_tabs()
        self.render_rating_sliders()

    def draw_preferences(self):
        for v,c in self.preference_buttons.items():
            c.delete("all")
            active=self.preference.get()==v
            self.rounded_rect(c,2,2,93,38,18,
                              "#BBD7FC" if active else "#F5F8FD",
                              "#77A9E7" if active else "#DCE7F5",1)
            c.create_text(47,20,text=v,font=("Arial",12,"bold"),
                          fill="#174E83" if active else INK)

    def render_rating_sliders(self):
        for child in self.rating_panel.winfo_children():
            child.destroy()
        v=self.active_rating_voice
        for q in QUESTIONS:
            row=tk.Frame(self.rating_panel,bg="#F7FAFF",height=62)
            row.pack(fill="x",padx=12,pady=3)
            row.pack_propagate(False)
            tk.Label(row,text=q,bg="#F7FAFF",fg=INK,font=("Arial",12,"bold"),anchor="w",
                     width=18).pack(side="left",padx=(3,6))
            value=tk.Label(row,text=str(self.rating_vars[(v,q)].get()),bg="#F7FAFF",fg="#3979C8",
                           width=2,font=("Arial",14,"bold"))
            value.pack(side="right",padx=(4,8))
            c=tk.Canvas(row,bg="#F7FAFF",height=58,highlightthickness=0,cursor="hand2")
            c.pack(side="left",fill="both",expand=True)
            def draw(event=None,canvas=c,voice=v,question=q):
                canvas.delete("all")
                w=max(90,canvas.winfo_width())
                l,r,cy=19,w-19,28
                n=self.rating_vars[(voice,question)].get()
                x=l+(r-l)*(n-1)/6
                self.rounded_rect(canvas,l,cy-4,r,cy+4,4,"#D7E5F8")
                if x>l+1:
                    self.rounded_rect(canvas,l,cy-4,x,cy+4,4,"#A5C9F9")
                for i in range(7):
                    px=l+(r-l)*i/6
                    canvas.create_oval(px-2,cy-2,px+2,cy+2,fill="#B5CAE4",outline="")
                canvas.create_oval(x-15,cy-15,x+15,cy+15,fill="#EAF4FF",outline="")
                canvas.create_oval(x-11,cy-11,x+11,cy+11,fill="white",outline="#89B6F2",width=2)
            def change(event,canvas=c,voice=v,question=q,label=value,redraw=draw):
                w=max(90,canvas.winfo_width())
                ratio=max(0,min(1,(event.x-19)/(w-38)))
                n=max(1,min(7,round(1+ratio*6)))
                self.rating_vars[(voice,question)].set(n)
                self.rating_touched.add((voice,question))
                label.configure(text=str(n))
                redraw()
            c.bind("<Configure>",draw)
            c.bind("<Button-1>",change)
            c.bind("<B1-Motion>",change)
        self.root.after_idle(self.draw_rating_tabs)



# V8 compact full-screen touchscreen interface.
# The proven V7 serial, audio mappings, rating validation and CSV writer are inherited unchanged.
class _SilentStatus:
    def config(self, **kwargs):
        pass


def find_secondary_display():
    """Return (left, top, width, height) of a Windows non-primary display, or None."""
    try:
        import ctypes
        from ctypes import wintypes
        class RECT(ctypes.Structure):
            _fields_ = [("left",wintypes.LONG),("top",wintypes.LONG),
                        ("right",wintypes.LONG),("bottom",wintypes.LONG)]
        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize",wintypes.DWORD),("rcMonitor",RECT),
                        ("rcWork",RECT),("dwFlags",wintypes.DWORD)]
        infos=[]
        MonitorEnumProc=ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p,
                                         ctypes.c_void_p,ctypes.POINTER(RECT),ctypes.c_ssize_t)
        def callback(handle, hdc, rect, data):
            mi=MONITORINFO()
            mi.cbSize=ctypes.sizeof(MONITORINFO)
            if ctypes.windll.user32.GetMonitorInfoW(handle,ctypes.byref(mi)):
                r=mi.rcMonitor
                infos.append((bool(mi.dwFlags & 1),(r.left,r.top,r.right-r.left,r.bottom-r.top)))
            return True
        fn=MonitorEnumProc(callback)
        ctypes.windll.user32.EnumDisplayMonitors(None,None,fn,0)
        return next((coords for primary,coords in infos if not primary),None)
    except Exception as e:
        print('[DISPLAY] Detection fallback:',e,flush=True)
        return None


class VoiceStudyV8(VoiceStudyV7):
    """Kiosk-ready second-screen UI. F11 toggles fullscreen; Esc exits kiosk; Ctrl+Shift+Q quits."""
    def __init__(self):
        # Avoid Windows DPI scaling making the 5-inch layout microscopic.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.kiosk = False
        self.display_rect = None
        self.slider_drag = None
        self.screen_notice = ""
        self.hitboxes = []
        self.ui_canvas = None
        self.win_geometry = "800x480+80+80"
        self._replay_rect = None
        super().__init__()
        self.root.title("Robot Voice Study - V8 Touch")
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self.exit_fullscreen())
        self.root.bind("<Control-Shift-Q>", lambda e: self.close())
        self.root.bind("<Control-Shift-P>", lambda e: self.reconnect())
        print('[V8] Test on desktop with keyboard A/B/C; Ctrl+Shift+Q to quit.',flush=True)

    def _position_kiosk_window(self, x, y, w, h):
        """Force the native top-level window to the target monitor on Windows.

        Tk geometry alone can leave a borderless window at its old +55,+55
        position when Windows display mode/DPI changes (duplicate/extend).
        """
        if not self.kiosk or not self.root.winfo_exists():
            return
        self.root.geometry(f"{w}x{h}{x:+d}{y:+d}")
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # Tk's winfo_id may be a child of the native decorated wrapper.
            user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint)
            user32.GetAncestor.restype = ctypes.c_void_p
            user32.SetWindowPos.argtypes = (
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
            user32.SetWindowPos.restype = ctypes.c_int
            hwnd = user32.GetAncestor(ctypes.c_void_p(self.root.winfo_id()), 2)  # GA_ROOT
            if not hwnd:
                hwnd = self.root.winfo_id()
            # HWND_TOPMOST = -1, SWP_SHOWWINDOW = 0x0040.
            user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1),
                                int(x), int(y), int(w), int(h), 0x0040)
        except Exception as exc:
            print(f"[DISPLAY] Native positioning fallback: {exc}", flush=True)

    def enable_kiosk(self):
        if self.kiosk:
            return
        self.root.update_idletasks()
        self.win_geometry = self.root.geometry()
        target = find_secondary_display()
        if target is None:
            # In Duplicate mode Windows exposes a single logical display.
            # GetSystemMetrics gives its real desktop dimensions; do not
            # rely on Tk's cached screen width after changing display modes.
            try:
                import ctypes
                user32 = ctypes.windll.user32
                target = (0, 0, int(user32.GetSystemMetrics(0)),
                          int(user32.GetSystemMetrics(1)))
            except Exception:
                target = (0, 0, self.root.winfo_screenwidth(),
                          self.root.winfo_screenheight())
            print('[DISPLAY] Single logical monitor (duplicate or primary); '
                  'using full primary screen.', flush=True)
        self.display_rect = target
        x, y, w, h = target
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.kiosk = True
        self._position_kiosk_window(x, y, w, h)
        # Windows sometimes applies the old window location one idle cycle
        # later, so reassert placement after its pending window messages.
        self.root.after(80, lambda: self._position_kiosk_window(x, y, w, h))
        self.root.after(300, lambda: self._position_kiosk_window(x, y, w, h))
        print(f'[DISPLAY] Kiosk target {x},{y} {w}x{h}', flush=True)

    def exit_fullscreen(self):
        if not self.kiosk: return
        self.root.attributes('-topmost',False)
        self.root.overrideredirect(False)
        self.root.geometry(self.win_geometry)
        self.kiosk=False
        self.root.update_idletasks()
        print('[DISPLAY] Windowed mode. Press F11 to return.',flush=True)

    def toggle_fullscreen(self):
        self.exit_fullscreen() if self.kiosk else self.enable_kiosk()

    def show_start(self):
        # Setup page remains in a normal window so port selection is accessible.
        super().show_start()
        self.root.bind('<F11>',lambda e:self.toggle_fullscreen())

    def show_listening(self):
        self.mode='listening'
        self.clear()
        self.enable_kiosk()
        self.screen_status = _SilentStatus()  # inherited playback loop updates this
        self.face_canvas=tk.Canvas(self.root,bg=FACE_BG,highlightthickness=0,bd=0)
        self.face_canvas.pack(fill='both',expand=True)
        self.draw_face()

    def draw_face(self):
        c=self.face_canvas
        if self.mode!='listening' or c is None or not c.winfo_exists(): return
        c.delete('all')
        w,h=max(1,c.winfo_width()),max(1,c.winfo_height())
        s=min(w/800,h/480)
        cx,cy=w/2,h/2
        t=time.monotonic()-self.face_start
        speaking=self.current_voice is not None and self.channel.get_busy()
        phase=t%4.5
        blink=max(.10,abs(phase-.11)/.11) if phase<.22 else 1.0
        shift=(1.2*math.sin(t*3.5) if speaking else 0)*s
        col=FACE_CYAN if not speaking or math.sin(t*5)>-.75 else '#9CF4FB'
        # Large friendly eyes and symmetrical cheeks / omega mouth.
        for dx in (-130,130):
            x,y=cx+dx*s,cy-32*s+shift
            ew,eh=55*s,82*s*blink
            c.create_oval(x-ew/2,y-eh/2,x+ew/2,y+eh/2,fill=col,outline='')
        for dx in (-220,220):
            x,y=cx+dx*s,cy+49*s
            c.create_oval(x-31*s,y-14*s,x+31*s,y+14*s,fill=FACE_PINK,outline='')
        pts=[cx-28*s,cy+24*s,cx-26*s,cy+45*s,cx-13*s,cy+51*s,
             cx,cy+34*s,cx+13*s,cy+51*s,cx+26*s,cy+45*s,cx+28*s,cy+24*s]
        c.create_line(*pts,fill=col,width=max(3,round(6*s)),smooth=True,
                      capstyle=tk.ROUND,joinstyle=tk.ROUND)
        if speaking:
            for side in (-1,1):
                x,y=cx+side*305*s,cy-100*s
                c.create_line(x,y,x+side*12*s,y-14*s,fill=col,width=max(2,round(4*s)),capstyle=tk.ROUND)
                c.create_line(x+side*17*s,y+16*s,x+side*34*s,y+10*s,
                              fill=col,width=max(2,round(4*s)),capstyle=tk.ROUND)

    def _screen_canvas(self):
        self.clear()
        canvas=tk.Canvas(self.root,bg='#F4F8FE',bd=0,highlightthickness=0)
        canvas.pack(fill='both',expand=True)
        self.ui_canvas=canvas
        self.hitboxes=[]
        self.slider_drag=None
        canvas.bind('<Configure>',lambda e:self.paint_questionnaire())
        canvas.bind('<Button-1>',self.touch_start)
        canvas.bind('<B1-Motion>',self.touch_move)
        canvas.bind('<ButtonRelease-1>',self.touch_end)
        return canvas

    def render_questionnaire(self):
        self.mode='questionnaire'
        self._screen_canvas()
        self.root.after_idle(self.paint_questionnaire)

    def _coord(self,event):
        w=max(self.ui_canvas.winfo_width(),1)
        h=max(self.ui_canvas.winfo_height(),1)
        return event.x*800/w,event.y*480/h

    def _rounded(self,x1,y1,x2,y2,r,fill,stroke='',sw=1):
        # Canvas is scaled via helpers to the actual screen pixel dimensions.
        c=self.ui_canvas; sx=self.ui_canvas.winfo_width()/800; sy=self.ui_canvas.winfo_height()/480
        r=min(r,(x2-x1)/2,(y2-y1)/2)
        p=[(x1+r,y1),(x2-r,y1),(x2,y1),(x2,y1+r),
           (x2,y2-r),(x2,y2),(x2-r,y2),(x1+r,y2),
           (x1,y2),(x1,y2-r),(x1,y1+r),(x1,y1)]
        coords=[]
        for x,y in p: coords.extend((x*sx,y*sy))
        c.create_polygon(coords,smooth=True,splinesteps=15,
                         fill=fill,outline=stroke,width=max(1,sw*min(sx,sy)))

    def _text(self,x,y,txt,size=17,color='#233650',bold=False,anchor='center'):
        c=self.ui_canvas; sx=c.winfo_width()/800; sy=c.winfo_height()/480
        fs=max(9,round(size*min(sx,sy)))
        return c.create_text(x*sx,y*sy,text=txt,fill=color,
                      font=('Arial',fs,'bold' if bold else 'normal'),anchor=anchor)

    def _oval(self,x1,y1,x2,y2,fill,stroke='',width=1):
        c=self.ui_canvas; sx=c.winfo_width()/800; sy=c.winfo_height()/480
        c.create_oval(x1*sx,y1*sy,x2*sx,y2*sy,fill=fill,
                      outline=stroke,width=max(1,width*min(sx,sy)))

    def _line(self,x1,y1,x2,y2,color,width=5):
        c=self.ui_canvas; sx=c.winfo_width()/800; sy=c.winfo_height()/480
        c.create_line(x1*sx,y1*sy,x2*sx,y2*sy,fill=color,
                      width=max(2,width*min(sx,sy)),capstyle=tk.ROUND)

    def _target(self,rect,kind,value):
        self.hitboxes.append((rect,kind,value))

    def paint_questionnaire(self):
        if self.mode!='questionnaire' or self.ui_canvas is None or not self.ui_canvas.winfo_exists(): return
        c=self.ui_canvas
        if c.winfo_width()<2 or c.winfo_height()<2:return
        c.delete('all');self.hitboxes=[]
        task=self.rounds[self.index][0]
        # Keep the actual participant screen uncluttered: no tech info or desktop controls.
        self._rounded(12,8,788,472,27,'#F7FAFF','#E3ECF9')
        self._rounded(24,14,157,48,17,'#E7F1FE')
        self._text(90,31,f'Round {self.index+1} / 6',16,'#3D638C',True)
        self._text(400,31,task,21,'#294B75',True)
        # Voice tabs: equal width, large finger targets.
        for j,v in enumerate('ABC'):
            x1=27+j*252; x2=x1+242
            active=v==self.active_rating_voice
            self._rounded(x1,60,x2,108,24,'#BFD9FA' if active else '#FFFFFF',
                          '#91B9EF' if active else '#E1EAF5')
            self._text((x1+x2)/2,84,f'Voice {v}',19,'#20548C' if active else '#516680',True)
            self._target((x1,56,x2,112),'tab',v)
        # Three rating rows; rating values are saved independently per voice.
        self._rounded(27,119,773,324,23,'#FFFFFF','#E1EAF5')
        voice=self.active_rating_voice
        ylist=(157,225,293)
        for q,y in zip(QUESTIONS,ylist):
            n=self.rating_vars[(voice,q)].get()
            touched=(voice,q) in self.rating_touched
            self._text(47,y-11,q,18,'#273E5D',True,anchor='w')
            self._rounded(701,y-25,752,y+10,16,'#EDF5FF')
            self._text(726,y-7,str(n) if touched else '—',18,'#3577C7',True)
            left,right,cy=310,672,y+12
            self._rounded(left,cy-5,right,cy+5,5,'#DCE9F9')
            thumb=left+(right-left)*(n-1)/6
            if thumb>left+1:
                self._rounded(left,cy-5,thumb,cy+5,5,'#A4C8F7')
            for i in range(7):
                px=left+(right-left)*i/6
                self._oval(px-2,cy-2,px+2,cy+2,'#C1D4EF')
            self._oval(thumb-19,cy-19,thumb+19,cy+19,'#E6F2FF')
            self._oval(thumb-15,cy-15,thumb+15,cy+15,'#FFFFFF','#8CB9F3',2)
            self._oval(thumb-5,cy-5,thumb+5,cy+5,'#8CB9F3')
            self._target((left-22,cy-24,right+22,cy+24),'slider',q)
        # Preference is chosen only once, after scoring A, B, C.
        self._text(38,353,'Preferred voice',17,'#334B6D',True,anchor='w')
        for i,v in enumerate('ABC'):
            x1=321+i*147; x2=x1+133
            selected=self.preference.get()==v
            self._rounded(x1,332,x2,384,24,'#BFD9FA' if selected else '#FFFFFF',
                          '#86B2EA' if selected else '#DAE7F7')
            self._oval(x1+19,350,x1+37,368,'#4288DF' if selected else '#FFFFFF',
                       '#7DAAE5' if selected else '#C0D3EA',2)
            self._text(x1+84,358,v,19,'#255A94',True)
            self._target((x1,330,x2,386),'prefer',v)
        # Bottom toolbar.
        self._rounded(27,401,251,462,28,'#FFFFFF','#DCE8F7')
        self._text(139,431,'↻  Replay',19,'#547398',True)
        self._target((27,398,251,468),'replay',None)
        self._rounded(269,401,773,462,28,'#BCD8FD','#8FB8ED')
        self._text(521,431,'Submit & Continue  →',19,'#225B99',True)
        self._target((269,398,773,468),'submit',None)
        if self.screen_notice:
            self._rounded(268,113,750,140,12,'#FFF5DB','#F1DDA1')
            self._text(509,126,self.screen_notice,12,'#886128',True)

    def _set_slider(self,x,q):
        left,right=310,672
        value=1+round(6*min(1,max(0,(x-left)/(right-left))))
        voice=self.active_rating_voice
        self.rating_vars[(voice,q)].set(value)
        self.rating_touched.add((voice,q))
        self.screen_notice=''
        self.paint_questionnaire()

    def touch_start(self,event):
        if self.mode!='questionnaire':return
        x,y=self._coord(event)
        for (x1,y1,x2,y2),kind,value in self.hitboxes:
            if x1<=x<=x2 and y1<=y<=y2:
                if kind=='slider':
                    self.slider_drag=value
                    self._set_slider(x,value)
                elif kind=='tab':
                    self.active_rating_voice=value; self.screen_notice='';self.paint_questionnaire()
                elif kind=='prefer':
                    self.preference.set(value);self.screen_notice='';self.paint_questionnaire()
                elif kind=='replay':
                    self.replay_selected()
                elif kind=='submit':
                    self.submit()
                return

    def touch_move(self,event):
        if self.slider_drag and self.mode=='questionnaire':
            x,_=self._coord(event)
            self._set_slider(x,self.slider_drag)

    def touch_end(self,event):
        self.slider_drag=None

    def submit(self):
        if self.channel.get_busy():
            self.screen_notice='Please wait for playback to finish'
            self.paint_questionnaire();return
        missing=[(v,q) for v in 'ABC' for q in QUESTIONS if (v,q) not in self.rating_touched]
        if missing:
            v,q=missing[0]
            self.active_rating_voice=v
            self.screen_notice=f'Please rate {q} for Voice {v}'
            self.paint_questionnaire();return
        if self.preference.get() not in 'ABC':
            self.screen_notice='Please choose your preferred voice'
            self.paint_questionnaire();return
        # Save exactly as proven V7, preserving session id, CSV column names, etc.
        super().submit()

    def show_finish(self,error=False):
        self.mode='finished';self.clear()
        c=tk.Canvas(self.root,bg='#F4F8FE',highlightthickness=0)
        c.pack(fill='both',expand=True)
        c.create_text(400,165, text='Study stopped' if error else 'Thank you!',
                      fill='#315B8B',font=('Arial',32,'bold'))
        c.create_text(400,245,text='Previously saved responses are retained.' if error else
                      'Your responses have been saved.',fill='#617C9B',font=('Arial',17))
        self.ui_canvas=c
        c.bind('<Button-1>',lambda e:self.close())

    def close(self):
        self.kiosk=False
        super().close()



class VoiceStudyV9(VoiceStudyV8):
    """V9: balanced task blocks, balanced voice positions, A-B-C guided playback."""
    COUNTER = DATA_DIR / "participant_sequence_v9.txt"

    def _prepare_participant(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            number = int(self.COUNTER.read_text(encoding="utf-8").strip()) + 1
        except (FileNotFoundError, ValueError):
            number = 1
        # Advance the counter before testing; aborted sessions can leave gaps.
        self.COUNTER.write_text(str(number), encoding="utf-8")
        self.participant_number = number
        self.session = uuid.uuid4().hex[:8]
        self.index = 0
        tasks = ("Welcome", "Wayfinding") if number % 2 else ("Wayfinding", "Welcome")
        self.task_order = " > ".join(tasks)
        permutations = list(itertools.permutations(("Pitch", "Loudness", "Intonation")))
        params = permutations[((number - 1) // 2) % len(permutations)]
        self.parameter_order = " > ".join(params)
        original = {(task, param): codes for task, param, codes in ROUNDS}
        self.rounds = []
        for task in tasks:
            for param in params:
                codes = original[(task, param)]
                # Three positions rotate: baseline is not always B.
                shift = (number - 1 + len(self.rounds)) % 3
                rotated = codes[shift:] + codes[:shift]
                self.rounds.append((task, param, rotated))
        print(f"[PARTICIPANT] {number} {self.session} | {self.task_order} | {self.parameter_order}", flush=True)

    def start(self):
        self._prepare_participant()
        self.show_scenario()

    def show_scenario(self):
        """Responsive scenario page for 800x480 touch displays and larger monitors."""
        self.mode = "scenario"
        self.clear()
        self.enable_kiosk()
        task = self.rounds[self.index][0]
        if task == "Welcome":
            self.scenario_title = "Welcome"
            self.scenario_description = (
                "You have just arrived at the school.\n"
                "The robot is welcoming you."
            )
        else:
            self.scenario_title = "Wayfinding"
            self.scenario_description = (
                "You are looking for a classroom.\n"
                "You ask the robot: 'Where is the classroom?'"
            )
        c = tk.Canvas(self.root, bg="#F4F8FE", highlightthickness=0, bd=0)
        c.pack(fill="both", expand=True)
        self.ui_canvas = c
        c.bind("<Configure>", self._paint_scenario)
        c.bind("<Button-1>", self._scenario_touch)
        self.root.after_idle(self._paint_scenario)
        print(f"[SCENARIO] {task}", flush=True)

    def _scenario_transform(self):
        """Uniform scale and center relative to a virtual 800x480 layout."""
        c = self.ui_canvas
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        scale = min(w / 800.0, h / 480.0)
        return (w - 800 * scale) / 2, (h - 480 * scale) / 2, scale

    def _paint_scenario(self, event=None):
        if self.mode != "scenario" or self.ui_canvas is None or not self.ui_canvas.winfo_exists():
            return
        c = self.ui_canvas
        if c.winfo_width() < 2 or c.winfo_height() < 2:
            return
        c.delete("all")
        ox, oy, scale = self._scenario_transform()

        def xy(x, y):
            return ox + x * scale, oy + y * scale

        def font(size, bold=False):
            return ("Arial", max(10, round(size * scale)), "bold" if bold else "normal")

        c.create_text(*xy(400, 76), text=self.scenario_title,
                      fill="#294B75", font=font(29, True))
        c.create_text(*xy(400, 188), text=self.scenario_description,
                      fill="#344D70", font=font(19), justify="center",
                      width=730 * scale)
        c.create_text(*xy(400, 298), text="Listen in order: A → B → C",
                      fill="#577698", font=font(17))
        x1, y1 = xy(265, 350)
        x2, y2 = xy(535, 426)
        c.create_rectangle(x1, y1, x2, y2, fill="#BFD9FA",
                           outline="#91B9EF", width=max(1, round(2 * scale)),
                           tags="scenario_start")
        c.create_text(*xy(400, 388), text="Start →",
                      fill="#225B99", font=font(23, True), tags="scenario_start")

    def _scenario_touch(self, event):
        if self.mode != "scenario":
            return
        ox, oy, scale = self._scenario_transform()
        x, y = (event.x - ox) / scale, (event.y - oy) / scale
        if 265 <= x <= 535 and 350 <= y <= 426:
            self.begin_block()

    def begin_block(self):
        if self.mode != "scenario":
            return
        try:
            self.load_round()
        except (OSError, pygame.error, RuntimeError) as exc:
            messagebox.showerror("Unable to load audio", str(exc))
            return
        self.show_listening()

    def play(self, letter, replay=False):
        if self.mode == "listening":
            expected = "ABC"[len(self.finished)] if len(self.finished) < 3 else None
            if letter != expected:
                print(f"[ORDER] Ignored {letter}; next required: {expected}", flush=True)
                return
        super().play(letter, replay=replay)

    def on_key(self, event):
        if self.mode == "scenario" and event.keysym in ("Return", "space"):
            self.begin_block()
            return
        super().on_key(event)

    def show_start(self):
        super().show_start()
        # A spoken protocol is given by the researcher, before clicking Start Study.

if __name__=='__main__':
    VoiceStudyV9().run()
