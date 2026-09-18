import os
import sys
import json

APP_NAME = "WTFriendCounter"
FONT_NAME = "Consolas"

DEFAULT_CONFIG = {
    "x": 139,
    "y": 553,
    "font_size": 15,
    "font_color": "#00FF00",     # 默认亮绿色
    "warn_color": "#FF0000",     # 警告红色
    "text_prefix": "IAS: ",      # 前缀文本
    "update_rate": 30,           # 默认 30 Hz
    "warn_percent": 97,          # 警告阈值 (70-95)
    "unit": "km/h",              # km/h, kt, mph
    "show_unit": True,           # 是否显示单位
    "text_mode": "ingame",       # 文字显示: always=始终显示 / ingame=仅对局内显示 / never=始终隐藏
    "smart_hide_ui": False,      # 智能隐藏UI: 勾选后只在对战开始后显示圆球
    "enable_sound": False,       # 默认关闭声音
    "sound_volume": 35,          # 音量 0-100
    "exp_telemetry_enabled": False, # 实验性遥测 (Exp Telemetry)
    "ab_trigger_pct": 99.7,      # 触发阈值
    "ab_exit_pct": 95.0,         # 退出阈值
    "exp_input_enabled": False,  # 输入测试 (Input Test)
    "handle_size": 29,            # 圆球手柄直径 (px)
    "show_crosshair": False       # 默认不显示十字准星
}

def resource_path(relative_path):
    """ 获取资源绝对路径，兼容 PyInstaller 打包 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def get_config_path():
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

def load_config():
    config_path = get_config_path()
    config = DEFAULT_CONFIG.copy()
    saved = {}   # 配置文件里实际写过的键（用于判断是否需要迁移旧字段）
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                config.update(saved)
                
            # Migration for renamed keys (Backward Compatibility)
            if 'auto_airbrake' in config:
                # If old key exists, migrate value to new key if new key is default (or just overwrite)
                # But careful not to overwrite if new key was also present (unlikely if strictly migration)
                # Simply preferring old config value if present
                config['exp_telemetry_enabled'] = config.pop('auto_airbrake')
                
            if 'auto_cut_afterburner' in config:
                config['exp_input_enabled'] = config.pop('auto_cut_afterburner')
                
        except:
            pass
            
    # 兼容性处理 / 默认值补全
    # 文字显示模式：合并旧的 smart_hide / hide_text 两个开关（只在对局内显示 = 旧智能隐藏；始终隐藏 = 旧只显示圆球）
    if 'text_mode' not in saved and ('hide_text' in saved or 'smart_hide' in saved):
        if saved.get('hide_text'):
            config['text_mode'] = 'never'
        elif saved.get('smart_hide'):
            config['text_mode'] = 'ingame'
        else:
            config['text_mode'] = 'always'
    config.pop('hide_text', None)
    config.pop('smart_hide', None)

    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value
            
    return config

def save_config(config):
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"保存配置失败: {e}")
