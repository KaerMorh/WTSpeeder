import tkinter as tk
import sys
from tkinter import messagebox
from ui.overlay import OverlayApp
from core.instance_manager import InstanceManager

if __name__ == "__main__":
    # 1. 实例化 InstanceManager
    im = InstanceManager()
    
    # 2. 执行单实例检查
    if not im.ensure_single_instance():
        # 如果最终失败（重试多次仍被占用），弹窗提示并退出
        # 这里创建一个临时的隐藏 root 窗口来显示 messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", "无法启动程序：端口被占用且旧实例无法关闭。\n请尝试手动结束 WTOverlay.exe 进程。")
        root.destroy()
        sys.exit(1)

    # 3. 正常启动
    root = tk.Tk()
    app = OverlayApp(root)
    
    # 注册退出回调，确保旧实例被顶替时能正确清理（托盘图标等）
    im.register_shutdown_callback(app.quit_app)
    
    root.mainloop()
