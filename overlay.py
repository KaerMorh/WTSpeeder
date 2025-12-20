import requests
import tkinter as tk
from tkinter import colorchooser, messagebox
import threading
import time
import json
import os
import sys

# === 托盘图标库 ===
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# ================= 默认配置 =================
DEFAULT_CONFIG = {
    "x": 85,
    "y": 730,
    "font_size": 18,
    "font_color": "#00FF00",     # 默认亮绿色
    "text_prefix": "IAS: ",      # 前缀文本
    "update_rate": 30            # 默认 30 Hz
}

APP_NAME = "WTOverlay"     # 在 AppData 里创建的文件夹名
FONT_NAME = "Consolas" 
# ===========================================

class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WT Speed Monitor")
        
        # 1. 路径处理：使用 AppData (行业标准)
        self.config_path = self.get_config_path()
        
        # 2. 读取配置
        self.cfg = self.load_config()

        # 3. 窗口基础设置
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.config(bg='black')
        self.root.wm_attributes("-transparentcolor", "black")
        
        # 防止第一次坐标在屏幕外
        safe_x = max(0, self.cfg['x'])
        safe_y = max(0, self.cfg['y'])
        self.root.geometry(f"+{safe_x}+{safe_y}")
        
        # 4. UI 布局
        self.frame = tk.Frame(root, bg='black')
        self.frame.pack(fill=tk.BOTH, expand=True)

        # 左侧圆圈 (手柄)
        self.canvas = tk.Canvas(self.frame, width=30, height=40, bg='black', highlightthickness=0)
        self.canvas.pack(side=tk.LEFT)
        self.handle = self.canvas.create_oval(5, 10, 25, 30, fill='#404040', stipple='gray50', outline=self.cfg['font_color'], width=2)

        # 右侧文字
        self.label = tk.Label(self.frame, text="Wait...", 
                              font=(FONT_NAME, self.cfg['font_size'], "bold"), 
                              fg=self.cfg['font_color'], bg='black')
        self.label.pack(side=tk.LEFT)
        
        # 5. 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="⚙ 设置 (Settings)", command=self.open_settings_window)
        self.context_menu.add_command(label="👁 隐藏 (Hide)", command=self.hide_window)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="❌ 退出 (Exit)", command=self.quit_app)

        # 6. 事件绑定
        for widget in [self.canvas, self.label]:
            widget.bind("<Button-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)
            widget.bind("<ButtonRelease-1>", self.stop_move)
            widget.bind("<Button-3>", self.show_context_menu)
        
        # 7. 启动线程
        self.is_running = True
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()
        
        self.thread = threading.Thread(target=self.update_data_loop)
        self.thread.daemon = True
        self.thread.start()

    # ================= 路径逻辑 =================
    def get_config_path(self):
        """获取 AppData/Roaming 下的配置文件路径"""
        app_data = os.getenv('APPDATA')
        config_dir = os.path.join(app_data, APP_NAME)
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
            except Exception as e:
                print(f"创建文件夹失败: {e}")
                return "config.json"
        
        return os.path.join(config_dir, "config.json")

    # ================= 设置窗口逻辑 =================
    def open_settings_window(self):
        if hasattr(self, 'setting_win') and self.setting_win.winfo_exists():
            self.setting_win.lift()
            return

        self.setting_win = tk.Toplevel(self.root)
        self.setting_win.title("设置 - 战雷速度监视器")
        self.setting_win.geometry("340x380")
        self.setting_win.attributes("-topmost", True)
        
        pad_opts = {'padx': 10, 'pady': 5}
        
        # 1. 文本前缀
        tk.Label(self.setting_win, text="显示前缀:").pack(**pad_opts)
        self.entry_prefix = tk.Entry(self.setting_win, width=30)
        self.entry_prefix.insert(0, self.cfg.get('text_prefix', "IAS: "))
        self.entry_prefix.pack()

        # 2. 字号大小
        tk.Label(self.setting_win, text="字体大小:").pack(**pad_opts)
        self.scale_size = tk.Scale(self.setting_win, from_=10, to=60, orient=tk.HORIZONTAL, length=200)
        self.scale_size.set(self.cfg['font_size'])
        self.scale_size.pack()

        # 3. 刷新频率
        tk.Label(self.setting_win, text="刷新频率 (Hz/次每秒):").pack(**pad_opts)
        self.scale_rate = tk.Scale(self.setting_win, from_=5, to=30, resolution=1, orient=tk.HORIZONTAL, length=200)
        self.scale_rate.set(self.cfg.get('update_rate', 30))
        self.scale_rate.pack()

        # 4. 颜色选择
        tk.Label(self.setting_win, text="文字颜色 (Hex):").pack(**pad_opts)
        color_frame = tk.Frame(self.setting_win)
        color_frame.pack()
        
        self.color_preview = tk.Label(color_frame, text="    ", bg=self.cfg['font_color'], relief="solid", borderwidth=1)
        self.color_preview.pack(side=tk.LEFT, padx=5)
        
        self.entry_hex = tk.Entry(color_frame, width=10)
        self.entry_hex.insert(0, self.cfg['font_color'])
        self.entry_hex.pack(side=tk.LEFT, padx=5)
        
        tk.Button(color_frame, text="调色盘", command=self.choose_color).pack(side=tk.LEFT, padx=5)

        # 5. 按钮区
        btn_frame = tk.Frame(self.setting_win)
        btn_frame.pack(pady=20, fill=tk.X, padx=20)

        # 恢复默认
        tk.Button(btn_frame, text="恢复默认", command=self.restore_defaults, fg="red").pack(side=tk.LEFT)
        
        # 保存并关闭
        tk.Button(btn_frame, text="保存并关闭", command=self.save_settings_from_ui, bg="#DDDDDD", width=15).pack(side=tk.RIGHT)

        # 仅保存
        tk.Button(btn_frame, text="保存", command=self.apply_settings, width=10).pack(side=tk.RIGHT, padx=5)

    def choose_color(self):
        current_hex = self.entry_hex.get()
        try:
            color = colorchooser.askcolor(title="选择颜色", color=current_hex)
        except:
            color = colorchooser.askcolor(title="选择颜色")
            
        if color[1]:
            self.entry_hex.delete(0, tk.END)
            self.entry_hex.insert(0, color[1])
            self.color_preview.config(bg=color[1])

    def restore_defaults(self):
        """恢复默认设置 (除了位置)，且不关闭窗口"""
        if messagebox.askyesno("确认", "确定要恢复默认设置吗？\n(位置不会改变，但颜色、大小、频率会重置)"):
            # 1. 重置配置数据 (保留坐标)
            current_x = self.cfg['x']
            current_y = self.cfg['y']
            
            self.cfg = DEFAULT_CONFIG.copy()
            self.cfg['x'] = current_x
            self.cfg['y'] = current_y
            
            # 2. 刷新设置窗口的 UI 控件值
            self.entry_prefix.delete(0, tk.END)
            self.entry_prefix.insert(0, self.cfg['text_prefix'])
            
            self.scale_size.set(self.cfg['font_size'])
            self.scale_rate.set(self.cfg['update_rate'])
            
            self.entry_hex.delete(0, tk.END)
            self.entry_hex.insert(0, self.cfg['font_color'])
            self.color_preview.config(bg=self.cfg['font_color'])
            
            # 3. 立即应用到悬浮窗 (无需点击保存)
            self.label.config(font=(FONT_NAME, self.cfg['font_size'], "bold"), fg=self.cfg['font_color'])
            self.canvas.itemconfig(self.handle, outline=self.cfg['font_color'])
            
            # 4. 保存配置到文件
            self.save_config_file()
            
            # 5. 提示成功 (但不关闭窗口)
            messagebox.showinfo("提示", "已恢复默认设置！")

    def apply_settings(self):
        new_prefix = self.entry_prefix.get()
        new_size = self.scale_size.get()
        new_rate = self.scale_rate.get()
        new_color = self.entry_hex.get()
        
        try:
            self.root.winfo_rgb(new_color)
        except:
            messagebox.showerror("颜色错误", "颜色代码无效！")
            return False

        self.cfg['text_prefix'] = new_prefix
        self.cfg['font_size'] = new_size
        self.cfg['font_color'] = new_color
        self.cfg['update_rate'] = new_rate
        
        # 应用
        self.label.config(font=(FONT_NAME, new_size, "bold"), fg=new_color)
        self.canvas.itemconfig(self.handle, outline=new_color)
        self.color_preview.config(bg=new_color)
        self.update_text(self.label.cget("text")) 
        self.save_config_file()
        return True

    def save_settings_from_ui(self):
        if self.apply_settings():
            # 只有点击右下角的“保存并关闭”才会关闭窗口
            if hasattr(self, 'setting_win') and self.setting_win.winfo_exists():
                self.setting_win.destroy()

    # ================= 配置文件逻辑 =================
    def load_config(self):
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    config.update(saved)
            except:
                pass
        # 兼容性处理：如果 update_rate 不存在，使用默认值
        if 'update_rate' not in config:
            config['update_rate'] = 30
        return config

    def save_config_file(self):
        self.cfg['x'] = self.root.winfo_x()
        self.cfg['y'] = self.root.winfo_y()
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, indent=4)
        except Exception as e:
            print(f"保存配置失败: {e}")

    # ================= 托盘与系统 =================
    def create_tray_image(self):
        image = Image.new('RGB', (64, 64), color=(0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((8, 8, 56, 56), fill=(57, 217, 33))
        return image

    def setup_tray_icon(self):
        image = self.create_tray_image()
        menu = (
            item('⚙ 设置 (Settings)', self.open_settings_window_safely),
            item('显示/隐藏 (Show/Hide)', self.toggle_window),
            item('重置位置 (Reset Pos)', self.reset_position),
            item('退出 (Exit)', self.quit_app)
        )
        self.icon = pystray.Icon("WT_Counter", image, "战雷速度监视器", menu)
        self.icon.run()

    def open_settings_window_safely(self, icon=None, item=None):
        self.root.after(0, self.open_settings_window)

    def toggle_window(self, icon=None, item=None):
        if self.root.state() == 'normal':
            self.root.after(0, self.root.withdraw)
        else:
            self.root.after(0, self.root.deiconify)

    def hide_window(self):
        self.root.withdraw()

    def quit_app(self, icon=None, item=None):
        self.is_running = False
        if hasattr(self, 'icon'):
            self.icon.stop()
        self.root.after(0, self.root.destroy)

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def reset_position(self, icon=None, item=None):
        def _reset():
            self.root.deiconify()
            self.root.geometry(f"+{DEFAULT_CONFIG['x']}+{DEFAULT_CONFIG['y']}")
            self.save_config_file()
        self.root.after(0, _reset)

    # ================= 拖拽逻辑 =================
    def start_move(self, event):
        self.last_x = event.x_root
        self.last_y = event.y_root

    def do_move(self, event):
        deltax = event.x_root - self.last_x
        deltay = event.y_root - self.last_y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
        self.last_x = event.x_root
        self.last_y = event.y_root

    def stop_move(self, event):
        self.save_config_file()

    # ================= 数据循环 =================
    def update_text(self, text):
        if self.root.state() == 'normal':
            self.label.config(text=text)

    def get_ias(self):
        try:
            # timeout 0.05s for high frequency polling
            response = requests.get('http://127.0.0.1:8111/state', timeout=0.05)
            data = response.json()
            if data.get('valid') is True:
                val = data.get('IAS, km/h')
                return int(val) if val is not None else None
            return None
        except:
            return None

    def update_data_loop(self):
        while self.is_running:
            ias = self.get_ias()
            prefix = self.cfg.get('text_prefix', "IAS: ")
            
            if ias is None:
                display_text = f"{prefix}?"
            else:
                display_text = f"{prefix}{ias}"
            
            try:
                self.root.after(0, self.update_text, display_text)
            except:
                break
            
            rate = self.cfg.get('update_rate', 30)
            if rate <= 0: rate = 1
            if rate > 60: rate = 60 # Cap at 60 just in case
            time.sleep(1.0 / rate)

if __name__ == "__main__":
    root = tk.Tk()
    app = OverlayApp(root)
    root.mainloop()
