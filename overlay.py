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
    "warn_color": "#FF0000",     # 警告红色
    "text_prefix": "IAS: ",      # 前缀文本
    "update_rate": 30,           # 默认 30 Hz
    "warn_percent": 95,          # 警告阈值 (70-95)
    "unit": "km/h",              # km/h, kt, mph
    "show_unit": True,           # 是否显示单位
    "smart_hide": True           # 默认开启智能隐藏 (仅在空战中显示)
}

APP_NAME = "WTFriendCounter"     # 在 AppData 里创建的文件夹名
FONT_NAME = "Consolas" 
# ===========================================

class FM_DB:
    """处理飞机气动数据加载"""
    def __init__(self):
        self.crit_speeds = {} # { "plane_type_id": float_speed_kmh }
        self.load_db()
        
    def load_db(self):
        # 尝试定位 FM/fm_data_db.csv
        # 假设脚本在项目根目录，FM在 ./FM
        base_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(base_dir, "FM", "fm_data_db.csv")
        
        if not os.path.exists(csv_path):
            print(f"警告: 找不到数据文件 {csv_path}")
            return
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # 跳过第一行 Header
                next(f) 
                for line in f:
                    parts = line.strip().split(';')
                    if len(parts) >= 7:
                        name = parts[0]
                        try:
                            crit_spd = float(parts[6]) # CritAirSpd (index 6)
                            self.crit_speeds[name] = crit_spd
                        except ValueError:
                            pass
            print(f"成功加载 {len(self.crit_speeds)} 条飞机数据")
        except Exception as e:
            print(f"加载数据库出错: {e}")

    def get_limit(self, plane_type):
        return self.crit_speeds.get(plane_type)

class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WT Speed Monitor")
        
        # 加载数据库
        self.fm_db = FM_DB()
        
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
        # 移除固定大小，使用自适应 (方案 1)
        # self.setting_win.geometry("380x550")
        self.setting_win.attributes("-topmost", True)
        
        # 减少间距 (方案 3)
        pad_opts = {'padx': 10, 'pady': 2}
        
        # 1. 文本前缀
        row1 = tk.Frame(self.setting_win)
        row1.pack(fill=tk.X, **pad_opts)
        tk.Label(row1, text="显示前缀:").pack(side=tk.LEFT)
        self.entry_prefix = tk.Entry(row1, width=15)
        self.entry_prefix.insert(0, self.cfg.get('text_prefix', "IAS: "))
        self.entry_prefix.pack(side=tk.RIGHT)

        # 2. 字号大小
        row2 = tk.Frame(self.setting_win)
        row2.pack(fill=tk.X, **pad_opts)
        tk.Label(row2, text="字体大小:").pack(side=tk.LEFT)
        self.scale_size = tk.Scale(row2, from_=10, to=60, orient=tk.HORIZONTAL, length=150)
        self.scale_size.set(self.cfg['font_size'])
        self.scale_size.pack(side=tk.RIGHT)

        # 3. 刷新频率
        row3 = tk.Frame(self.setting_win)
        row3.pack(fill=tk.X, **pad_opts)
        tk.Label(row3, text="刷新频率 (Hz):").pack(side=tk.LEFT)
        self.scale_rate = tk.Scale(row3, from_=5, to=30, resolution=1, orient=tk.HORIZONTAL, length=150)
        self.scale_rate.set(self.cfg.get('update_rate', 30))
        self.scale_rate.pack(side=tk.RIGHT)

        # 4. 颜色设置 (正常 + 警告) - 合并在一行或两行紧凑显示
        tk.Label(self.setting_win, text="[颜色设置]").pack(pady=(5, 0))
        
        color_frame = tk.Frame(self.setting_win)
        color_frame.pack(fill=tk.X, **pad_opts)
        
        # 正常颜色
        f_norm = tk.Frame(color_frame)
        f_norm.pack(side=tk.LEFT, padx=5)
        tk.Label(f_norm, text="正常:").pack(side=tk.LEFT)
        self.color_preview = tk.Label(f_norm, text="  ", bg=self.cfg['font_color'], relief="solid", width=3)
        self.color_preview.pack(side=tk.LEFT, padx=2)
        self.entry_hex = tk.Entry(f_norm, width=7)
        self.entry_hex.insert(0, self.cfg['font_color'])
        self.entry_hex.pack(side=tk.LEFT)
        tk.Button(f_norm, text="选", command=lambda: self.choose_color(self.entry_hex, self.color_preview), width=3).pack(side=tk.LEFT)

        # 警告颜色
        f_warn = tk.Frame(color_frame)
        f_warn.pack(side=tk.RIGHT, padx=5)
        tk.Label(f_warn, text="警告:").pack(side=tk.LEFT)
        self.warn_preview = tk.Label(f_warn, text="  ", bg=self.cfg.get('warn_color', '#FF0000'), relief="solid", width=3)
        self.warn_preview.pack(side=tk.LEFT, padx=2)
        self.entry_warn = tk.Entry(f_warn, width=7)
        self.entry_warn.insert(0, self.cfg.get('warn_color', '#FF0000'))
        self.entry_warn.pack(side=tk.LEFT)
        tk.Button(f_warn, text="选", command=lambda: self.choose_color(self.entry_warn, self.warn_preview), width=3).pack(side=tk.LEFT)

        # 5. 警告阈值
        row5 = tk.Frame(self.setting_win)
        row5.pack(fill=tk.X, **pad_opts)
        tk.Label(row5, text="警告阈值 (%):").pack(side=tk.LEFT)
        self.scale_warn_pct = tk.Scale(row5, from_=70, to=100, orient=tk.HORIZONTAL, length=150)
        self.scale_warn_pct.set(self.cfg.get('warn_percent', 90))
        self.scale_warn_pct.pack(side=tk.RIGHT)

        # 6. 单位选择
        tk.Label(self.setting_win, text="[单位设置]").pack(pady=(5, 0))
        unit_frame = tk.Frame(self.setting_win)
        unit_frame.pack(**pad_opts)
        self.var_unit = tk.StringVar(value=self.cfg.get('unit', 'km/h'))
        for u in ['km/h', 'kt', 'mph']:
            tk.Radiobutton(unit_frame, text=u, variable=self.var_unit, value=u).pack(side=tk.LEFT)
            
        self.var_show_unit = tk.BooleanVar(value=self.cfg.get('show_unit', True))
        tk.Checkbutton(self.setting_win, text="显示单位文字", variable=self.var_show_unit).pack(pady=0)

        # 7. 智能隐藏
        self.var_smart = tk.BooleanVar(value=self.cfg.get('smart_hide', True))
        tk.Checkbutton(self.setting_win, text="智能隐藏 (仅在空战中显示数值)", variable=self.var_smart).pack(pady=0)

        # 8. 按钮区
        btn_frame = tk.Frame(self.setting_win)
        btn_frame.pack(pady=10, fill=tk.X, padx=10)
        tk.Button(btn_frame, text="恢复默认", command=self.restore_defaults, fg="red").pack(side=tk.LEFT)
        tk.Button(btn_frame, text="保存并关闭", command=self.save_settings_from_ui, bg="#DDDDDD").pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="保存", command=self.apply_settings).pack(side=tk.RIGHT, padx=5)

    def choose_color(self, entry_widget, preview_widget):
        current_hex = entry_widget.get()
        try:
            color = colorchooser.askcolor(title="选择颜色", color=current_hex)
        except:
            color = colorchooser.askcolor(title="选择颜色")
            
        if color[1]:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, color[1])
            preview_widget.config(bg=color[1])

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

            self.entry_warn.delete(0, tk.END)
            self.entry_warn.insert(0, self.cfg['warn_color'])
            self.warn_preview.config(bg=self.cfg['warn_color'])
            
            self.scale_warn_pct.set(self.cfg['warn_percent'])
            self.var_unit.set(self.cfg['unit'])
            self.var_show_unit.set(self.cfg['show_unit'])
            self.var_smart.set(self.cfg['smart_hide'])
            
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
        new_warn = self.entry_warn.get()
        
        new_warn_pct = self.scale_warn_pct.get()
        new_unit = self.var_unit.get()
        new_show_unit = self.var_show_unit.get()
        new_smart = self.var_smart.get()
        
        try:
            self.root.winfo_rgb(new_color)
            self.root.winfo_rgb(new_warn)
        except:
            messagebox.showerror("颜色错误", "颜色代码无效！")
            return False

        self.cfg['text_prefix'] = new_prefix
        self.cfg['font_size'] = new_size
        self.cfg['font_color'] = new_color
        self.cfg['warn_color'] = new_warn
        self.cfg['update_rate'] = new_rate
        
        self.cfg['warn_percent'] = new_warn_pct
        self.cfg['unit'] = new_unit
        self.cfg['show_unit'] = new_show_unit
        self.cfg['smart_hide'] = new_smart
        
        # 应用
        self.label.config(font=(FONT_NAME, new_size, "bold"), fg=new_color)
        self.canvas.itemconfig(self.handle, outline=new_color)
        self.color_preview.config(bg=new_color)
        self.update_text(self.label.cget("text"), new_color) 
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
        # 兼容性处理
        if 'update_rate' not in config: config['update_rate'] = 30
        if 'warn_percent' not in config: config['warn_percent'] = 90
        if 'warn_color' not in config: config['warn_color'] = "#FF0000"
        if 'unit' not in config: config['unit'] = "km/h"
        if 'show_unit' not in config: config['show_unit'] = True
        if 'smart_hide' not in config: config['smart_hide'] = True
        
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
    def update_text(self, text, color=None):
        if self.root.state() == 'normal':
            if color:
                self.label.config(text=text, fg=color)
            else:
                self.label.config(text=text)

    def get_telemetry(self):
        """获取所有必要的遥测数据: {status, army, type, ias}"""
        data = {
            'running': False,
            'army': '',
            'type': '',
            'ias_kmh': None
        }
        
        try:
            # 1. Check Mission Status
            r_mission = requests.get('http://127.0.0.1:8111/mission.json', timeout=0.05)
            if r_mission.ok:
                mission = r_mission.json()
                data['running'] = (mission.get('status') == 'running')
            
            if data['running']:
                # 2. Check Indicators
                r_ind = requests.get('http://127.0.0.1:8111/indicators', timeout=0.05)
                if r_ind.ok:
                    ind = r_ind.json()
                    if ind.get('valid'):
                        data['army'] = ind.get('army', '')
                        data['type'] = ind.get('type', '')
                
                # 3. Check State (IAS)
                r_state = requests.get('http://127.0.0.1:8111/state', timeout=0.05)
                if r_state.ok:
                    state = r_state.json()
                    if state.get('valid'):
                        val = state.get('IAS, km/h')
                        if val is not None:
                            data['ias_kmh'] = float(val)
        except:
            pass
            
        return data

    def update_data_loop(self):
        while self.is_running:
            data = self.get_telemetry()
            
            # --- Config Values ---
            prefix = self.cfg.get('text_prefix', "IAS: ")
            unit_str = self.cfg.get('unit', 'km/h')
            show_unit = self.cfg.get('show_unit', True)
            smart_hide = self.cfg.get('smart_hide', True)
            
            base_color = self.cfg.get('font_color', '#00FF00')
            warn_color = self.cfg.get('warn_color', '#FF0000')
            warn_percent = self.cfg.get('warn_percent', 90) / 100.0
            
            # --- Visibility Logic ---
            should_show = True
            if smart_hide:
                # 只在 游戏运行中 AND 在飞机上 时显示
                if not data['running'] or data['army'] != 'air':
                    should_show = False
            
            display_text = ""
            final_color = base_color

            if should_show:
                if data['ias_kmh'] is not None:
                    # 1. 换算
                    val_kmh = data['ias_kmh']
                    val_disp = val_kmh
                    suffix = " km/h"
                    
                    if unit_str == 'kt':
                        val_disp = val_kmh / 1.852
                        suffix = " kt"
                    elif unit_str == 'mph':
                        val_disp = val_kmh / 1.60934
                        suffix = " mph"
                        
                    if not show_unit:
                        suffix = ""
                        
                    display_text = f"{prefix}{int(val_disp)}{suffix}"
                    
                    # 2. 警告判断
                    limit_kmh = self.fm_db.get_limit(data['type'])
                    if limit_kmh:
                        if val_kmh >= limit_kmh * warn_percent:
                            final_color = warn_color
                else:
                    # 在游戏里但在菜单/无数据时显示 ?
                    if data['running'] and data['army'] == 'air':
                        display_text = f"{prefix}?"
                    else:
                         # 理论上 smart_hide 会拦截，但如果 smart_hide=False，这里会显示 ?
                        display_text = f"{prefix}?"
            else:
                display_text = "" # 隐藏
            
            try:
                self.root.after(0, self.update_text, display_text, final_color)
            except:
                break
            
            rate = self.cfg.get('update_rate', 30)
            if rate <= 0: rate = 1
            if rate > 60: rate = 60 
            time.sleep(1.0 / rate)

if __name__ == "__main__":
    root = tk.Tk()
    app = OverlayApp(root)
    root.mainloop()
