import os
import time
import datetime
import csv

class CSVLogger:
    def __init__(self):
        self.file = None
        self.writer = None
        self.start_time = 0
        self.session_active = False

    def start_new_session(self):
        """开始新的日志会话，创建文件"""
        if self.session_active:
            self.stop_session()

        # 确保 logs 目录存在
        log_dir = os.path.join(os.getcwd(), 'logs')
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except Exception as e:
                print(f"无法创建日志目录: {e}")
                return

        # 创建文件名 logs/log_YYYYMMDD_HHMMSS.csv
        filename = f"log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(log_dir, filename)

        try:
            self.file = open(filepath, 'w', newline='', encoding='utf-8')
            self.writer = csv.writer(self.file)
            
            # 写入表头
            headers = [
                'Timestamp',        # 格式化时间 HH:MM:SS.mmm
                'Unix_Time',        # Unix 时间戳
                'IAS_kmh',          # 指示空速
                'TAS_kmh',          # 真空速 (地速参考)
                'Altitude_m',       # 高度
                'Mach',             # 马赫数
                'Airbrake_Pct',     # 减速板开度 %
                'Throttle_In',      # 油门输入
                'Throttle_Out_Pct', # 引擎输出 %
                'Exp_Action',       # 实验动作类型
                'Exp_Reason'        # 实验触发原因
            ]
            self.writer.writerow(headers)
            self.file.flush()
            
            self.session_active = True
            print(f"日志记录已开启: {filepath}")
            
        except Exception as e:
            print(f"创建日志文件失败: {e}")
            self.session_active = False

    def stop_session(self):
        """停止日志记录并关闭文件"""
        if self.file:
            try:
                self.file.close()
            except:
                pass
            self.file = None
            self.writer = None
        
        self.session_active = False
        print("日志记录已停止")

    def log_step(self, data, auto_result):
        """
        记录一步数据
        data: get_telemetry() 的返回字典
        auto_result: ab_mgr.update() 的返回字典
        """
        if not self.session_active or not self.writer:
            return

        try:
            now = datetime.datetime.now()
            time_str = now.strftime('%H:%M:%S.%f')[:-3] # HH:MM:SS.mmm
            
            # 提取数据，处理 None
            row = [
                time_str,
                f"{time.time():.3f}",
                data.get('ias_kmh', ''),
                data.get('tas_kmh', ''),
                data.get('altitude', ''),
                data.get('mach', ''),
                data.get('airbrake', ''),
                data.get('throttle_in', ''),
                data.get('throttle_out', ''),
                auto_result.get('action_type', '') if auto_result else '',
                auto_result.get('reason', '') if auto_result else ''
            ]
            
            self.writer.writerow(row)
            # 实时刷新，防止崩溃丢失数据
            self.file.flush()
            
        except Exception as e:
            print(f"写入日志失败: {e}")
            # 如果出错次数太多可能需要停止，暂时忽略

