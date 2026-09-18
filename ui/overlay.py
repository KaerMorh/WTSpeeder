import tkinter as tk
from tkinter import colorchooser, messagebox
from tkinter import ttk
import threading
import time
import os
from datetime import datetime
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

from config import (
    APP_NAME, FONT_NAME, DEFAULT_CONFIG, 
    resource_path, load_config, save_config
)
from core.telemetry import get_telemetry
from core.fm_db import FM_DB
from core.sound_manager import SoundManager
from core.exp_telemetry import ExpTelemetry, get_ui_patcher
from utils.logger import CSVLogger
from app_version import APP_VERSION
from core.app_update import check_release, download_release, install_on_exit, is_public_build
from core.fm_versions import FMVersionManager, SCHEMA_VERSION

class ToolTip:
    """简单的工具提示控件"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = int(self.widget.winfo_rootx() + 20)
        y = int(self.widget.winfo_rooty() + self.widget.winfo_height() + 5)
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            tw.wm_attributes("-topmost", True)
        except:
            pass
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left',
                       background="#ffffe0", relief='solid', borderwidth=1,
                       font=("Microsoft YaHei UI", 9, "normal"))
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()

class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("设置 - 战雷速度监视器")
        self.win.attributes("-topmost", True)
        self.cfg = app.cfg # Reference to app config
        
        self.setup_ui()
        
        # Apply UI Patch if available (Shadow Area Restore)
        patcher = get_ui_patcher()
        if patcher:
            patcher(self)
        
    def setup_ui(self):
        # 底部按钮区 (独立于 Tab) - 先 Pack
        btn_frame = tk.Frame(self.win)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        tk.Button(btn_frame, text="恢复默认", command=self.restore_defaults, fg="red").pack(side=tk.LEFT)
        tk.Button(btn_frame, text="保存并关闭", command=self.save_settings_from_ui, bg="#DDDDDD").pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="保存", command=self.apply_settings).pack(side=tk.RIGHT, padx=5)

        # 使用 Notebook 分页
        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tab_ui = tk.Frame(self.notebook)
        self.tab_func = tk.Frame(self.notebook)
        self.tab_exp = tk.Frame(self.notebook)
        self.tab_update = tk.Frame(self.notebook)
        
        self.notebook.add(self.tab_ui, text="界面显示")
        self.notebook.add(self.tab_func, text="功能设置")
        self.notebook.add(self.tab_update, text="更新")
        if ExpTelemetry().is_available:
            self.notebook.add(self.tab_exp, text="实验功能")
            
        self.setup_tab_ui()
        self.setup_tab_func()
        self.setup_tab_update()
        if ExpTelemetry().is_available:
            self.setup_tab_exp()

    def setup_tab_update(self):
        self.fm_manager = FMVersionManager()
        self.update_busy = False
        app_group = tk.LabelFrame(self.tab_update, text="应用更新", padx=8, pady=8)
        app_group.pack(fill=tk.X, padx=10, pady=6)
        mode = "Public" if is_public_build() else "源码/本地构建，应用更新不适用"
        self.app_update_status = tk.StringVar(value=f"当前版本：{APP_VERSION}　{mode}")
        tk.Label(app_group, textvariable=self.app_update_status, anchor="w", justify=tk.LEFT).pack(fill=tk.X)
        self.app_notes = tk.Text(app_group, height=4, wrap=tk.WORD, state=tk.DISABLED)
        self.app_notes.pack(fill=tk.X, pady=4)
        app_buttons = tk.Frame(app_group)
        app_buttons.pack(fill=tk.X)
        self.btn_app_check = tk.Button(app_buttons, text="检查应用更新", command=self.check_app_update)
        self.btn_app_check.pack(side=tk.LEFT)
        self.btn_app_install = tk.Button(app_buttons, text="下载并安装", state=tk.DISABLED, command=self.install_app_update)
        self.btn_app_install.pack(side=tk.LEFT, padx=5)
        if not is_public_build():
            self.btn_app_check.config(state=tk.DISABLED)

        fm_group = tk.LabelFrame(self.tab_update, text="FM 数据更新", padx=8, pady=8)
        fm_group.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.fm_status = tk.StringVar()
        tk.Label(fm_group, textvariable=self.fm_status, anchor="w", justify=tk.LEFT).pack(fill=tk.X)
        row = tk.Frame(fm_group)
        row.pack(fill=tk.X, pady=4)
        self.fm_choice = ttk.Combobox(row, state="readonly", width=54)
        self.fm_choice.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.fm_choice.bind("<<ComboboxSelected>>", self.show_fm_details)
        self.btn_fm_select = tk.Button(row, text="下次启动使用", command=self.select_fm_version)
        self.btn_fm_select.pack(side=tk.LEFT, padx=5)
        self.btn_fm_sync = tk.Button(fm_group, text="检查并下载 FM 更新", command=self.sync_fm_versions)
        self.btn_fm_sync.pack(anchor=tk.W)
        self.fm_details = tk.Text(fm_group, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.fm_details.pack(fill=tk.BOTH, expand=True, pady=4)
        self.refresh_fm_versions()

    def _set_text(self, widget, value):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.config(state=tk.DISABLED)

    def _run_update_task(self, worker, finished):
        if self.update_busy:
            return
        self.update_busy = True
        def run():
            try:
                result = worker()
                self.win.after(0, lambda: finished(result, None))
            except Exception as exc:
                self.win.after(0, lambda error=exc: finished(None, error))
        threading.Thread(target=run, daemon=True).start()

    def check_app_update(self):
        self.app_update_status.set("正在检查应用更新……")
        self._run_update_task(check_release, self._app_check_finished)

    def _app_check_finished(self, release, error):
        self.update_busy = False
        if error:
            self.app_update_status.set(f"检查失败，可重试：{error}")
            return
        self.available_release = release
        tag = release.get("tag_name", "未知")
        self._set_text(self.app_notes, release.get("body") or "此版本没有更新说明。")
        if release.get("newer"):
            self.app_update_status.set(f"发现可用版本：{tag}")
            self.btn_app_install.config(state=tk.NORMAL)
        else:
            self.app_update_status.set(f"当前已是最新版本（远端 {tag}）")

    def install_app_update(self):
        release = getattr(self, "available_release", None)
        if not release:
            return
        self.app_update_status.set("正在下载并校验应用更新……")
        self.btn_app_install.config(state=tk.DISABLED)
        self._run_update_task(lambda: download_release(release), self._app_download_finished)

    def _app_download_finished(self, path, error):
        self.update_busy = False
        if error:
            self.app_update_status.set(f"下载失败，旧程序未改动：{error}")
            self.btn_app_install.config(state=tk.NORMAL)
            return
        if messagebox.askyesno("安装更新", "更新已校验。现在退出并替换 Public 程序吗？"):
            try:
                install_on_exit(path)
                self.app.quit_app()
            except Exception as exc:
                self.app_update_status.set(f"无法自动替换；已下载文件位于 {path}：{exc}")

    def refresh_fm_versions(self):
        versions = sorted(
            self.fm_manager.index.get("versions", []),
            key=lambda value: (value.get("published_at", ""), value.get("id", "")),
            reverse=True,
        )
        latest = self.fm_manager.latest_published()
        stable_id = self.fm_manager.index.get("stable_id")
        running = self.app.fm_db.version_manager.current_id
        selected = self.fm_manager.state.get("selected_id") or stable_id
        labels = []
        self.fm_label_versions = {}
        for version in versions:
            tags = []
            if latest and version["id"] == latest["id"]:
                tags.append("推荐")
            if version["id"] == stable_id:
                tags.append("人工稳定版")
            if version["id"] == running:
                tags.append("当前使用")
            if version.get("schema_version") != SCHEMA_VERSION:
                tags.append("需升级应用")
            label = f"{version['id']}　{self._local_time(version.get('published_at', ''))}"
            if tags:
                label += "　[" + " / ".join(tags) + "]"
            labels.append(label)
            self.fm_label_versions[label] = version
        self.fm_choice["values"] = labels
        target = next((label for label, version in self.fm_label_versions.items() if version["id"] == selected), labels[0] if labels else "")
        self.fm_choice.set(target)
        checked = self.fm_manager.state.get("last_checked_at", "尚未联网检查")
        self.fm_status.set(f"当前使用：{running or '内置基线'}　下次启动：{selected or running or '内置基线'}\n上次检查：{checked}")
        self.show_fm_details()

    def _local_time(self, value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return value or "未知"

    def show_fm_details(self, event=None):
        version = getattr(self, "fm_label_versions", {}).get(self.fm_choice.get())
        if not version:
            return
        kind = "人工构建" if version.get("kind") == "manual" else "自动构建"
        compatibility = "兼容" if version.get("schema_version") == SCHEMA_VERSION else "需升级应用，不能启用"
        text = (f"版本：{version.get('id')}\n更新时间：{self._local_time(version.get('published_at', ''))}\n"
                f"来源：{kind}\n说明：{version.get('notes', '')}")
        text += f"\n格式：{compatibility}"
        self._set_text(self.fm_details, text)

    def select_fm_version(self):
        version = getattr(self, "fm_label_versions", {}).get(self.fm_choice.get())
        if not version:
            return
        try:
            self.fm_manager.choose(version["id"])
            self.fm_status.set(f"已选择 {version['id']}，将在下次启动生效；当前运行数据未改变。")
            self.refresh_fm_versions()
        except Exception as exc:
            messagebox.showerror("FM 选择失败", str(exc))

    def sync_fm_versions(self):
        self.fm_status.set("正在检查并下载 FM 更新……")
        self.btn_fm_sync.config(state=tk.DISABLED)
        self._run_update_task(self.fm_manager.sync, self._fm_sync_finished)

    def _fm_sync_finished(self, versions, error):
        self.update_busy = False
        self.btn_fm_sync.config(state=tk.NORMAL)
        if error:
            self.fm_status.set(f"FM 更新失败，可重试；现有数据继续可用：{error}")
            return
        self.refresh_fm_versions()
        self.fm_status.set(self.fm_status.get() + "\n同步完成。推荐版本仅标记最新发布版。")

    def setup_tab_ui(self):
        pad_opts = {'padx': 10, 'pady': 5}
        
        # --- 分组 1: 基础样式 ---
        group_basic = tk.LabelFrame(self.tab_ui, text="基础样式", padx=5, pady=5)
        group_basic.pack(fill=tk.X, **pad_opts)
        
        # 文本前缀
        row1 = tk.Frame(group_basic)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="显示前缀:").pack(side=tk.LEFT)
        self.entry_prefix = tk.Entry(row1, width=15)
        self.entry_prefix.insert(0, self.cfg.get('text_prefix', "IAS: "))
        self.entry_prefix.pack(side=tk.RIGHT)
        
        # 字体大小
        row2 = tk.Frame(group_basic)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="字体大小:").pack(side=tk.LEFT)
        self.scale_size = tk.Scale(row2, from_=10, to=60, orient=tk.HORIZONTAL, length=150)
        self.scale_size.set(self.cfg['font_size'])
        self.scale_size.pack(side=tk.RIGHT)

        # 圆球大小
        row3 = tk.Frame(group_basic)
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="圆球大小:").pack(side=tk.LEFT)
        self.scale_handle = tk.Scale(row3, from_=10, to=50, orient=tk.HORIZONTAL, length=150)
        self.scale_handle.set(self.cfg.get('handle_size', 20))
        self.scale_handle.pack(side=tk.RIGHT)

        # --- 分组 2: 颜色设置 ---
        group_color = tk.LabelFrame(self.tab_ui, text="颜色风格", padx=5, pady=5)
        group_color.pack(fill=tk.X, **pad_opts)
        
        # 正常颜色
        f_norm = tk.Frame(group_color)
        f_norm.pack(fill=tk.X, pady=2)
        tk.Label(f_norm, text="正常状态颜色:").pack(side=tk.LEFT)
        
        f_norm_r = tk.Frame(f_norm) # 右侧容器
        f_norm_r.pack(side=tk.RIGHT)
        
        tk.Button(f_norm_r, text="选", command=lambda: self.choose_color(self.entry_hex, self.color_preview), width=3).pack(side=tk.RIGHT)
        self.entry_hex = tk.Entry(f_norm_r, width=7)
        self.entry_hex.insert(0, self.cfg['font_color'])
        self.entry_hex.pack(side=tk.RIGHT, padx=2)
        self.color_preview = tk.Label(f_norm_r, text="  ", bg=self.cfg['font_color'], relief="solid", width=3)
        self.color_preview.pack(side=tk.RIGHT, padx=2)

        # 警告颜色
        f_warn = tk.Frame(group_color)
        f_warn.pack(fill=tk.X, pady=2)
        tk.Label(f_warn, text="警告状态颜色:").pack(side=tk.LEFT)
        
        f_warn_r = tk.Frame(f_warn)
        f_warn_r.pack(side=tk.RIGHT)
        
        tk.Button(f_warn_r, text="选", command=lambda: self.choose_color(self.entry_warn, self.warn_preview), width=3).pack(side=tk.RIGHT)
        self.entry_warn = tk.Entry(f_warn_r, width=7)
        self.entry_warn.insert(0, self.cfg.get('warn_color', '#FF0000'))
        self.entry_warn.pack(side=tk.RIGHT, padx=2)
        self.warn_preview = tk.Label(f_warn_r, text="  ", bg=self.cfg.get('warn_color', '#FF0000'), relief="solid", width=3)
        self.warn_preview.pack(side=tk.RIGHT, padx=2)
        
        # --- 分组 3: 显示控制 ---
        group_display = tk.LabelFrame(self.tab_ui, text="显示控制", padx=5, pady=5)
        group_display.pack(fill=tk.X, **pad_opts)
        
        # 单位行
        row_unit = tk.Frame(group_display)
        row_unit.pack(fill=tk.X, pady=2)
        tk.Label(row_unit, text="单位:").pack(side=tk.LEFT)
        self.var_unit = tk.StringVar(value=self.cfg.get('unit', 'km/h'))
        for u in ['km/h', 'kt', 'mph']:
            tk.Radiobutton(row_unit, text=u, variable=self.var_unit, value=u).pack(side=tk.LEFT, padx=2)
            
        # 复选框们
        self.var_show_unit = tk.BooleanVar(value=self.cfg.get('show_unit', True))
        tk.Checkbutton(group_display, text="显示单位文字", variable=self.var_show_unit).pack(anchor=tk.W)

        self.var_smart = tk.BooleanVar(value=self.cfg.get('smart_hide', True))
        chk_smart = tk.Checkbutton(group_display, text="智能隐藏 (仅在对局中显示)", variable=self.var_smart)
        chk_smart.pack(anchor=tk.W)
        ToolTip(chk_smart, "开启后只在对局中显示真空速")

        self.var_hide_text = tk.BooleanVar(value=self.cfg.get('hide_text', False))
        tk.Checkbutton(group_display, text="只显示圆球 (始终隐藏文字)", variable=self.var_hide_text).pack(anchor=tk.W)
        
        self.var_show_cross = tk.BooleanVar(value=self.cfg.get('show_crosshair', False))
        tk.Checkbutton(group_display, text="显示十字准星 (透明穿透)", variable=self.var_show_cross).pack(anchor=tk.W)

    def setup_tab_func(self):
        pad_opts = {'padx': 10, 'pady': 5}

        # --- 分组 1: 告警设置 ---
        group_warn = tk.LabelFrame(self.tab_func, text="告警设置", padx=5, pady=5)
        group_warn.pack(fill=tk.X, **pad_opts)
        
        row_w = tk.Frame(group_warn)
        row_w.pack(fill=tk.X)
        lbl_warn = tk.Label(row_w, text="警告阈值 (%):")
        lbl_warn.pack(side=tk.LEFT)
        ToolTip(lbl_warn, "推荐97 98")
        
        self.scale_warn_pct = tk.Scale(row_w, from_=70, to=100, resolution=0.1, orient=tk.HORIZONTAL, length=120, showvalue=0)
        self.scale_warn_pct.set(self.cfg.get('warn_percent', 90))
        self.scale_warn_pct.pack(side=tk.RIGHT, padx=5)
        self.scale_warn_pct.configure(command=self.on_scale_change)
        
        self.entry_warn_pct = tk.Entry(row_w, width=5)
        self.entry_warn_pct.insert(0, f"{self.cfg.get('warn_percent', 90):.1f}")
        self.entry_warn_pct.pack(side=tk.RIGHT)
        self.entry_warn_pct.bind('<FocusOut>', self.on_warn_entry_change)
        self.entry_warn_pct.bind('<Return>', self.on_warn_entry_change)

        # --- 分组 2: 声音设置 ---
        group_snd = tk.LabelFrame(self.tab_func, text="声音提示", padx=5, pady=5)
        group_snd.pack(fill=tk.X, **pad_opts)
        
        self.var_snd_enable = tk.BooleanVar(value=self.cfg.get('enable_sound', False))
        tk.Checkbutton(group_snd, text="启用声音警报", variable=self.var_snd_enable).pack(anchor=tk.W)
        
        row_vol = tk.Frame(group_snd)
        row_vol.pack(fill=tk.X, pady=5)
        tk.Label(row_vol, text="音量大小:").pack(side=tk.LEFT)
        self.scale_vol = tk.Scale(row_vol, from_=0, to=100, orient=tk.HORIZONTAL, length=150)
        self.scale_vol.set(self.cfg.get('sound_volume', 50))
        self.scale_vol.pack(side=tk.RIGHT)

        # --- 分组 3: 系统设置 ---
        group_sys = tk.LabelFrame(self.tab_func, text="系统性能", padx=5, pady=5)
        group_sys.pack(fill=tk.X, **pad_opts)
        
        row_rate = tk.Frame(group_sys)
        row_rate.pack(fill=tk.X)
        lbl_rate = tk.Label(row_rate, text="刷新频率 (Hz):")
        lbl_rate.pack(side=tk.LEFT)
        ToolTip(lbl_rate, "推荐30HZ，过低可能导致提醒延误")
        
        self.scale_rate = tk.Scale(row_rate, from_=5, to=60, resolution=1, orient=tk.HORIZONTAL, length=150)
        self.scale_rate.set(self.cfg.get('update_rate', 30))
        self.scale_rate.pack(side=tk.RIGHT)

    def setup_tab_exp(self):
        pad_opts = {'padx': 10, 'pady': 5}
        
        group_exp = tk.LabelFrame(self.tab_exp, text="实验性功能", padx=5, pady=5)
        group_exp.pack(fill=tk.X, **pad_opts)
        
        # 实验性遥测
        self.var_exp_telemetry = tk.BooleanVar(value=self.cfg.get('exp_telemetry_enabled', False))
        self.chk_exp_telemetry = tk.Checkbutton(group_exp, text="启用实验性遥测 (Exp Telemetry)", variable=self.var_exp_telemetry, command=self.toggle_exp_inputs)
        self.chk_exp_telemetry.pack(anchor=tk.W)
        self.tip_exp_telemetry = ToolTip(self.chk_exp_telemetry, "开启实验性飞行数据遥测模块")
        
        # 实验性输入
        self.var_exp_input = tk.BooleanVar(value=self.cfg.get('exp_input_enabled', False))
        self.chk_exp_input = tk.Checkbutton(group_exp, text="启用实验性输入捕获 (Exp Input)", variable=self.var_exp_input)
        self.chk_exp_input.pack(anchor=tk.W, padx=20)
        
        # 阈值设置
        row_th = tk.Frame(group_exp)
        row_th.pack(fill=tk.X, pady=5, padx=20)
        
        tk.Label(row_th, text="触发阈值(%):").pack(side=tk.LEFT)
        self.entry_trig = tk.Entry(row_th, width=5)
        self.entry_trig.insert(0, str(self.cfg.get('ab_trigger_pct', 99.7)))
        self.entry_trig.pack(side=tk.LEFT, padx=5)
        
        tk.Label(row_th, text="退出阈值(%):").pack(side=tk.LEFT, padx=(10,0))
        self.entry_exit = tk.Entry(row_th, width=5)
        self.entry_exit.insert(0, str(self.cfg.get('ab_exit_pct', 95.0)))
        self.entry_exit.pack(side=tk.LEFT, padx=5)
        
        # 初始化状态
        self.toggle_exp_inputs()

    def toggle_exp_inputs(self):
        """根据实验功能开关状态，启用或禁用相关设置"""
        if not hasattr(self, 'var_exp_telemetry'):
            return
            
        is_enabled = self.var_exp_telemetry.get()
        state = 'normal' if is_enabled else 'disabled'
        
        if hasattr(self, 'chk_exp_input'):
            self.chk_exp_input.config(state=state)
        if hasattr(self, 'entry_trig'):
            self.entry_trig.config(state=state)
        if hasattr(self, 'entry_exit'):
            self.entry_exit.config(state=state)

    def on_scale_change(self, val):
        f_val = float(val)
        self.entry_warn_pct.delete(0, tk.END)
        self.entry_warn_pct.insert(0, f"{f_val:.1f}")

    def on_warn_entry_change(self, event=None):
        text = self.entry_warn_pct.get().strip()
        if not text: return

        try:
            val = float(text)
            if val < 0: val = 0
            if val > 100: val = 100
            self.scale_warn_pct.set(val) 
            self.entry_warn_pct.delete(0, tk.END)
            self.entry_warn_pct.insert(0, f"{val:.1f}")
        except ValueError:
            pass

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
        if messagebox.askyesno("确认", "确定要恢复默认设置吗？\n(位置不会改变，但颜色、大小、频率会重置)"):
            current_x = self.cfg['x']
            current_y = self.cfg['y']
            
            # Reset config using default copy
            self.app.cfg = DEFAULT_CONFIG.copy()
            self.app.cfg['x'] = current_x
            self.app.cfg['y'] = current_y
            self.cfg = self.app.cfg # Re-bind to new object
            
            # Refresh UI
            self.entry_prefix.delete(0, tk.END)
            self.entry_prefix.insert(0, self.cfg['text_prefix'])
            
            self.scale_size.set(self.cfg['font_size'])
            self.scale_handle.set(self.cfg.get('handle_size', 20))
            self.scale_rate.set(self.cfg['update_rate'])
            
            self.entry_hex.delete(0, tk.END)
            self.entry_hex.insert(0, self.cfg['font_color'])
            self.color_preview.config(bg=self.cfg['font_color'])
            
            self.entry_warn.delete(0, tk.END)
            self.entry_warn.insert(0, self.cfg['warn_color'])
            self.warn_preview.config(bg=self.cfg['warn_color'])
            
            self.scale_warn_pct.set(self.cfg['warn_percent'])
            self.entry_warn_pct.delete(0, tk.END)
            self.entry_warn_pct.insert(0, f"{self.cfg['warn_percent']:.1f}")

            self.var_unit.set(self.cfg['unit'])
            self.var_show_unit.set(self.cfg['show_unit'])
            self.var_smart.set(self.cfg['smart_hide'])
            self.var_hide_text.set(self.cfg['hide_text'])
            self.var_show_cross.set(self.cfg.get('show_crosshair', False))
            
            self.var_snd_enable.set(self.cfg['enable_sound'])
            self.scale_vol.set(self.cfg['sound_volume'])
            
            # Restore experimental vars
            if hasattr(self, 'var_exp_telemetry'):
                self.var_exp_telemetry.set(self.cfg['exp_telemetry_enabled'])
                self.var_exp_input.set(self.cfg['exp_input_enabled'])
                
                self.toggle_exp_inputs()
                
                self.entry_trig.delete(0, tk.END)
                self.entry_trig.insert(0, str(self.cfg['ab_trigger_pct']))
                
                self.entry_exit.delete(0, tk.END)
                self.entry_exit.insert(0, str(self.cfg['ab_exit_pct']))
            
            # Sync app
            self.app.apply_ui_update()
            
            messagebox.showinfo("提示", "已恢复默认设置！")

    def apply_settings(self):
        new_prefix = self.entry_prefix.get()
        new_size = self.scale_size.get()
        new_h_size = self.scale_handle.get()
        new_rate = self.scale_rate.get()
        new_color = self.entry_hex.get()
        new_warn = self.entry_warn.get()
        
        raw_warn_txt = self.entry_warn_pct.get().strip()
        new_warn_pct = 90.0
        if raw_warn_txt:
            try:
                new_warn_pct = float(raw_warn_txt)
            except ValueError:
                new_warn_pct = self.scale_warn_pct.get()
        else:
             new_warn_pct = self.scale_warn_pct.get()

        new_unit = self.var_unit.get()
        new_show_unit = self.var_show_unit.get()
        new_smart = self.var_smart.get()
        new_hide_text = self.var_hide_text.get()
        new_show_cross = self.var_show_cross.get()
        
        new_snd_enable = self.var_snd_enable.get()
        new_vol = self.scale_vol.get()
        
        # Experimental features
        new_exp_telemetry = self.cfg.get('exp_telemetry_enabled', False)
        new_exp_input = self.cfg.get('exp_input_enabled', False)
        new_trig = self.cfg.get('ab_trigger_pct', 99.7)
        new_exit = self.cfg.get('ab_exit_pct', 95.0)

        if hasattr(self, 'var_exp_telemetry'):
            new_exp_telemetry = self.var_exp_telemetry.get()
            new_exp_input = self.var_exp_input.get()
            
            try:
                new_trig = float(self.entry_trig.get())
                new_exit = float(self.entry_exit.get())
            except ValueError:
                messagebox.showerror("错误", "阈值必须是数字")
                return False
        
        try:
            self.win.winfo_rgb(new_color)
            self.win.winfo_rgb(new_warn)
        except:
            messagebox.showerror("颜色错误", "颜色代码无效！")
            return False

        self.cfg['text_prefix'] = new_prefix
        self.cfg['font_size'] = new_size
        self.cfg['handle_size'] = new_h_size
        self.cfg['font_color'] = new_color
        self.cfg['warn_color'] = new_warn
        self.cfg['update_rate'] = new_rate
        
        self.cfg['warn_percent'] = new_warn_pct
        self.cfg['unit'] = new_unit
        self.cfg['show_unit'] = new_show_unit
        self.cfg['smart_hide'] = new_smart
        self.cfg['hide_text'] = new_hide_text
        self.cfg['show_crosshair'] = new_show_cross
        
        self.cfg['enable_sound'] = new_snd_enable
        self.cfg['sound_volume'] = new_vol
        
        self.cfg['exp_telemetry_enabled'] = new_exp_telemetry
        self.cfg['exp_input_enabled'] = new_exp_input
        self.cfg['ab_trigger_pct'] = new_trig
        self.cfg['ab_exit_pct'] = new_exit
        
        # Apply changes to main app
        self.app.apply_ui_update()
        
        return True

    def save_settings_from_ui(self):
        if self.apply_settings():
            self.win.destroy()


class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WT Speed Monitor")
        
        self.fm_db = FM_DB()
        self.sound_mgr = SoundManager()
        
        # Initialize ExpTelemetry (Experiment Manager)
        self.exp_mgr = ExpTelemetry()
        
        self.logger = CSVLogger()
        self.is_logging_enabled = False
        self.debug_mode_unlocked = False
        self.click_count = 0
        self.last_click_time = 0
        
        self.cfg = load_config()
        self.current_handle_size = self.cfg.get('handle_size', 20)
        
        # Apply initial settings
        self.sound_mgr.update_settings(self.cfg.get('enable_sound', False), self.cfg.get('sound_volume', 50))
        
        # Update Exp settings
        self.exp_mgr.update_settings(
            self.cfg.get('exp_telemetry_enabled', False), 
            self.cfg.get('exp_input_enabled', False)
        )

        # Window settings
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.config(bg='black')
        self.root.wm_attributes("-transparentcolor", "black")
        
        safe_x = max(0, self.cfg['x'])
        safe_y = max(0, self.cfg['y'])
        self.root.geometry(f"+{int(safe_x)}+{int(safe_y)}")
        
        # UI Layout
        self.frame = tk.Frame(root, bg='black')
        self.frame.pack(fill=tk.BOTH, expand=True)

        # 动态圆球尺寸
        h_size = self.cfg.get('handle_size', 20)
        padding = 5
        canvas_w = h_size + padding * 2
        canvas_h = h_size + padding * 2 # 确保正方形区域居中
        
        # 兼容旧代码，确保至少有一定高度
        if canvas_h < 40: canvas_h = 40

        self.canvas = tk.Canvas(self.frame, width=canvas_w, height=canvas_h, bg='black', highlightthickness=0)
        # 使用 anchor=CENTER 垂直居中
        self.canvas.pack(side=tk.LEFT, anchor=tk.CENTER)
        
        # 计算圆球坐标使其居中
        cx = canvas_w / 2
        cy = canvas_h / 2
        r = h_size / 2
        
        self.handle = self.canvas.create_oval(
            cx - r, cy - r, 
            cx + r, cy + r, 
            fill='#404040', stipple='gray50', outline=self.cfg['font_color'], width=2
        )
        
        # 绘制透明十字准星
        if self.cfg.get('show_crosshair', False):
            inset = 3
            self.canvas.create_line(cx - r + inset, cy, cx + r - inset, cy, fill='black', width=2)
            self.canvas.create_line(cx, cy - r + inset, cx, cy + r - inset, fill='black', width=2)

        self.label = tk.Label(self.frame, text="Wait...", 
                              font=(FONT_NAME, self.cfg['font_size'], "bold"), 
                              fg=self.cfg['font_color'], bg='black')
        self.label.pack(side=tk.LEFT, anchor=tk.CENTER) # 文字也垂直居中
        
        # Right Click Menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="⚙ 设置 (Settings)", command=self.open_settings_window)
        self.context_menu.add_command(label="👁 隐藏 (Hide)", command=self.hide_window)
        
        self.var_snd_menu = tk.BooleanVar(value=self.cfg.get('enable_sound', False))
        self.context_menu.add_checkbutton(label="🔊 声音 (Sound)", variable=self.var_snd_menu, command=self.toggle_sound_from_menu)
        
        self.var_log_menu = tk.BooleanVar(value=False)
        # 默认不添加日志菜单，需连点解锁
        # self.context_menu.add_checkbutton(label="📝 记录日志 (Debug Log)", variable=self.var_log_menu, command=self.toggle_logging)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="❌ 退出 (Exit)", command=self.quit_app)

        # Bindings
        for widget in [self.canvas, self.label]:
            widget.bind("<Button-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)
            widget.bind("<ButtonRelease-1>", self.stop_move)
            widget.bind("<Button-3>", self.show_context_menu)
        
        self.is_running = True
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()
        
        self.thread = threading.Thread(target=self.update_data_loop)
        self.thread.daemon = True
        self.thread.start()

    def open_settings_window(self):
        if hasattr(self, 'setting_win_ref') and self.setting_win_ref and self.setting_win_ref.win.winfo_exists():
            self.setting_win_ref.win.lift()
            return
        self.setting_win_ref = SettingsWindow(self)

    def apply_ui_update(self):
        # Called when settings change
        self.label.config(font=(FONT_NAME, self.cfg['font_size'], "bold"), fg=self.cfg['font_color'])
        
        # 重绘圆球以适应新尺寸
        new_h_size = self.cfg.get('handle_size', 20)
        
        # 窗口中心补偿逻辑
        if hasattr(self, 'current_handle_size') and self.current_handle_size != new_h_size:
            diff = new_h_size - self.current_handle_size
            offset = diff / 2
            self.cfg['x'] -= offset
            self.cfg['y'] -= offset
            self.root.geometry(f"+{int(self.cfg['x'])}+{int(self.cfg['y'])}")
            self.current_handle_size = new_h_size
            save_config(self.cfg)

        h_size = new_h_size
        padding = 5
        canvas_w = h_size + padding * 2
        canvas_h = h_size + padding * 2
        if canvas_h < 40: canvas_h = 40
        
        self.canvas.config(width=canvas_w, height=canvas_h)
        self.canvas.delete("all") # 清除旧的
        
        cx = canvas_w / 2
        cy = canvas_h / 2
        r = h_size / 2
        
        # 绘制半透明圆球 (使用 stipple 模拟)
        self.handle = self.canvas.create_oval(
            cx - r, cy - r, 
            cx + r, cy + r, 
            fill='#404040', stipple='gray50', outline=self.cfg['font_color'], width=2
        )
        
        # 绘制透明十字准星 (利用 transparentcolor='black' 特性)
        # 缩进一点以避免切割外圈 (width=2)
        if self.cfg.get('show_crosshair', False):
            inset = 3
            # 水平线
            self.canvas.create_line(cx - r + inset, cy, cx + r - inset, cy, fill='black', width=2)
            # 垂直线
            self.canvas.create_line(cx, cy - r + inset, cx, cy + r - inset, fill='black', width=2)
        
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<ButtonRelease-1>", self.stop_move)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        
        self.sound_mgr.update_settings(self.cfg['enable_sound'], self.cfg['sound_volume'])
        
        # Update Exp settings
        self.exp_mgr.update_settings(self.cfg['exp_telemetry_enabled'], self.cfg['exp_input_enabled'])
        
        self.var_snd_menu.set(self.cfg['enable_sound'])
        
        if hasattr(self, 'setting_win_ref') and self.setting_win_ref.win.winfo_exists():
            # Sync settings window controls if open
            try:
                 self.setting_win_ref.var_snd_enable.set(self.cfg['enable_sound'])
            except:
                pass

        save_config(self.cfg)

    def create_tray_image(self):
        image = Image.new('RGB', (64, 64), color=(0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((8, 8, 56, 56), fill=(57, 217, 33))
        return image

    def setup_tray_icon(self):
        icon_path = resource_path("icon.ico")
        image = None
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
            except:
                pass
        if image is None:
            image = self.create_tray_image()
            
        menu = (
            item('⚙ 设置 (Settings)', self.open_settings_window_safely),
            item('显示/隐藏 (Show/Hide)', self.toggle_window),
            item('重置位置 (Reset Pos)', self.reset_position),
            item('退出 (Exit)', self.quit_app)
        )
        
        # 配置 Icon
        self.icon = pystray.Icon("WT_Counter", image, "战雷速度监视器", menu)
        
        # 注册左键点击回调 (activate)
        # 绑定左键点击事件以恢复窗口
        # pystray 默认没有直接的 left_click，但可以通过 run 的 setup 参数或者 hack 方式，
        # 不过 pystray 的 activate 行为在某些系统上就是左键双击或单击
        # 比较通用的方式是作为 default menu item，或者在 run 时不阻塞
        
        # 为了实现“点击图标恢复”，可以设置 menu 的 default action
        # 这样单击/双击（取决于OS）图标时会触发该 action
        self.icon.menu = pystray.Menu(
            item('显示/隐藏 (Show/Hide)', self.on_tray_click, default=True),
            item('⚙ 设置 (Settings)', self.open_settings_window_safely),
            item('重置位置 (Reset Pos)', self.reset_position),
            item('退出 (Exit)', self.quit_app)
        )
        
        self.icon.run()

    def on_tray_click(self, icon=None, item=None):
        """左键点击托盘图标时的回调：显示并置顶"""
        self.root.after(0, self.restore_and_lift)

    def restore_and_lift(self):
        """恢复窗口并置顶"""
        # 1. 恢复显示 (deiconify)
        self.root.deiconify()
        
        # 2. 尝试置顶操作，以确保它浮在最上面
        # lift() 提升窗口层级
        self.root.lift()
        
        # 3. 重新应用 topmost 属性 (有时 deiconify 后会丢失 topmost)
        self.root.wm_attributes("-topmost", True)
        
        # 4. 可选：强制聚焦 (focus_force)，但这可能抢走游戏焦点，视情况而定
        # self.root.focus_force() 
        # 考虑到这是 overlay，通常不需要获取输入焦点，只需要视觉置顶

    def open_settings_window_safely(self, icon=None, item=None):
        self.root.after(0, self.open_settings_window)

    def toggle_window(self, icon=None, item=None):
        if self.root.state() == 'normal':
            self.root.after(0, self.root.withdraw)
        else:
            self.root.after(0, self.restore_and_lift)

    def hide_window(self):
        self.root.withdraw()

    def quit_app(self, icon=None, item=None):
        self.is_running = False
        if self.logger:
            self.logger.stop_session()
        if hasattr(self, 'icon'):
            self.icon.stop()
        self.root.after(0, self.root.destroy)

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def reset_position(self, icon=None, item=None):
        def _reset():
            self.root.deiconify()
            self.root.geometry(f"+{int(DEFAULT_CONFIG['x'])}+{int(DEFAULT_CONFIG['y'])}")
            self.cfg['x'] = DEFAULT_CONFIG['x']
            self.cfg['y'] = DEFAULT_CONFIG['y']
            save_config(self.cfg)
        self.root.after(0, _reset)

    def toggle_sound_from_menu(self):
        new_val = self.var_snd_menu.get()
        self.cfg['enable_sound'] = new_val
        self.apply_ui_update()

    def toggle_logging(self):
        self.is_logging_enabled = self.var_log_menu.get()
        if self.is_logging_enabled:
            self.logger.start_new_session()
        else:
            self.logger.stop_session()

    def start_move(self, event):
        self.last_x = event.x_root
        self.last_y = event.y_root

        # 隐藏调试模式解锁逻辑
        now = time.time()
        if now - self.last_click_time < 0.5: # 0.5秒内的连击
            self.click_count += 1
        else:
            self.click_count = 1
        self.last_click_time = now

        if not self.debug_mode_unlocked and self.click_count >= 4:
            self.debug_mode_unlocked = True
            # 插入菜单项
            try:
                # 找到分隔符位置或直接插入
                self.context_menu.insert_checkbutton(3, label="📝 记录日志 (Debug Log)", variable=self.var_log_menu, command=self.toggle_logging)
                # 反馈
                self.label.config(fg='#FFD700') # 闪一下黄色
                self.root.after(200, lambda: self.label.config(fg=self.cfg['font_color']))
                print("Debug mode unlocked")
            except Exception as e:
                print(f"Menu insert failed: {e}")

    def do_move(self, event):
        deltax = event.x_root - self.last_x
        deltay = event.y_root - self.last_y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{int(x)}+{int(y)}")
        self.last_x = event.x_root
        self.last_y = event.y_root

    def stop_move(self, event):
        self.cfg['x'] = self.root.winfo_x()
        self.cfg['y'] = self.root.winfo_y()
        save_config(self.cfg)

    def update_text(self, text, color=None):
        if self.root.state() == 'normal':
            # 基础更新
            if color:
                self.label.config(text=text, fg=color)
                # 边框颜色默认跟随文字颜色
                outline_color = color
            else:
                self.label.config(text=text)
                outline_color = self.cfg['font_color']
            
            # 录制状态下覆盖边框颜色
            if self.is_logging_enabled:
                outline_color = '#FFD700' # 金黄色

            self.canvas.itemconfig(self.handle, outline=outline_color)

    def update_data_loop(self):
        while self.is_running:
            data = get_telemetry()
            
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
                if not data['running'] or data['army'] != 'air':
                    should_show = False
            
            display_text = ""
            final_color = base_color
            snd_state = 0
            
            if data['ias_kmh'] is not None:
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
                
                wing_sweep = data.get('wing_sweep')
                limit_kmh = self.fm_db.get_limit(data['type'], wing_sweep)
                limit_mach = self.fm_db.get_mach_limit(data['type'], wing_sweep)
                
                is_warn_ui = False
                
                if limit_kmh:
                    if val_kmh >= limit_kmh * warn_percent:
                        is_warn_ui = True
                        snd_state = 1

                is_crit = False
                if limit_kmh:
                    if val_kmh >= limit_kmh * 0.992:
                        is_crit = True
                if limit_mach and data['mach'] is not None:
                    if data['mach'] >= limit_mach - 0.02:
                        is_crit = True

                if is_crit:
                    is_warn_ui = True
                    snd_state = 2

                if is_warn_ui:
                    final_color = warn_color
            else:
                if data['running'] and data['army'] == 'air':
                    display_text = f"{prefix}?"
                else:
                    display_text = f"{prefix}?"
            
            if not (data['running'] and data['army'] == 'air'):
                 snd_state = 0
            
            self.sound_mgr.update_state(snd_state)

            ab_result = None # Store result for logging

            if data['running'] and data['army'] == 'air':
                wing_sweep = data.get('wing_sweep')
                limit_kmh = self.fm_db.get_limit(data['type'], wing_sweep)
                limit_mach = self.fm_db.get_mach_limit(data['type'], wing_sweep)
                
                if data['ias_kmh'] is not None:
                    ab_result = self.exp_mgr.update(
                        ias_kmh=data['ias_kmh'],
                        mach=data['mach'],
                        limit_kmh=limit_kmh,
                        limit_mach=limit_mach,
                        ab_pct=data['airbrake'],
                        trigger_pct=self.cfg.get('ab_trigger_pct', 99.7),
                        exit_pct=self.cfg.get('ab_exit_pct', 95.0)
                    )

            # Debug Logging
            if self.is_logging_enabled and data['running'] and data['army'] == 'air':
                self.logger.log_step(data, ab_result)

            if self.cfg.get('hide_text', False):
                display_text = ""
            
            if not should_show:
                display_text = ""
            
            try:
                self.root.after(0, self.update_text, display_text, final_color)
            except:
                break
            
            rate = self.cfg.get('update_rate', 30)
            if rate <= 0: rate = 1
            if rate > 60: rate = 60 
            time.sleep(1.0 / rate)
