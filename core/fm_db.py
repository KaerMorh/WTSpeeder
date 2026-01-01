import os
from config import resource_path

class FM_DB:
    """处理飞机气动数据加载，支持可变后掠翼飞机"""
    def __init__(self):
        # 存储格式: float (普通飞机) 或 list[(sweep, value), ...] (可变后掠翼)
        self.crit_speeds = {}
        self.crit_machs = {}
        # 名称映射: 游戏返回的 type -> FM 数据库中的 name
        self.name_to_fm = {}
        self.load_names_db()
        self.load_db()
    
    @staticmethod
    def _parse_sweep_value(raw: str):
        """
        解析可能包含后掠角数据的值
        
        普通飞机: "892" -> 892.0
        可变后掠翼: "0,892,0.5,1312,1,1470" -> [(0.0, 892.0), (0.5, 1312.0), (1.0, 1470.0)]
        """
        raw = raw.strip()
        if not raw:
            return None
            
        if ',' in raw:
            # 可变后掠翼格式: sweep0,value0,sweep1,value1,...
            parts = raw.split(',')
            if len(parts) < 2 or len(parts) % 2 != 0:
                return None
            result = []
            for i in range(0, len(parts), 2):
                sweep = float(parts[i])
                value = float(parts[i+1])
                result.append((sweep, value))
            # 按 sweep 排序确保插值正确
            result.sort(key=lambda x: x[0])
            return result
        else:
            return float(raw)
    
    @staticmethod
    def _interpolate(data_points: list, sweep: float):
        """
        根据后掠角进行线性插值
        
        Args:
            data_points: [(sweep0, value0), (sweep1, value1), ...] 已按 sweep 排序
            sweep: 当前后掠角位置 (0.0~1.0)
            
        Returns:
            插值后的限制值
        """
        if not data_points:
            return None
        
        # sweep 为 None 时，返回最大后掠角时的限制值
        # 理由：可变后掠翼通常自动控制，大后掠角时不易超速
        # 这样可以避免数据读取异常时频繁误告警
        if sweep is None:
            return data_points[-1][1]  # 列表已按 sweep 排序，最后一个是最大后掠角
        
        # 边界处理
        if sweep <= data_points[0][0]:
            return data_points[0][1]
        if sweep >= data_points[-1][0]:
            return data_points[-1][1]
        
        # 找到插值区间
        for i in range(len(data_points) - 1):
            s0, v0 = data_points[i]
            s1, v1 = data_points[i + 1]
            if s0 <= sweep <= s1:
                # 线性插值: v = v0 + (v1 - v0) * (sweep - s0) / (s1 - s0)
                t = (sweep - s0) / (s1 - s0) if s1 != s0 else 0
                return v0 + (v1 - v0) * t
        
        # 不应该到达这里，但作为安全回退
        return data_points[-1][1]
    
    def load_names_db(self):
        """加载 fm_names_db.csv，建立游戏名称 -> FM名称的映射"""
        csv_path = resource_path(os.path.join("FM", "fm_names_db.csv"))
        
        if not os.path.exists(csv_path):
            print(f"警告: 找不到名称映射文件 {csv_path}")
            return
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                next(f)  # 跳过 Header: Name;FmName;Type;English
                for line in f:
                    parts = line.strip().split(';')
                    if len(parts) >= 2:
                        game_name = parts[0].strip()  # 游戏返回的 type
                        fm_name = parts[1].strip()    # FM 数据库中的 name
                        if game_name and fm_name:
                            self.name_to_fm[game_name] = fm_name
            print(f"成功加载 {len(self.name_to_fm)} 条名称映射")
        except Exception as e:
            print(f"加载名称映射出错: {e}")
        
    def load_db(self):
        csv_path = resource_path(os.path.join("FM", "fm_data_db.csv"))
        
        if not os.path.exists(csv_path):
            print(f"警告: 找不到数据文件 {csv_path}")
            return
            
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                next(f)  # 跳过 Header
                for line in f:
                    parts = line.strip().split(';')
                    if len(parts) >= 8:
                        name = parts[0]
                        
                        # 解析 CritAirSpd (index 6)
                        try:
                            parsed = self._parse_sweep_value(parts[6])
                            if parsed is not None:
                                self.crit_speeds[name] = parsed
                        except (ValueError, IndexError):
                            pass
                        
                        # 解析 CritAirSpdMach (index 7)
                        try:
                            parsed = self._parse_sweep_value(parts[7])
                            if parsed is not None:
                                self.crit_machs[name] = parsed
                        except (ValueError, IndexError):
                            pass
                            
            print(f"成功加载 {len(self.crit_speeds)} 条飞机数据")
        except Exception as e:
            print(f"加载数据库出错: {e}")

    def _resolve_name(self, plane_type):
        """
        解析飞机名称，尝试多种方式匹配数据库
        
        Args:
            plane_type: 游戏返回的飞机类型
            
        Returns:
            在 crit_speeds 中找到的有效名称，或 None
        """
        if not plane_type:
            return None
        
        # 1. 直接用原始名称查找
        if plane_type in self.crit_speeds:
            return plane_type
        
        # 2. 尝试通过 fm_names_db 映射查找
        fm_name = self.name_to_fm.get(plane_type)
        if fm_name and fm_name in self.crit_speeds:
            return fm_name
        
        return None

    def get_limit(self, plane_type, wing_sweep=None):
        """
        获取速度限制 (km/h)
        
        Args:
            plane_type: 飞机类型标识
            wing_sweep: 可变后掠翼位置 (0.0~1.0)，普通飞机忽略此参数
            
        Returns:
            速度限制值，未找到时返回 None
        """
        resolved = self._resolve_name(plane_type)
        if resolved is None:
            return None
        limit = self.crit_speeds.get(resolved)
        if limit is None:
            return None
        if isinstance(limit, list):
            return self._interpolate(limit, wing_sweep)
        return limit

    def get_mach_limit(self, plane_type, wing_sweep=None):
        """
        获取马赫数限制
        
        Args:
            plane_type: 飞机类型标识
            wing_sweep: 可变后掠翼位置 (0.0~1.0)，普通飞机忽略此参数
            
        Returns:
            马赫数限制值，未找到时返回 None
        """
        resolved = self._resolve_name(plane_type)
        if resolved is None:
            return None
        limit = self.crit_machs.get(resolved)
        if limit is None:
            return None
        if isinstance(limit, list):
            return self._interpolate(limit, wing_sweep)
        return limit
