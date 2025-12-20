import tkinter as tk
from tkinter import ttk
import pygame
import numpy as np
import threading
import time
import json

class SoundEngine:
    def __init__(self):
        try:
            pygame.mixer.pre_init(44100, -16, 1, 512)
            pygame.mixer.init()
            self.ready = True
            self.channel = pygame.mixer.Channel(0) 
        except Exception as e:
            print(f"Audio init failed: {e}")
            self.ready = False

        self.last_beep_time = 0
        self.is_running = True
        self.current_params = {}
        self.current_speed_pct = 0.0
        
        # Internal scaler because raw waves are too loud
        # If user sets vol=100%, we actually use 0.2 internally
        self.internal_gain = 0.1 
        self.master_volume = 0.5 
        
        self.continuous_sound = None
        self.is_continuous_active = False

    def generate_tone(self, frequency, duration_ms, volume=1.0, waveform='square'):
        if not self.ready: return None
        
        sample_rate = 44100
        n_samples = int(sample_rate * (duration_ms / 1000.0))
        
        t = np.linspace(0, duration_ms / 1000.0, n_samples, False)
        
        # Waveform generation
        if waveform == 'sine':
            wave = np.sin(2 * np.pi * frequency * t)
        elif waveform == 'triangle':
            # Simple triangle approximation
            wave = 2 * np.abs(2 * (t * frequency - np.floor(t * frequency + 0.5))) - 1
        else: # square
            wave = np.sign(np.sin(2 * np.pi * frequency * t))
            # Smooth out square wave slightly to reduce harshness?
            # A simple way is to limit the slew rate or just rely on envelope
        
        # Envelope (Fade In/Out) - Increased length to reduce popping
        # 5ms fade is usually enough to stop clicking, but let's do 10% or max 200 samples
        fade_len = int(min(200, n_samples * 0.15)) 
        if fade_len > 0:
            fade_in = np.linspace(0.0, 1.0, fade_len)
            fade_out = np.linspace(1.0, 0.0, fade_len)
            wave[:fade_len] *= fade_in
            wave[-fade_len:] *= fade_out
            
        # Volume scaling
        # User Volume * Internal Gain * Local Event Volume
        final_vol = volume * self.master_volume * self.internal_gain
        
        # Clip to prevent overflow
        wave = np.clip(wave * final_vol, -1.0, 1.0)
        
        wave = (wave * 32767).astype(np.int16)
        
        try:
            _, _, channels = pygame.mixer.get_init()
            if channels == 2:
                wave = np.column_stack((wave, wave))
        except:
             if wave.ndim == 1:
                 wave = np.column_stack((wave, wave))

        return pygame.sndarray.make_sound(wave)

    def logic_loop(self, update_ui_callback):
        while self.is_running:
            params = self.current_params
            speed = self.current_speed_pct 
            
            threshold = params.get('threshold', 95) / 100.0
            min_freq = params.get('min_freq', 712)
            max_freq = params.get('max_freq', 850)
            min_interval = params.get('min_interval', 146) 
            max_interval = params.get('max_interval', 61)
            pulse_dur = params.get('pulse_dur', 88)
            waveform = params.get('waveform', 'square')
            
            if speed >= threshold:
                now = time.time() * 1000 
                
                if speed >= 1.0:
                    intensity = 1.0
                else:
                    intensity = (speed - threshold) / (1.0 - threshold)
                    intensity = max(0.0, min(1.0, intensity))
                
                current_interval = min_interval - (min_interval - max_interval) * intensity
                current_interval = max(10, current_interval)
                
                current_freq = min_freq + (max_freq - min_freq) * intensity
                
                # Continuous Check
                if current_interval < pulse_dur:
                    if not self.is_continuous_active:
                        # Generate Loop
                        loop_sound = self.generate_tone(max_freq, 1000, volume=1.0, waveform=waveform) 
                        if loop_sound:
                            self.channel.play(loop_sound, loops=-1)
                            self.is_continuous_active = True
                            if update_ui_callback: update_ui_callback(True)
                    else:
                         # Update volume if changed?
                         # self.channel.set_volume(self.master_volume) 
                         pass
                else:
                    if self.is_continuous_active:
                        self.channel.stop()
                        self.is_continuous_active = False
                        if update_ui_callback: update_ui_callback(False)
                    
                    if now - self.last_beep_time >= current_interval:
                        sound = self.generate_tone(current_freq, pulse_dur, volume=1.0, waveform=waveform)
                        if sound:
                            self.channel.play(sound)
                        
                        self.last_beep_time = now
                        if update_ui_callback: update_ui_callback(intensity)

            else:
                if self.is_continuous_active:
                    self.channel.stop()
                    self.is_continuous_active = False
                    if update_ui_callback: update_ui_callback(False)

            time.sleep(0.01) 

    def stop(self):
        self.is_running = False
        if self.ready:
            self.channel.stop()
        pygame.quit()


class TunerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sound Lab - WTFriendCounter")
        self.root.geometry("600x800")
        
        self.engine = SoundEngine()
        
        style = ttk.Style()
        style.configure("TLabel", font=("Segoe UI", 10))
        
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Simulation Section ---
        sim_frame = ttk.LabelFrame(main_frame, text=" ✈ Flight Simulation ", padding="10")
        sim_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.var_speed = tk.DoubleVar(value=0)
        ttk.Label(sim_frame, text="Current Speed % (IAS / Limit):").pack(anchor=tk.W)
        self.scale_speed = ttk.Scale(sim_frame, from_=0, to=120, orient=tk.HORIZONTAL, 
                                     variable=self.var_speed, command=self.update_engine)
        self.scale_speed.pack(fill=tk.X, pady=5)
        self.lbl_speed_val = ttk.Label(sim_frame, text="0%", font=("Consolas", 14, "bold"))
        self.lbl_speed_val.pack(anchor=tk.CENTER)
        
        self.canvas_led = tk.Canvas(sim_frame, width=40, height=40, highlightthickness=0)
        self.canvas_led.pack(side=tk.RIGHT)
        self.led = self.canvas_led.create_oval(5, 5, 35, 35, fill="#333333", outline="")

        # --- Volume Section ---
        vol_frame = ttk.LabelFrame(main_frame, text=" 🔊 Master Volume ", padding="10")
        vol_frame.pack(fill=tk.X, pady=(0, 20))
        # Default volume very low as requested (0.5 out of 100)
        self.var_vol = tk.DoubleVar(value=0.5) 
        self.scale_vol = ttk.Scale(vol_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                   variable=self.var_vol, command=self.update_volume)
        self.scale_vol.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.lbl_vol = ttk.Label(vol_frame, text="0.5%", width=6)
        self.lbl_vol.pack(side=tk.LEFT, padx=5)

        # --- Parameters Section ---
        param_frame = ttk.LabelFrame(main_frame, text=" 🎛 Audio Parameters ", padding="10")
        param_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Default Params from User
        self.params = {
            'threshold': tk.IntVar(value=95),
            'min_freq': tk.IntVar(value=712),
            'max_freq': tk.IntVar(value=850),
            'min_interval': tk.IntVar(value=146),
            'max_interval': tk.IntVar(value=61),
            'pulse_dur': tk.IntVar(value=88),
            'waveform': tk.StringVar(value='square')
        }
        
        # Waveform Selector
        wf_frame = ttk.Frame(param_frame)
        wf_frame.pack(fill=tk.X, pady=5)
        ttk.Label(wf_frame, text="Waveform Type:", width=20).pack(side=tk.LEFT)
        modes = [("Square (Sharp)", "square"), ("Sine (Soft)", "sine"), ("Triangle (Balanced)", "triangle")]
        for text, mode in modes:
            ttk.Radiobutton(wf_frame, text=text, variable=self.params['waveform'], value=mode, command=self.update_engine).pack(side=tk.LEFT, padx=10)

        def create_param_slider(parent, label, key, from_, to_):
            f = ttk.Frame(parent)
            f.pack(fill=tk.X, pady=5)
            ttk.Label(f, text=label, width=20).pack(side=tk.LEFT)
            s = ttk.Scale(f, from_=from_, to=to_, variable=self.params[key], orient=tk.HORIZONTAL, command=self.update_engine)
            s.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            l = ttk.Label(f, textvariable=self.params[key], width=5)
            l.pack(side=tk.LEFT)
            return s

        create_param_slider(param_frame, "Start Threshold (%)", 'threshold', 50, 99)
        create_param_slider(param_frame, "Start Frequency (Hz)", 'min_freq', 100, 2000)
        create_param_slider(param_frame, "End Frequency (Hz)", 'max_freq', 100, 2000)
        create_param_slider(param_frame, "Slow Interval (ms)", 'min_interval', 10, 1000)
        create_param_slider(param_frame, "Fast Interval (ms)", 'max_interval', 10, 1000)
        create_param_slider(param_frame, "Pulse Length (ms)", 'pulse_dur', 20, 500)

        # --- Import/Export Section ---
        io_frame = ttk.Frame(main_frame)
        io_frame.pack(fill=tk.X)
        
        ttk.Button(io_frame, text="Copy Config", command=self.copy_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(io_frame, text="Paste Config", command=self.paste_config).pack(side=tk.LEFT, padx=5)
        self.lbl_status = ttk.Label(io_frame, text="", foreground="green")
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Start Thread
        self.update_volume()
        self.update_engine() 
        self.thread = threading.Thread(target=self.engine.logic_loop, args=(self.update_led_state,), daemon=True)
        self.thread.start()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_volume(self, _=None):
        val = self.var_vol.get()
        self.lbl_vol.config(text=f"{val:.1f}%")
        self.engine.master_volume = val / 100.0
        
        # Force continuous regeneration for volume update
        if self.engine.is_continuous_active:
            self.engine.channel.stop()
            self.engine.is_continuous_active = False

    def update_engine(self, _=None):
        val = self.var_speed.get()
        self.lbl_speed_val.config(text=f"{val:.1f}%")
        self.engine.current_speed_pct = val / 100.0
        
        p = {}
        for k, v in self.params.items():
            p[k] = v.get()
        self.engine.current_params = p

    def update_led_state(self, state):
        if not self.root.winfo_exists(): return
        def _set_color(color):
             try: self.canvas_led.itemconfig(self.led, fill=color)
             except: pass
        if state is True: self.root.after(0, lambda: _set_color("#FF0000"))
        elif state is False: self.root.after(0, lambda: _set_color("#333333"))
        else:
             self.root.after(0, lambda: _set_color("#FF0000"))
             self.root.after(int(self.params['pulse_dur'].get()), lambda: _set_color("#333333"))

    def copy_config(self):
        p = {}
        for k, v in self.params.items():
            p[k] = v.get()
        p['volume'] = round(self.var_vol.get(), 2) # Keep float precision
        
        json_str = json.dumps(p, indent=4)
        self.root.clipboard_clear()
        self.root.clipboard_append(json_str)
        self.lbl_status.config(text="Copied!")
        self.root.after(2000, lambda: self.lbl_status.config(text=""))

    def paste_config(self):
        try:
            content = self.root.clipboard_get()
            data = json.loads(content)
            
            # Apply values safely
            if 'volume' in data:
                self.var_vol.set(float(data['volume']))
                self.update_volume()
            
            for k in self.params:
                if k in data:
                    self.params[k].set(data[k])
            
            self.update_engine()
            self.lbl_status.config(text="Imported!")
            self.root.after(2000, lambda: self.lbl_status.config(text=""))
        except Exception as e:
            self.lbl_status.config(text="Invalid JSON", foreground="red")
            print(e)

    def on_close(self):
        self.engine.stop()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TunerApp(root)
    root.mainloop()
