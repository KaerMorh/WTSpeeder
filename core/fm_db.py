import os
from config import resource_path

class FM_DB:
    """处理飞机气动数据加载"""
    def __init__(self):
        self.crit_speeds = {} # { "plane_type_id": float_speed_kmh }
        self.crit_machs = {}  # { "plane_type_id": float_mach }
        self.load_db()
        
    def load_db(self):
        # 尝试定位 FM/fm_data_db.csv
        # 假设脚本在项目根目录，FM在 ./FM
        csv_path = resource_path(os.path.join("FM", "fm_data_db.csv"))
        
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
                            
                        try:
                            crit_mach = float(parts[7]) # CritAirSpdMach (index 7)
                            self.crit_machs[name] = crit_mach
                        except (ValueError, IndexError):
                            pass
            print(f"成功加载 {len(self.crit_speeds)} 条飞机数据")
        except Exception as e:
            print(f"加载数据库出错: {e}")

    def get_limit(self, plane_type):
        return self.crit_speeds.get(plane_type)

    def get_mach_limit(self, plane_type):
        return self.crit_machs.get(plane_type)



