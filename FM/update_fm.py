#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FM Database Update Tool
从 GitHub War Thunder Datamine 仓库更新本地飞行模型数据库

使用方法:
    python FM/update_fm.py --add-missing    # 添加缺失的飞机FM和名称映射
    python FM/update_fm.py --check-updates  # 检查并更新已有飞机的FM数据
    python FM/update_fm.py --sync-names     # 仅同步名称映射(不含FM)
    python FM/update_fm.py --all            # 执行全部操作

环境变量:
    GITHUB_TOKEN    # 设置 GitHub Token 以避免 API 限流
"""

import os
import sys
import json
import argparse
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# 确保可以导入 requests
try:
    import requests
except ImportError:
    print("错误: 需要安装 requests 库")
    print("运行: pip install requests")
    sys.exit(1)


# ============================================================================
# 常量配置
# ============================================================================

GITHUB_API_BASE = "https://api.github.com/repos/gszabi99/War-Thunder-Datamine/contents"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/gszabi99/War-Thunder-Datamine/master"
FM_PATH = "aces.vromfs.bin_u/gamedata/flightmodels"

# 本地文件路径 (相对于脚本所在目录)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FM_DATA_CSV = os.path.join(SCRIPT_DIR, "fm_data_db.csv")
FM_NAMES_CSV = os.path.join(SCRIPT_DIR, "fm_names_db.csv")
FM_VERSION_FILE = os.path.join(SCRIPT_DIR, "fm_version")

# CSV 列定义
FM_DATA_COLUMNS = [
    "Name", "Length", "WingSpan", "WingArea", "EmptyMass", "MaxFuelMass",
    "CritAirSpd", "CritAirSpdMach", "CritGearSpd", "CombatFlaps", "TakeoffFlaps",
    "CritFlapsSpd", "CritWingOverload", "NumEngines", "RPM", "MaxNitro",
    "NitroConsum", "CritAoA"
]

FM_NAMES_COLUMNS = ["Name", "FmName", "Type", "English"]

# 飞机类型映射
TYPE_MAP = {
    "typeFighter": "fighter",
    "typeBomber": "bomber",
    "typeAssault": "strike",
    "typeStormtrooper": "strike",
    "typeDiveBomber": "bomber",
    "typeTorpedo": "bomber",
    "typeTransport": "bomber",
    "typeHelicopter": "helicopter",
}


# ============================================================================
# BlkxParser - 解析 blkx 文件
# ============================================================================

class BlkxParser:
    """解析 War Thunder blkx 文件并提取飞行模型参数"""
    
    @staticmethod
    def parse_json(content: str) -> Optional[Dict]:
        """解析 JSON 内容"""
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"  JSON 解析错误: {e}")
            return None
    
    @staticmethod
    def safe_get(data: Dict, *keys, default=None):
        """安全地获取嵌套字典值"""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    @staticmethod
    def extract_fm_data(fm_content: str, fm_name: str) -> Optional[Dict]:
        """
        从 FM 文件内容提取飞行模型数据
        
        Args:
            fm_content: FM blkx 文件的 JSON 内容
            fm_name: FM 名称
            
        Returns:
            包含所有字段的字典，或 None 如果解析失败
        """
        data = BlkxParser.parse_json(fm_content)
        if not data:
            return None
        
        result = {"Name": fm_name}
        
        # Length - 根级
        result["Length"] = BlkxParser.safe_get(data, "Length", default="")
        
        # WingSpan - Aerodynamics.WingPlane.Span
        result["WingSpan"] = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "Span", default=""
        )
        
        # WingArea - 需要计算: 各区域面积之和
        wing_areas = BlkxParser.safe_get(data, "Aerodynamics", "WingPlane", "Areas", default={})
        if wing_areas:
            total_area = 0
            for key in ["LeftIn", "LeftMid", "LeftOut", "RightIn", "RightMid", "RightOut"]:
                val = wing_areas.get(key, 0)
                if isinstance(val, (int, float)):
                    total_area += val
            result["WingArea"] = round(total_area, 4) if total_area > 0 else ""
        else:
            result["WingArea"] = ""
        
        # EmptyMass - Mass.EmptyMass
        result["EmptyMass"] = BlkxParser.safe_get(data, "Mass", "EmptyMass", default="")
        
        # MaxFuelMass - Mass.MaxFuelMass0
        result["MaxFuelMass"] = BlkxParser.safe_get(data, "Mass", "MaxFuelMass0", default="")
        
        # CritAirSpd - Aerodynamics.WingPlane.Strength.VNE (首选) 或 VneControl (备选)
        crit_air_spd = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "Strength", "VNE", default=None
        )
        if crit_air_spd is None:
            crit_air_spd = BlkxParser.safe_get(data, "VneControl", default="")
        result["CritAirSpd"] = crit_air_spd
        
        # CritAirSpdMach - Aerodynamics.WingPlane.Strength.MNE (Mach Never Exceed)
        result["CritAirSpdMach"] = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "Strength", "MNE", default=""
        )
        
        # CritGearSpd - Mass.GearDestructionIndSpeed
        result["CritGearSpd"] = BlkxParser.safe_get(
            data, "Mass", "GearDestructionIndSpeed", default=""
        )
        
        # CombatFlaps - Aerodynamics.FlapsAxis.Combat
        # 仅当 Combat.Presents == True 时才有意义
        combat_axis = BlkxParser.safe_get(
            data, "Aerodynamics", "FlapsAxis", "Combat", default={}
        )
        if combat_axis.get("Presents", False):
            flaps_ratio = combat_axis.get("Flaps", 0)
            result["CombatFlaps"] = round(flaps_ratio * 100, 1) if flaps_ratio else 0
        else:
            result["CombatFlaps"] = 0
        
        # TakeoffFlaps (存储为百分比 0-100)
        takeoff_flaps_ratio = BlkxParser.safe_get(
            data, "Aerodynamics", "FlapsAxis", "Takeoff", "Flaps", default=None
        )
        if takeoff_flaps_ratio is not None:
            result["TakeoffFlaps"] = round(takeoff_flaps_ratio * 100, 1)
        else:
            result["TakeoffFlaps"] = 0
        
        # CritFlapsSpd - Mass.FlapsDestructionIndSpeedP 或 FlapsDestructionIndSpeedP0/P1
        flaps_spd = BlkxParser.safe_get(data, "Mass", "FlapsDestructionIndSpeedP", default=None)
        if flaps_spd and isinstance(flaps_spd, list):
            # 格式: [比例1, 速度1, 比例2, 速度2, ...]
            result["CritFlapsSpd"] = ",".join(str(v) for v in flaps_spd)
        else:
            # 尝试 FlapsDestructionIndSpeedP0/P1 格式
            mass = BlkxParser.safe_get(data, "Mass", default={})
            flaps_parts = []
            for i in range(10):  # 最多10个
                key = f"FlapsDestructionIndSpeedP{i}"
                val = mass.get(key)
                if val and isinstance(val, list):
                    flaps_parts.extend(val)
                elif val is None and i > 0:
                    break
            if flaps_parts:
                result["CritFlapsSpd"] = ",".join(str(v) for v in flaps_parts)
            else:
                result["CritFlapsSpd"] = ""
        
        # CritWingOverload - Aerodynamics.WingPlane.Strength.CritOverload
        crit_overload = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "Strength", "CritOverload", default=None
        )
        if crit_overload and isinstance(crit_overload, list) and len(crit_overload) >= 2:
            # 格式: [负过载, 正过载]
            result["CritWingOverload"] = f"{crit_overload[0]},{crit_overload[1]}"
        else:
            result["CritWingOverload"] = ""
        
        # NumEngines - 统计 EngineType* 数量
        num_engines = 0
        for key in data.keys():
            if key.startswith("EngineType") and key[10:].isdigit():
                num_engines += 1
        result["NumEngines"] = num_engines if num_engines > 0 else ""
        
        # RPM - EngineType0.Main 的 RPMMin, RPMMax, RPMMaxAllowed
        engine0 = BlkxParser.safe_get(data, "EngineType0", "Main", default={})
        rpm_min = engine0.get("RPMMin", "")
        rpm_max = engine0.get("RPMMax", "")
        rpm_allowed = engine0.get("RPMMaxAllowed", "")
        if rpm_min or rpm_max or rpm_allowed:
            result["RPM"] = f"{rpm_min},{rpm_max},{rpm_allowed}"
        else:
            result["RPM"] = ""
        
        # MaxNitro - Mass.MaxNitro
        result["MaxNitro"] = BlkxParser.safe_get(data, "Mass", "MaxNitro", default="")
        
        # NitroConsum - EngineType0.Mixer.NitroConsumption
        nitro_consum = BlkxParser.safe_get(
            data, "EngineType0", "Mixer", "NitroConsumption", default=None
        )
        result["NitroConsum"] = nitro_consum if nitro_consum is not None else 0
        
        # CritAoA - Aerodynamics.WingPlane.FlapsPolar0 的 alphaCritHigh, alphaCritLow
        polar0 = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "FlapsPolar0", default={}
        )
        aoa_high = polar0.get("alphaCritHigh", "")
        aoa_low = polar0.get("alphaCritLow", "")
        # 同时获取 FlapsPolar1 的值 (襟翼放下时)
        polar1 = BlkxParser.safe_get(
            data, "Aerodynamics", "WingPlane", "FlapsPolar1", default={}
        )
        aoa_high_flaps = polar1.get("alphaCritHigh", "")
        aoa_low_flaps = polar1.get("alphaCritLow", "")
        
        if aoa_high or aoa_low:
            result["CritAoA"] = f"{aoa_high},{aoa_low},{aoa_high_flaps},{aoa_low_flaps}"
        else:
            result["CritAoA"] = ""
        
        return result
    
    @staticmethod
    def extract_unit_info(unit_content: str) -> Optional[Dict]:
        """
        从单位文件提取飞机信息
        
        Returns:
            {"fm_name": ..., "type": ..., "english": ...}
        """
        data = BlkxParser.parse_json(unit_content)
        if not data:
            return None
        
        result = {}
        
        # fmFile 路径提取 fm 名称: "fm/xxx.blk" -> "xxx"
        fm_file = data.get("fmFile", "")
        if fm_file:
            fm_name = fm_file.replace("fm/", "").replace(".blk", "")
            result["fm_name"] = fm_name
        else:
            result["fm_name"] = ""
        
        # type - 可能是字符串或列表
        raw_type = data.get("type", "")
        # 如果是列表，取第一个元素
        if isinstance(raw_type, list):
            raw_type = raw_type[0] if raw_type else ""
        result["type"] = TYPE_MAP.get(raw_type, "fighter")
        
        # 英文名称 - 尝试从 wiki 获取
        wiki = data.get("wiki", {})
        general = wiki.get("general", {}) if wiki else {}
        # 实际上 wiki 里没有英文名，需要从其他地方获取
        # 暂时使用空值，后续可以从 lang 文件获取
        result["english"] = ""
        
        return result


# ============================================================================
# GitHubFetcher - GitHub API 和文件下载
# ============================================================================

class GitHubFetcher:
    """从 GitHub 获取 War Thunder Datamine 数据"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "WTFriendCounter-FM-Updater"
        })
        
        # 支持 GitHub Token 以避免 API 限流
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            self.session.headers["Authorization"] = f"token {github_token}"
            print("已配置 GitHub Token")
    
    def get_fm_file_list(self) -> List[str]:
        """
        获取 flightmodels/fm 目录下所有 FM 文件名
        
        Returns:
            FM 名称列表 (不含扩展名)
        """
        url = f"{GITHUB_API_BASE}/{FM_PATH}/fm"
        print(f"正在获取 FM 文件列表...")
        
        fm_names = []
        page = 1
        max_pages = 50  # 安全限制
        
        while page <= max_pages:
            try:
                resp = self.session.get(url, params={"per_page": 100, "page": page}, timeout=30)
                if resp.status_code == 403:
                    print("  警告: GitHub API 限流，请稍后重试或配置 GITHUB_TOKEN 环境变量")
                    return fm_names  # 返回已获取的部分
                if resp.status_code == 404:
                    print("  错误: 目录不存在")
                    return []
                resp.raise_for_status()
                
                files = resp.json()
                if not files or not isinstance(files, list):
                    break
                
                for f in files:
                    name = f.get("name", "")
                    if name.endswith(".blkx"):
                        # 去掉 .blkx 后缀
                        fm_name = name[:-5]
                        fm_names.append(fm_name)
                
                # 检查是否还有更多页
                if len(files) < 100:
                    break
                page += 1
                
            except requests.RequestException as e:
                print(f"  获取文件列表失败: {e}")
                break
        
        print(f"  找到 {len(fm_names)} 个 FM 文件")
        return fm_names
    
    def get_unit_file_list(self) -> List[str]:
        """
        获取 flightmodels 目录下所有单位文件名
        
        Returns:
            单位名称列表 (不含扩展名)
        """
        url = f"{GITHUB_API_BASE}/{FM_PATH}"
        print(f"正在获取单位文件列表...")
        
        unit_names = []
        page = 1
        
        while True:
            try:
                resp = self.session.get(url, params={"per_page": 100, "page": page}, timeout=30)
                if resp.status_code == 403:
                    print("  警告: GitHub API 限流")
                    break
                resp.raise_for_status()
                
                files = resp.json()
                if not files:
                    break
                
                for f in files:
                    if f.get("type") != "file":
                        continue
                    name = f.get("name", "")
                    if name.endswith(".blkx") and not name.startswith("fm_"):
                        unit_name = name[:-5]
                        unit_names.append(unit_name)
                
                if len(files) < 100:
                    break
                page += 1
                
            except requests.RequestException as e:
                print(f"  获取文件列表失败: {e}")
                break
        
        print(f"  找到 {len(unit_names)} 个单位文件")
        return unit_names
    
    def download_fm_file(self, fm_name: str) -> Optional[str]:
        """下载 FM 文件内容"""
        url = f"{GITHUB_RAW_BASE}/{FM_PATH}/fm/{fm_name}.blkx"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"  下载 {fm_name} 失败: {e}")
            return None
    
    def download_unit_file(self, unit_name: str) -> Optional[str]:
        """下载单位文件内容"""
        url = f"{GITHUB_RAW_BASE}/{FM_PATH}/{unit_name}.blkx"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"  下载 {unit_name} 失败: {e}")
            return None


# ============================================================================
# FMDatabase - 本地 CSV 数据库操作
# ============================================================================

class FMDatabase:
    """管理本地 FM CSV 数据库"""
    
    def __init__(self):
        self.data_records: Dict[str, Dict] = {}  # fm_name -> record
        self.names_records: Dict[str, Dict] = {}  # unit_name -> record
        self.load()
    
    def load(self):
        """加载本地 CSV 文件"""
        # 加载 fm_data_db.csv
        if os.path.exists(FM_DATA_CSV):
            with open(FM_DATA_CSV, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    # 跳过 header
                    for line in lines[1:]:
                        parts = line.strip().split(';')
                        if len(parts) >= 1 and parts[0]:
                            record = {}
                            for i, col in enumerate(FM_DATA_COLUMNS):
                                record[col] = parts[i] if i < len(parts) else ""
                            self.data_records[parts[0]] = record
        
        # 加载 fm_names_db.csv
        if os.path.exists(FM_NAMES_CSV):
            with open(FM_NAMES_CSV, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    for line in lines[1:]:
                        parts = line.strip().split(';')
                        if len(parts) >= 1 and parts[0]:
                            record = {}
                            for i, col in enumerate(FM_NAMES_COLUMNS):
                                record[col] = parts[i] if i < len(parts) else ""
                            self.names_records[parts[0]] = record
        
        print(f"已加载 {len(self.data_records)} 条 FM 数据, {len(self.names_records)} 条名称映射")
    
    def backup(self):
        """备份当前数据文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(SCRIPT_DIR, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        if os.path.exists(FM_DATA_CSV):
            backup_path = os.path.join(backup_dir, f"fm_data_db_{timestamp}.csv")
            shutil.copy(FM_DATA_CSV, backup_path)
            print(f"已备份: {backup_path}")
        
        if os.path.exists(FM_NAMES_CSV):
            backup_path = os.path.join(backup_dir, f"fm_names_db_{timestamp}.csv")
            shutil.copy(FM_NAMES_CSV, backup_path)
    
    def save_data(self):
        """保存 fm_data_db.csv"""
        with open(FM_DATA_CSV, 'w', encoding='utf-8', newline='') as f:
            # Header
            f.write(';'.join(FM_DATA_COLUMNS) + '\n')
            # Data (按名称排序)
            for name in sorted(self.data_records.keys()):
                record = self.data_records[name]
                values = [str(record.get(col, "")) for col in FM_DATA_COLUMNS]
                f.write(';'.join(values) + '\n')
        print(f"已保存 {len(self.data_records)} 条 FM 数据")
    
    def save_names(self):
        """保存 fm_names_db.csv"""
        with open(FM_NAMES_CSV, 'w', encoding='utf-8', newline='') as f:
            # Header
            f.write(';'.join(FM_NAMES_COLUMNS) + '\n')
            # Data (按名称排序)
            for name in sorted(self.names_records.keys()):
                record = self.names_records[name]
                values = [str(record.get(col, "")) for col in FM_NAMES_COLUMNS]
                f.write(';'.join(values) + '\n')
        print(f"已保存 {len(self.names_records)} 条名称映射")
    
    def get_existing_fm_names(self) -> set:
        """获取已存在的 FM 名称集合"""
        return set(self.data_records.keys())
    
    def get_existing_unit_names(self) -> set:
        """获取已存在的单位名称集合"""
        return set(self.names_records.keys())
    
    def add_data_record(self, record: Dict):
        """添加或更新 FM 数据记录"""
        name = record.get("Name", "")
        if name:
            self.data_records[name] = record
    
    def add_names_record(self, unit_name: str, fm_name: str, unit_type: str, english: str):
        """添加或更新名称映射记录"""
        self.names_records[unit_name] = {
            "Name": unit_name,
            "FmName": fm_name,
            "Type": unit_type,
            "English": english
        }
    
    @staticmethod
    def _values_equal(old_val, new_val) -> bool:
        """比较两个值是否相等，支持数值和逗号分隔的复合值"""
        old_str = str(old_val).strip()
        new_str = str(new_val).strip()
        
        if old_str == new_str:
            return True
        
        # 检查是否是逗号分隔的复合值
        if ',' in old_str or ',' in new_str:
            old_parts = old_str.split(',')
            new_parts = new_str.split(',')
            
            if len(old_parts) != len(new_parts):
                return False
            
            for o, n in zip(old_parts, new_parts):
                if not FMDatabase._values_equal(o.strip(), n.strip()):
                    return False
            return True
        
        # 尝试数值比较
        try:
            old_num = float(old_str) if old_str else None
            new_num = float(new_str) if new_str else None
            
            if old_num is not None and new_num is not None:
                return abs(old_num - new_num) < 0.001
            return old_num == new_num
        except (ValueError, TypeError):
            return False
    
    def compare_records(self, old: Dict, new: Dict) -> List[Tuple[str, Any, Any]]:
        """比较两条记录的差异，返回 [(字段名, 旧值, 新值), ...]"""
        diffs = []
        for col in FM_DATA_COLUMNS:
            old_val = old.get(col, "")
            new_val = new.get(col, "")
            
            if not self._values_equal(old_val, new_val):
                diffs.append((col, old_val, new_val))
        return diffs


# ============================================================================
# 主要功能函数
# ============================================================================

def add_missing_aircraft(db: FMDatabase, fetcher: GitHubFetcher):
    """功能1: 添加缺失的飞机（同时更新 FM 数据和名称映射）"""
    print("\n" + "="*60)
    print("功能1: 检索并添加缺失的飞机")
    print("="*60)
    
    # 获取远程 FM 列表
    remote_fm_names = set(fetcher.get_fm_file_list())
    if not remote_fm_names:
        print("错误: 无法获取远程 FM 列表")
        return
    
    # 获取远程单位列表（用于名称映射）
    remote_unit_names = fetcher.get_unit_file_list()
    
    # 计算缺失的 FM
    local_fm_names = db.get_existing_fm_names()
    missing_fm = remote_fm_names - local_fm_names
    
    # 计算缺失的单位名称映射
    local_unit_names = db.get_existing_unit_names()
    missing_units = set(remote_unit_names) - local_unit_names
    
    print(f"\nFM 数据: 本地 {len(local_fm_names)} 个, 远程 {len(remote_fm_names)} 个, 缺失 {len(missing_fm)} 个")
    print(f"名称映射: 本地 {len(local_unit_names)} 个, 远程 {len(remote_unit_names)} 个, 缺失 {len(missing_units)} 个")
    
    if not missing_fm and not missing_units:
        print("没有缺失的数据需要添加")
        return
    
    # 显示缺失列表并确认
    if missing_fm:
        print("\n缺失的 FM 列表:")
        for name in sorted(missing_fm)[:10]:
            print(f"  - {name}")
        if len(missing_fm) > 10:
            print(f"  ... 还有 {len(missing_fm) - 10} 个")
    
    if missing_units:
        print("\n缺失的单位映射:")
        for name in sorted(missing_units)[:10]:
            print(f"  - {name}")
        if len(missing_units) > 10:
            print(f"  ... 还有 {len(missing_units) - 10} 个")
    
    confirm = input(f"\n是否添加缺失的数据? (y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return
    
    # 备份
    db.backup()
    
    # 下载并解析缺失的 FM
    fm_added = 0
    if missing_fm:
        print(f"\n正在添加 {len(missing_fm)} 个 FM...")
        for i, fm_name in enumerate(sorted(missing_fm), 1):
            print(f"\r[{i}/{len(missing_fm)}] FM: {fm_name}".ljust(60), end="")
            
            content = fetcher.download_fm_file(fm_name)
            if not content:
                continue
            
            record = BlkxParser.extract_fm_data(content, fm_name)
            if not record:
                continue
            
            db.add_data_record(record)
            fm_added += 1
        print()
    
    # 下载并解析缺失的单位名称映射
    units_added = 0
    if missing_units:
        print(f"\n正在添加 {len(missing_units)} 个单位映射...")
        for i, unit_name in enumerate(sorted(missing_units), 1):
            print(f"\r[{i}/{len(missing_units)}] 单位: {unit_name}".ljust(60), end="")
            
            content = fetcher.download_unit_file(unit_name)
            if not content:
                continue
            
            info = BlkxParser.extract_unit_info(content)
            if not info:
                continue
            
            # 跳过直升机
            if info.get("type") == "helicopter":
                continue
            
            db.add_names_record(
                unit_name,
                info.get("fm_name", unit_name),
                info.get("type", "fighter"),
                info.get("english", unit_name)
            )
            units_added += 1
        print()
    
    # 保存
    if fm_added > 0:
        db.save_data()
    if units_added > 0:
        db.save_names()
    
    print(f"\n完成! 添加了 {fm_added} 个 FM, {units_added} 个单位映射")


def check_and_update_aircraft(db: FMDatabase, fetcher: GitHubFetcher):
    """功能2: 检查并更新已有飞机"""
    print("\n" + "="*60)
    print("功能2: 检查并更新已有飞机")
    print("="*60)
    
    local_fm_names = sorted(db.get_existing_fm_names())
    print(f"本地共有 {len(local_fm_names)} 个 FM 需要检查")
    
    if not local_fm_names:
        print("本地没有 FM 数据")
        return
    
    confirm = input(f"开始检查? 这可能需要一些时间 (y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return
    
    # 备份
    db.backup()
    
    changes = []  # [(fm_name, diffs), ...]
    
    for i, fm_name in enumerate(local_fm_names, 1):
        print(f"\r[{i}/{len(local_fm_names)}] 检查: {fm_name}".ljust(60), end="")
        
        content = fetcher.download_fm_file(fm_name)
        if not content:
            continue
        
        new_record = BlkxParser.extract_fm_data(content, fm_name)
        if not new_record:
            continue
        
        old_record = db.data_records.get(fm_name, {})
        diffs = db.compare_records(old_record, new_record)
        
        if diffs:
            changes.append((fm_name, diffs, new_record))
    
    print("\n")
    
    if not changes:
        print("没有发现任何更改")
        return
    
    print(f"发现 {len(changes)} 个 FM 有更改:\n")
    
    updated_count = 0
    for fm_name, diffs, new_record in changes:
        print(f"\n【{fm_name}】")
        for col, old_val, new_val in diffs:
            # 转换为字符串并截断过长的值
            old_str = str(old_val)
            new_str = str(new_val)
            old_display = old_str[:30] + "..." if len(old_str) > 30 else old_str
            new_display = new_str[:30] + "..." if len(new_str) > 30 else new_str
            print(f"  {col}: {old_display} -> {new_display}")
        
        choice = input("  更新这个 FM? (y/N/a=全部更新/q=退出): ").strip().lower()
        
        if choice == 'q':
            print("已退出")
            break
        elif choice == 'a':
            # 更新当前及所有后续
            db.add_data_record(new_record)
            updated_count += 1
            for fm2, diffs2, rec2 in changes[changes.index((fm_name, diffs, new_record))+1:]:
                db.add_data_record(rec2)
                updated_count += 1
            break
        elif choice == 'y':
            db.add_data_record(new_record)
            updated_count += 1
    
    if updated_count > 0:
        db.save_data()
        print(f"\n完成! 更新了 {updated_count} 个 FM")
    else:
        print("\n没有进行任何更新")


def sync_names_database(db: FMDatabase, fetcher: GitHubFetcher):
    """同步名称数据库 (单位 -> FM 映射)"""
    print("\n" + "="*60)
    print("同步名称数据库")
    print("="*60)
    
    # 获取远程单位列表
    remote_units = set(fetcher.get_unit_file_list())
    local_units = db.get_existing_unit_names()
    
    missing_units = remote_units - local_units
    print(f"本地: {len(local_units)}, 远程: {len(remote_units)}, 缺失: {len(missing_units)}")
    
    if not missing_units:
        print("名称数据库已是最新")
        return
    
    confirm = input(f"是否添加 {len(missing_units)} 个缺失的单位映射? (y/N): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return
    
    added = 0
    for i, unit_name in enumerate(sorted(missing_units), 1):
        print(f"\r[{i}/{len(missing_units)}] 处理: {unit_name}".ljust(60), end="")
        
        content = fetcher.download_unit_file(unit_name)
        if not content:
            continue
        
        info = BlkxParser.extract_unit_info(content)
        if not info:
            continue
        
        # 跳过直升机
        if info.get("type") == "helicopter":
            continue
        
        db.add_names_record(
            unit_name,
            info.get("fm_name", unit_name),
            info.get("type", "fighter"),
            info.get("english", unit_name)
        )
        added += 1
    
    print("\n")
    if added > 0:
        db.save_names()
        print(f"添加了 {added} 个单位映射")


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="FM 数据库更新工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python FM/update_fm.py --add-missing     # 添加缺失的飞机
  python FM/update_fm.py --check-updates   # 检查并更新已有飞机
  python FM/update_fm.py --sync-names      # 同步名称数据库
  python FM/update_fm.py --all             # 执行全部操作
        """
    )
    
    parser.add_argument("--add-missing", action="store_true",
                        help="添加缺失的飞机FM和名称映射")
    parser.add_argument("--check-updates", action="store_true",
                        help="检查并更新已有飞机的FM数据")
    parser.add_argument("--sync-names", action="store_true",
                        help="仅同步名称映射数据库(不含FM)")
    parser.add_argument("--all", action="store_true",
                        help="执行全部操作")
    
    args = parser.parse_args()
    
    # 如果没有任何参数，显示帮助
    if not any([args.add_missing, args.check_updates, args.sync_names, args.all]):
        parser.print_help()
        return
    
    print("="*60)
    print("FM 数据库更新工具")
    print("="*60)
    
    db = FMDatabase()
    fetcher = GitHubFetcher()
    
    if args.all or args.add_missing:
        add_missing_aircraft(db, fetcher)
    
    if args.all or args.check_updates:
        check_and_update_aircraft(db, fetcher)
    
    if args.all or args.sync_names:
        sync_names_database(db, fetcher)
    
    print("\n全部操作完成!")


if __name__ == "__main__":
    main()

