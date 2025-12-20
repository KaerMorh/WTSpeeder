import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import math
from array import array

import pygame


def clamp(x, a, b):
    return a if x < a else (b if x > b else x)


class AlarmCurvePygameDemo:
    """
    pygame.mixer 音频 + Tk UI
    - Tone 模式：生成正弦波，可做“越危险越尖锐”的 pitch
    - File 模式：播放用户选择的音效文件，可做“越危险越大声/越密集”的节奏
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Alarm Curve Demo (pygame.mixer)")

        # ---- pygame init (audio only) ----
        self.sample_rate = 44100
        try:
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1, buffer=512)
        except Exception as e:
            messagebox.showerror("pygame.mixer init failed", str(e))
            raise

        self.channel = pygame.mixer.Channel(0)  # dedicated channel

        # ---- state ----
        self.running = False
        self.audio_thread = None
        self.sound_file = None
        self.sound_file_path = ""

        # ---- UI vars ----
        self.var_mode = tk.StringVar(value="tone")  # "tone" or "file"

        # danger mapping
        self.var_r = tk.DoubleVar(value=0.85)       # r = IAS/limit
        self.var_start = tk.DoubleVar(value=0.85)   # start threshold

        # pitch curve (tone)
        self.var_fmin = tk.IntVar(value=600)
        self.var_fmax = tk.IntVar(value=2200)
        self.var_pitch_pow = tk.DoubleVar(value=1.8)

        # tempo curve
        self.var_tmin = tk.DoubleVar(value=0.06)
        self.var_tmax = tk.DoubleVar(value=0.80)
        self.var_time_pow = tk.DoubleVar(value=2.2)

        # loudness curve
        self.var_vmin = tk.DoubleVar(value=0.15)  # pygame volume 0..1
        self.var_vmax = tk.DoubleVar(value=1.00)
        self.var_vol_pow = tk.DoubleVar(value=1.4)

        # tone duration
        self.var_dur_min = tk.IntVar(value=30)   # ms
        self.var_dur_max = tk.IntVar(value=70)   # ms

        # hysteresis / gating
        self.var_gate = tk.BooleanVar(value=True)
        self.var_release = tk.DoubleVar(value=0.82)  # when r falls below this, silence (if gating)

        # ---- Build UI ----
        self._build_ui()
        self.refresh()

        # Close handling
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = dict(padx=10, pady=4)

        # Mode row
        row0 = tk.Frame(self.root)
        row0.pack(fill="x", **pad)

        tk.Label(row0, text="Mode:").pack(side="left")
        tk.Radiobutton(row0, text="Tone (generated)", variable=self.var_mode, value="tone",
                       command=self.refresh).pack(side="left", padx=6)
        tk.Radiobutton(row0, text="File (selected)", variable=self.var_mode, value="file",
                       command=self.refresh).pack(side="left", padx=6)

        self.btn_choose = tk.Button(row0, text="Choose Audio File...", command=self.choose_file)
        self.btn_choose.pack(side="right")

        self.lbl_file = tk.Label(self.root, text="(no file)", anchor="w")
        self.lbl_file.pack(fill="x", padx=10, pady=(0, 6))

        # r slider
        row1 = tk.Frame(self.root)
        row1.pack(fill="x", **pad)
        tk.Label(row1, text="r = IAS/limit").pack(side="left")
        tk.Scale(row1, from_=0.6, to=1.1, resolution=0.001, orient="horizontal",
                 variable=self.var_r, length=360, command=lambda _=None: self.refresh()).pack(side="left", padx=8)

        # Grid params
        grid = tk.Frame(self.root)
        grid.pack(fill="x", padx=10, pady=4)

        def add_field(r, c, label, var, width=10):
            tk.Label(grid, text=label, width=14, anchor="w").grid(row=r, column=c * 2, sticky="w", pady=2)
            e = tk.Entry(grid, textvariable=var, width=width)
            e.grid(row=r, column=c * 2 + 1, sticky="w", pady=2)
            e.bind("<KeyRelease>", lambda _e: self.refresh())
            return e

        add_field(0, 0, "start", self.var_start)
        add_field(0, 1, "release", self.var_release)
        tk.Checkbutton(grid, text="Gate+Hysteresis", variable=self.var_gate, command=self.refresh)\
            .grid(row=0, column=4, columnspan=2, sticky="w")

        add_field(1, 0, "f_min (Hz)", self.var_fmin)
        add_field(1, 1, "f_max (Hz)", self.var_fmax)
        add_field(1, 2, "pitch_pow", self.var_pitch_pow)

        add_field(2, 0, "t_min (s)", self.var_tmin)
        add_field(2, 1, "t_max (s)", self.var_tmax)
        add_field(2, 2, "time_pow", self.var_time_pow)

        add_field(3, 0, "v_min (0-1)", self.var_vmin)
        add_field(3, 1, "v_max (0-1)", self.var_vmax)
        add_field(3, 2, "vol_pow", self.var_vol_pow)

        add_field(4, 0, "dur_min (ms)", self.var_dur_min)
        add_field(4, 1, "dur_max (ms)", self.var_dur_max)

        # Buttons
        row_btn = tk.Frame(self.root)
        row_btn.pack(fill="x", padx=10, pady=8)

        self.btn_toggle = tk.Button(row_btn, text="Start", command=self.toggle)
        self.btn_toggle.pack(side="left")

        tk.Button(row_btn, text="Gentle", command=lambda: self.apply_preset("gentle")).pack(side="left", padx=6)
        tk.Button(row_btn, text="Normal", command=lambda: self.apply_preset("normal")).pack(side="left")
        tk.Button(row_btn, text="Aggressive", command=lambda: self.apply_preset("aggressive")).pack(side="left", padx=6)

        tk.Button(row_btn, text="Stop Sound", command=self.stop_sound).pack(side="right")

        # Status
        self.lbl_status = tk.Label(self.root, text="", font=("Consolas", 12), anchor="w")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 10))

        # Hint
        hint = (
            "Tips:\n"
            "- Tone 模式可以真实做 pitch (频率变高)。\n"
            "- File 模式主要做“变大声 + 变密集”，pitch 变化需要重采样才像样（这里不做）。\n"
            "- start/release 配合 Gate 可防止阈值附近抖动一直响。\n"
        )
        tk.Label(self.root, text=hint, justify="left", anchor="w").pack(fill="x", padx=10, pady=(0, 10))

    # ---------------- Presets ----------------
    def apply_preset(self, name: str):
        if name == "gentle":
            self.var_start.set(0.88)
            self.var_release.set(0.85)
            self.var_fmin.set(550)
            self.var_fmax.set(1800)
            self.var_pitch_pow.set(2.1)
            self.var_tmax.set(0.90)
            self.var_tmin.set(0.09)
            self.var_time_pow.set(2.5)
            self.var_vmin.set(0.12)
            self.var_vmax.set(0.85)
            self.var_vol_pow.set(1.6)
            self.var_dur_min.set(40)
            self.var_dur_max.set(80)

        elif name == "normal":
            self.var_start.set(0.85)
            self.var_release.set(0.82)
            self.var_fmin.set(600)
            self.var_fmax.set(2200)
            self.var_pitch_pow.set(1.8)
            self.var_tmax.set(0.80)
            self.var_tmin.set(0.06)
            self.var_time_pow.set(2.2)
            self.var_vmin.set(0.15)
            self.var_vmax.set(1.00)
            self.var_vol_pow.set(1.4)
            self.var_dur_min.set(30)
            self.var_dur_max.set(70)

        else:  # aggressive
            self.var_start.set(0.82)
            self.var_release.set(0.79)
            self.var_fmin.set(700)
            self.var_fmax.set(2600)
            self.var_pitch_pow.set(1.4)
            self.var_tmax.set(0.60)
            self.var_tmin.set(0.04)
            self.var_time_pow.set(1.8)
            self.var_vmin.set(0.20)
            self.var_vmax.set(1.00)
            self.var_vol_pow.set(1.2)
            self.var_dur_min.set(25)
            self.var_dur_max.set(60)

        self.refresh()

    # ---------------- Core mapping ----------------
    def calc(self):
        # read vars (with basic clamping)
        r = float(self.var_r.get())

        start = clamp(float(self.var_start.get()), 0.5, 0.99)
        release = clamp(float(self.var_release.get()), 0.4, start)  # release <= start

        u = (r - start) / (1.0 - start)
        u = clamp(u, 0.0, 1.0)

        fmin = int(self.var_fmin.get())
        fmax = int(self.var_fmax.get())
        fmin = max(50, fmin)
        fmax = max(fmin + 1, fmax)

        ppow = max(0.1, float(self.var_pitch_pow.get()))

        tmin = clamp(float(self.var_tmin.get()), 0.01, 5.0)
        tmax = clamp(float(self.var_tmax.get()), 0.01, 5.0)
        if tmax < tmin:
            tmax = tmin

        tpow = max(0.1, float(self.var_time_pow.get()))

        vmin = clamp(float(self.var_vmin.get()), 0.0, 1.0)
        vmax = clamp(float(self.var_vmax.get()), 0.0, 1.0)
        if vmax < vmin:
            vmax = vmin

        vpow = max(0.1, float(self.var_vol_pow.get()))

        dur_min = int(self.var_dur_min.get())
        dur_max = int(self.var_dur_max.get())
        dur_min = clamp(dur_min, 10, 500)
        dur_max = clamp(dur_max, 10, 500)
        if dur_max < dur_min:
            dur_max = dur_min

        # curves
        freq = int(fmin + (fmax - fmin) * (u ** ppow))
        interval = tmin + (tmax - tmin) * ((1.0 - u) ** tpow)
        volume = vmin + (vmax - vmin) * (u ** vpow)

        # duration: 越危险越短更“急”
        dur_ms = int(dur_max - (dur_max - dur_min) * u)

        return {
            "r": r,
            "start": start,
            "release": release,
            "u": u,
            "freq": freq,
            "interval": interval,
            "volume": volume,
            "dur_ms": dur_ms,
        }

    def refresh(self):
        d = self.calc()
        mode = self.var_mode.get()

        self.lbl_status.config(
            text=(
                f"mode={mode:<4}  "
                f"r={d['r']:.3f}  start={d['start']:.3f}  release={d['release']:.3f}  u={d['u']:.3f}  "
                f"freq={d['freq']}Hz  interval={d['interval']:.3f}s  vol={d['volume']:.2f}  dur={d['dur_ms']}ms"
            )
        )

        if mode == "file":
            self.btn_choose.config(state="normal")
        else:
            self.btn_choose.config(state="disabled")

    # ---------------- Audio generation ----------------
    def make_tone_sound(self, freq_hz: int, dur_ms: int, volume: float) -> pygame.mixer.Sound:
        """
        生成单声道 16-bit PCM 正弦波，返回 pygame Sound
        """
        n_samples = int(self.sample_rate * (dur_ms / 1000.0))
        n_samples = max(1, n_samples)

        # amplitude: avoid clipping
        amp = int(32767 * 0.6)
        buf = array("h")
        step = 2.0 * math.pi * freq_hz / self.sample_rate

        # 简单淡入淡出，降低 click（2ms）
        fade = int(self.sample_rate * 0.002)
        fade = max(1, min(fade, n_samples // 2))

        for i in range(n_samples):
            s = math.sin(step * i)
            v = int(amp * s)

            # fade in/out
            if i < fade:
                v = int(v * (i / fade))
            elif i > n_samples - fade:
                v = int(v * ((n_samples - i) / fade))

            buf.append(v)

        sound = pygame.mixer.Sound(buffer=buf.tobytes())
        sound.set_volume(clamp(volume, 0.0, 1.0))
        return sound

    def stop_sound(self):
        try:
            self.channel.stop()
        except:
            pass

    # ---------------- File selection ----------------
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Choose audio file",
            filetypes=[
                ("Audio files", "*.wav *.ogg *.mp3"),
                ("WAV", "*.wav"),
                ("OGG", "*.ogg"),
                ("MP3", "*.mp3"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            snd = pygame.mixer.Sound(path)
        except Exception as e:
            messagebox.showerror("Load audio failed", f"{e}\n\n建议优先使用 WAV/OGG。")
            return

        self.sound_file = snd
        self.sound_file_path = path
        self.lbl_file.config(text=path)

    # ---------------- Start/Stop ----------------
    def toggle(self):
        self.running = not self.running
        self.btn_toggle.config(text="Stop" if self.running else "Start")

        if self.running and (self.audio_thread is None or not self.audio_thread.is_alive()):
            self.audio_thread = threading.Thread(target=self.audio_loop, daemon=True)
            self.audio_thread.start()

    def audio_loop(self):
        """
        独立线程：根据当前参数实时播放（避免阻塞 UI）
        """
        latched_on = False  # for gate/hysteresis

        while self.running:
            d = self.calc()
            mode = self.var_mode.get()
            gate = bool(self.var_gate.get())

            r = d["r"]
            start = d["start"]
            release = d["release"]
            u = d["u"]

            # gating + hysteresis
            if gate:
                if not latched_on and r >= start:
                    latched_on = True
                elif latched_on and r <= release:
                    latched_on = False
            else:
                latched_on = (u > 0.0)

            if not latched_on:
                # ensure silence and sleep a bit
                self.stop_sound()
                time.sleep(0.03)
                continue

            # If we are latched_on, play according to u
            if mode == "tone":
                try:
                    snd = self.make_tone_sound(d["freq"], d["dur_ms"], d["volume"])
                    self.channel.play(snd)
                except:
                    pass

            else:  # file
                if self.sound_file is None:
                    # no file loaded -> silently fallback to tone so demo is still usable
                    try:
                        snd = self.make_tone_sound(d["freq"], d["dur_ms"], d["volume"])
                        self.channel.play(snd)
                    except:
                        pass
                else:
                    try:
                        self.sound_file.set_volume(d["volume"])
                        # 用 dedicated channel：每次触发都重播（节奏更清晰）
                        self.channel.play(self.sound_file)
                    except:
                        pass

            time.sleep(max(0.0, d["interval"]))

        # leaving loop
        self.stop_sound()

    def on_close(self):
        self.running = False
        try:
            self.stop_sound()
        except:
            pass
        try:
            pygame.mixer.quit()
        except:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AlarmCurvePygameDemo(root)
    root.mainloop()
