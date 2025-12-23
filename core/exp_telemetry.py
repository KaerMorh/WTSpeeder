try:
    from test_features.telemetry_exp import ExpManager
    from test_features.ui_patch import patch_settings_window
    _HAS_EXT = True
except ImportError:
    _HAS_EXT = False
    ExpManager = object
    patch_settings_window = None

if _HAS_EXT:
    class ExpTelemetry(ExpManager):
        """
        实验性遥测接口 (实际实现由 test_features 提供)
        """
        def __init__(self):
            super().__init__()
            
        @property
        def is_available(self):
            return True
else:
    class ExpTelemetry:
        """
        实验性遥测接口 (存根)
        """
        def __init__(self):
            self.enabled = False
            
        def update_settings(self, enabled, cut_ab=False):
            self.enabled = enabled
            
        def update(self, ias_kmh, mach, limit_kmh, limit_mach, ab_pct, trigger_pct, exit_pct):
            return {
                'did_action': False,
                'action_type': None,
                'reason': None
            }
            
        @property
        def is_available(self):
            return False

def get_ui_patcher():
    """获取UI补丁函数，用于私有文案"""
    if _HAS_EXT:
        return patch_settings_window
    return None

