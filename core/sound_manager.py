import os
from config import resource_path

# === 音频库 ===
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("警告: 未检测到 pygame, 声音功能将不可用")

class SoundManager:
    """处理声音播放，单例/单独管理"""
    def __init__(self):
        self.enabled = False
        self.volume = 0.5
        self.current_state = 0 # 0: None, 1: Warn, 2: Critical
        
        # 声音对象
        self.snd_warn = None
        self.snd_crit = None
        
        self.init_sound()
        
    def init_sound(self):
        if not PYGAME_AVAILABLE:
            return
            
        try:
            pygame.mixer.init()
            
            p_warn = resource_path(os.path.join("sounds", "beep_fast.wav"))
            p_crit = resource_path(os.path.join("sounds", "beep_force_critical.wav"))
            
            if os.path.exists(p_warn):
                self.snd_warn = pygame.mixer.Sound(p_warn)
            
            if os.path.exists(p_crit):
                self.snd_crit = pygame.mixer.Sound(p_crit)
                
            print("音频系统初始化完成")
        except Exception as e:
            print(f"音频初始化失败: {e}")

    def update_settings(self, enabled, volume_percent):
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume_percent / 100.0))
        
        # 如果被禁用，立即停止所有声音
        if not self.enabled:
            self.stop_all()
            self.current_state = 0
            
        # 更新音量
        if self.snd_warn: self.snd_warn.set_volume(self.volume)
        if self.snd_crit: self.snd_crit.set_volume(self.volume)

    def stop_all(self):
        if self.snd_warn: self.snd_warn.stop()
        if self.snd_crit: self.snd_crit.stop()

    def update_state(self, new_state):
        """
        new_state: 0=Silent, 1=Warn(beep_fast), 2=Critical(beep_critical)
        """
        if not self.enabled or not PYGAME_AVAILABLE:
            return

        if new_state == self.current_state:
            return # 状态未变
            
        # 状态改变，先停止旧的
        self.stop_all()
        
        if new_state == 1:
            if self.snd_warn: self.snd_warn.play(loops=-1)
        elif new_state == 2:
            if self.snd_crit: self.snd_crit.play(loops=-1)
            
        self.current_state = new_state


