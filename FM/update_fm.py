#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FM Database Update Tool
从 GitHub War Thunder Datamine 仓库更新本地飞行模型数据库

使用方法:
         # 添加缺失的飞机FM和名称映射
    python update_fm.py --check-updates  # 检查并更新已有飞机的FM数据
    python update_fm.py --all            # 执行全部操作

环境变量:
    GITHUB_TOKEN    # 设置 GitHub Token 以避免 API 限流
"""

import os
import sys
import json
import argparse
import shutil
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set

# 自动入口只使用标准库；交互入口按需使用这些辅助依赖。
try:
    import requests
except ImportError:
    requests = None
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, **_kwargs):
        return iterable


# ============================================================================
# 常量配置
# ============================================================================

GITHUB_API_BASE = "https://api.github.com/repos/gszabi99/War-Thunder-Datamine/contents"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/gszabi99/War-Thunder-Datamine/master"
GITHUB_TREE_API = "https://api.github.com/repos/gszabi99/War-Thunder-Datamine/git/trees/master"
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
        
        # 英文名称 - 暂时使用空值
        result["english"] = ""
        
        return result


# ============================================================================
# GitHubFetcher - GitHub API 和文件下载
# ============================================================================

class GitHubFetcher:
    """从 GitHub 获取 War Thunder Datamine 数据"""
    
    def __init__(self):
        if requests is None:
            raise RuntimeError("交互更新需要 requests；请先运行 pip install requests")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "WTFM-Updater"
        })
        
        # 缓存仓库文件树
        self._tree_cache = None
        
        # 支持 GitHub Token 以避免 API 限流
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            self.session.headers["Authorization"] = f"token {github_token}"
            print("已配置 GitHub Token")
    
    def _get_repo_tree(self) -> List[Dict]:
        """获取并缓存仓库文件树"""
        if self._tree_cache is not None:
            return self._tree_cache
        
        tree_url = f"{GITHUB_TREE_API}?recursive=1"
        
        try:
            print("  正在获取仓库文件树 (首次获取可能需要较长时间)...")
            resp = self.session.get(tree_url, timeout=120)
            if resp.status_code == 403:
                print("  警告: GitHub API 限流，请稍后重试或配置 GITHUB_TOKEN 环境变量")
                return []
            resp.raise_for_status()
            
            data = resp.json()
            self._tree_cache = data.get("tree", [])
            print(f"  文件树获取完成，共 {len(self._tree_cache)} 个条目")
            return self._tree_cache
            
        except requests.RequestException as e:
            print(f"  获取文件树失败: {e}")
            return []
    
    def get_fm_file_list(self) -> List[str]:
        """
        获取 flightmodels/fm 目录下所有 FM 文件名
        使用 Git Trees API 一次性获取完整目录树（避免分页问题）
        
        Returns:
            FM 名称列表 (不含扩展名)
        """
        print(f"正在获取 FM 文件列表...")
        
        tree = self._get_repo_tree()
        if not tree:
            return []
        
        fm_names = []
        fm_prefix = f"{FM_PATH}/fm/"
        
        for item in tree:
            path = item.get("path", "")
            if path.startswith(fm_prefix) and path.endswith(".blkx"):
                # 提取文件名并去掉 .blkx 后缀
                filename = path[len(fm_prefix):]
                fm_name = filename[:-5]  # 去掉 .blkx
                fm_names.append(fm_name)
        
        print(f"  总共找到 {len(fm_names)} 个 FM 文件")
        return fm_names
    
    def get_unit_file_list(self) -> List[str]:
        """
        获取 flightmodels 目录下所有单位文件名
        使用 Git Trees API 一次性获取完整目录树（避免分页问题）
        
        Returns:
            单位名称列表 (不含扩展名)
        """
        print(f"正在获取单位文件列表...")
        
        tree = self._get_repo_tree()
        if not tree:
            return []
        
        unit_names = []
        unit_prefix = f"{FM_PATH}/"
        fm_subdir = f"{FM_PATH}/fm/"
        
        for item in tree:
            path = item.get("path", "")
            item_type = item.get("type", "")
            
            # 只要 flightmodels 目录下的直接文件（不包括子目录如 fm/）
            if item_type != "blob":
                continue
            if not path.startswith(unit_prefix):
                continue
            if path.startswith(fm_subdir):
                continue  # 跳过 fm/ 子目录下的文件
            if not path.endswith(".blkx"):
                continue
            
            # 提取文件名
            filename = path[len(unit_prefix):]
            # 跳过子目录中的文件
            if "/" in filename:
                continue
                
            unit_name = filename[:-5]  # 去掉 .blkx
            unit_names.append(unit_name)
        
        print(f"  总共找到 {len(unit_names)} 个单位文件")
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
    
    def get_existing_fm_names(self) -> Set[str]:
        """获取已存在的 FM 名称集合"""
        return set(self.data_records.keys())
    
    def get_existing_unit_names(self) -> Set[str]:
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
# 功能1: 添加缺失的飞机
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
        for fm_name in tqdm(sorted(missing_fm), desc="添加FM数据"):
            content = fetcher.download_fm_file(fm_name)
            if not content:
                continue
            
            record = BlkxParser.extract_fm_data(content, fm_name)
            if not record:
                continue
            
            db.add_data_record(record)
            fm_added += 1
    
    # 下载并解析缺失的单位名称映射
    units_added = 0
    if missing_units:
        print(f"\n正在添加 {len(missing_units)} 个单位映射...")
        for unit_name in tqdm(sorted(missing_units), desc="添加名称映射"):
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
    
    # 保存
    if fm_added > 0:
        db.save_data()
    if units_added > 0:
        db.save_names()
    
    print(f"\n完成! 添加了 {fm_added} 个 FM, {units_added} 个单位映射")


# ============================================================================
# 功能2: 检查并更新已有飞机
# ============================================================================

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
    
    changes = []  # [(fm_name, diffs, new_record), ...]
    
    print("\n正在检查更新...")
    for fm_name in tqdm(local_fm_names, desc="检查FM数据"):
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
    
    print()
    
    if not changes:
        print("没有发现任何更改")
        return
    
    print(f"发现 {len(changes)} 个 FM 有更改:\n")
    
    updated_count = 0
    update_all = False
    
    for i, (fm_name, diffs, new_record) in enumerate(changes):
        print(f"\n【{fm_name}】({i+1}/{len(changes)})")
        for col, old_val, new_val in diffs:
            # 转换为字符串并截断过长的值
            old_str = str(old_val)
            new_str = str(new_val)
            old_display = old_str[:30] + "..." if len(old_str) > 30 else old_str
            new_display = new_str[:30] + "..." if len(new_str) > 30 else new_str
            print(f"  {col}: {old_display} -> {new_display}")
        
        if update_all:
            db.add_data_record(new_record)
            updated_count += 1
            continue
        
        choice = input("  更新? (y=是/n=否/a=全部更新/q=退出): ").strip().lower()
        
        if choice == 'q':
            print("已退出")
            break
        elif choice == 'a':
            update_all = True
            db.add_data_record(new_record)
            updated_count += 1
        elif choice == 'y':
            db.add_data_record(new_record)
            updated_count += 1
    
    if updated_count > 0:
        db.save_data()
        print(f"\n完成! 更新了 {updated_count} 个 FM")
    else:
        print("\n没有进行任何更新")


# ============================================================================
# GitHub Actions 非交互发布入口
# ============================================================================

def _read_records(path: Path, columns: List[str]) -> Dict[str, Dict]:
    records = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames != columns:
            raise ValueError(f"{path.name} 表头不符合预期")
        for row in reader:
            name = (row.get("Name") or "").strip()
            if not name or name in records:
                raise ValueError(f"{path.name} 包含空键或重复键: {name}")
            records[name] = {column: row.get(column, "") for column in columns}
    if not records:
        raise ValueError(f"{path.name} 没有有效数据")
    return records


def _write_records(path: Path, records: Dict[str, Dict], columns: List[str]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", lineterminator="\n")
        writer.writeheader()
        for name in sorted(records):
            writer.writerow({column: records[name].get(column, "") for column in columns})


def _records_equal(left: Dict[str, Dict], right: Dict[str, Dict], columns: List[str]) -> bool:
    if set(left) != set(right):
        return False
    for name in left:
        for column in columns:
            if not FMDatabase._values_equal(left[name].get(column, ""), right[name].get(column, "")):
                return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _change_notes(old_data, new_data, old_names, new_names) -> str:
    added_fm = sorted(set(new_data) - set(old_data))
    changed_fm = sorted(
        name for name in set(old_data) & set(new_data)
        if not _records_equal({name: old_data[name]}, {name: new_data[name]}, FM_DATA_COLUMNS)
    )
    added_names = sorted(set(new_names) - set(old_names))
    changed_names = sorted(
        name for name in set(old_names) & set(new_names)
        if old_names[name] != new_names[name]
    )
    parts = []
    if added_fm:
        parts.append(f"新增 {len(added_fm)} 个机型")
    if changed_fm:
        parts.append(f"更新 {len(changed_fm)} 个机型的飞行限制")
    if added_names:
        parts.append(f"新增 {len(added_names)} 条名称映射")
    if changed_names:
        parts.append(f"更新 {len(changed_names)} 条名称映射")
    details = added_fm + changed_fm + added_names + changed_names
    note = "；".join(parts)
    if details:
        shown = "、".join(details[:12])
        note += f"。涉及：{shown}"
        if len(details) > 12:
            note += f" 等 {len(details)} 项"
    return note


def run_automation(source_dir: str, source_commit: str, repo_root: str) -> int:
    root = Path(repo_root).resolve()
    fm_root = root / "FM"
    source = Path(source_dir).resolve()
    source_fm = source / "fm"
    if not source_fm.is_dir():
        raise ValueError("上游 flightmodels/fm 目录不存在")
    if len(source_commit) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in source_commit):
        raise ValueError("source_commit 必须是固定的完整 SHA")

    state_path = fm_root / "check_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    if state.get("last_checked_commit") == source_commit:
        print("上游提交未变化，不生成 FM 版本")
        return 0

    old_data = _read_records(fm_root / "fm_data_db.csv", FM_DATA_COLUMNS)
    old_names = _read_records(fm_root / "fm_names_db.csv", FM_NAMES_COLUMNS)
    new_data = {name: record.copy() for name, record in old_data.items()}
    new_names = {name: record.copy() for name, record in old_names.items()}

    fm_files = sorted(source_fm.glob("*.blkx"))
    unit_files = sorted(source.glob("*.blkx"))
    if not fm_files or not unit_files:
        raise ValueError("上游 FM 或单位文件列表为空")
    for path in fm_files:
        content = path.read_text(encoding="utf-8")
        parsed = BlkxParser.parse_json(content)
        if parsed == {}:
            # 上游保留少量空占位 FM；沿用基线的已知缺失，不发布空记录。
            continue
        if parsed is None:
            raise ValueError(f"解析失败: {path.name}")
        record = BlkxParser.extract_fm_data(content, path.stem)
        if record is None:
            raise ValueError(f"解析失败: {path.name}")
        new_data[path.stem] = {column: record.get(column, "") for column in FM_DATA_COLUMNS}
    for path in unit_files:
        info = BlkxParser.extract_unit_info(path.read_text(encoding="utf-8"))
        if info is None:
            raise ValueError(f"解析失败: {path.name}")
        fm_name = info.get("fm_name", "")
        if info.get("type") == "helicopter" or not fm_name or fm_name not in new_data:
            continue
        old_english = old_names.get(path.stem, {}).get("English", "")
        new_names[path.stem] = {
            "Name": path.stem,
            "FmName": fm_name,
            "Type": info.get("type", "fighter"),
            "English": info.get("english") or old_english,
        }

    data_changed = not _records_equal(old_data, new_data, FM_DATA_COLUMNS)
    names_changed = old_names != new_names
    index_path = fm_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    has_automatic = any(version.get("kind") == "automatic" for version in index.get("versions", []))
    state["last_checked_commit"] = source_commit
    state["checked_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if not data_changed and not names_changed and has_automatic:
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("有效 FM 数据未变化，不生成版本")
        return 0

    now = datetime.now(timezone.utc)
    version_id = now.strftime("fm-%Y%m%d-%H%M%S-") + source_commit[:8].lower() + "-automatic"
    published_at = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    notes = (_change_notes(old_data, new_data, old_names, new_names)
             if data_changed or names_changed
             else "首次自动构建，与人工稳定版数据一致")
    version_dir = fm_root / "versions" / version_id
    version_dir.mkdir(parents=True, exist_ok=False)
    _write_records(version_dir / "fm_data_db.csv", new_data, FM_DATA_COLUMNS)
    _write_records(version_dir / "fm_names_db.csv", new_names, FM_NAMES_COLUMNS)
    _write_records(fm_root / "fm_data_db.csv", new_data, FM_DATA_COLUMNS)
    _write_records(fm_root / "fm_names_db.csv", new_names, FM_NAMES_COLUMNS)

    files = {}
    for filename in ("fm_data_db.csv", "fm_names_db.csv"):
        path = version_dir / filename
        files[filename] = {
            "url": f"https://raw.githubusercontent.com/KaerMorh/WTSpeeder/main/FM/versions/{version_id}/{filename}",
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        }
    manifest = {
        "id": version_id,
        "published_at": published_at,
        "kind": "automatic",
        "notes": notes,
        "schema_version": 1,
        "source_commit": source_commit.lower(),
        "files": files,
    }
    (version_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index.setdefault("versions", []).append(manifest)
    index["versions"] = sorted(
        index["versions"], key=lambda value: (value["published_at"], value["id"]), reverse=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成 {version_id}: {notes}")
    return 0


# ============================================================================
# 主入口
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="FM 数据库更新工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python update_fm.py --add-missing     # 添加缺失的飞机
  python update_fm.py --check-updates   # 检查并更新已有飞机
  python update_fm.py --all             # 执行全部操作
        """
    )
    
    parser.add_argument("--add-missing", action="store_true",
                        help="添加缺失的飞机FM和名称映射")
    parser.add_argument("--check-updates", action="store_true",
                        help="检查并更新已有飞机的FM数据")
    parser.add_argument("--all", action="store_true",
                        help="执行全部操作")
    parser.add_argument("--automation", action="store_true",
                        help="从固定提交的本地上游目录执行非交互自动发布")
    parser.add_argument("--source-dir", help="上游 flightmodels 目录")
    parser.add_argument("--source-commit", help="上游完整提交 SHA")
    parser.add_argument("--repo-root", default=os.path.dirname(SCRIPT_DIR), help="本仓库根目录")
    
    args = parser.parse_args()
    
    # 如果没有任何参数，显示帮助
    if not any([args.add_missing, args.check_updates, args.all, args.automation]):
        parser.print_help()
        return

    if args.automation:
        if not args.source_dir or not args.source_commit:
            parser.error("--automation 需要 --source-dir 和 --source-commit")
        return run_automation(args.source_dir, args.source_commit, args.repo_root)
    
    print("="*60)
    print("FM 数据库更新工具")
    print("="*60)
    
    db = FMDatabase()
    fetcher = GitHubFetcher()
    
    if args.all or args.add_missing:
        add_missing_aircraft(db, fetcher)
    
    if args.all or args.check_updates:
        check_and_update_aircraft(db, fetcher)
    
    print("\n全部操作完成!")


if __name__ == "__main__":
    main()
