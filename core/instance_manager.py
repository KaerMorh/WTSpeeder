import socket
import threading
import time
import sys
import os

# 配置常量
PORT = 58621
HOST = '127.0.0.1'
MAGIC_KEY = "Overlay_App_Secret_Key_v1"
CMD_KILL = f"{MAGIC_KEY}:KILL".encode('utf-8')
CMD_KILL_LEGACY = b"KILL"

class InstanceManager:
    def __init__(self):
        self.server_socket = None
        self.is_running = True
        self.shutdown_callback = None
        self._thread = None

    def register_shutdown_callback(self, func):
        """注册退出清理函数"""
        self.shutdown_callback = func

    def ensure_single_instance(self):
        """
        尝试绑定端口，如果被占用则“杀旧启新”。
        返回 True 表示成功抢占并启动；返回 False 表示失败。
        """
        max_retries = 20
        
        for i in range(max_retries):
            try:
                # 创建 socket
                # 严禁设置 SO_REUSEADDR，以确保在 Windows 下能正确触发端口冲突异常
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # 尝试绑定
                self.server_socket.bind((HOST, PORT))
                self.server_socket.listen(1)
                
                print(f"[InstanceManager] Successfully bound to port {PORT}. I am the primary instance.")
                
                # 启动监听线程
                self._thread = threading.Thread(target=self._listen_loop, daemon=True)
                self._thread.start()
                return True
                
            except OSError:
                # 端口被占用，说明已有实例
                if self.server_socket:
                    self.server_socket.close()
                
                print(f"[InstanceManager] Port occupied. Attempt {i+1}/{max_retries}. Sending KILL...")
                
                # 发送关闭指令
                self._send_kill_signal()
                
                # 极速等待：只等 0.1 秒，快速抢占
                time.sleep(0.1)
        
        print("[InstanceManager] Failed to bind port after multiple attempts.")
        return False

    def _send_kill_signal(self):
        """连接旧实例并发送退出指令（支持向下兼容）"""
        try:
            # 1. 尝试发送带 Magic Key 的新指令
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((HOST, PORT))
            client.sendall(CMD_KILL)
            client.close()
            
            # 短暂等待看对方是否处理
            time.sleep(0.1)
            
            # 2. 再次尝试连接以检查是否还需要发送旧版指令
            # (向下兼容逻辑：如果对方没死，可能是旧版本不识别 Magic Key)
            try:
                client_check = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_check.connect((HOST, PORT))
                # 如果还能连上，说明对方没退，发旧版指令兜底
                print("[InstanceManager] Target still alive, trying legacy KILL command...")
                client_check.sendall(CMD_KILL_LEGACY)
                client_check.close()
            except ConnectionRefusedError:
                # 连接失败说明对方已经退出了，无需多做
                pass
                
        except ConnectionRefusedError:
            # 第一次连接就失败，说明对方正在退出或已经退出
            pass
        except Exception as e:
            print(f"[InstanceManager] Error sending kill signal: {e}")

    def _listen_loop(self):
        """监听端口指令"""
        while self.is_running:
            try:
                conn, addr = self.server_socket.accept()
                with conn:
                    data = conn.recv(1024)
                    
                    # 校验指令 (支持新版和旧版)
                    if data == CMD_KILL or data == CMD_KILL_LEGACY:
                        print(f"[InstanceManager] Received KILL signal ({data}). Shutting down...")
                        
                        # 1. 极速释放：立即停止标志位并关闭 socket
                        self.is_running = False
                        try:
                            self.server_socket.close()
                        except:
                            pass
                        
                        # 2. 执行清理
                        if self.shutdown_callback:
                            try:
                                self.shutdown_callback()
                            except Exception as e:
                                print(f"Error in shutdown callback: {e}")
                        
                        # 3. 强制退出兜底 (Daemon线程)
                        def force_exit():
                            time.sleep(2.0)
                            print("[InstanceManager] Force exiting...")
                            os._exit(0)
                            
                        threading.Thread(target=force_exit, daemon=True).start()
                        
                        # 4. 主动退出
                        sys.exit(0)
                        
            except OSError:
                # socket closed
                break
            except Exception as e:
                print(f"[InstanceManager] Error in listen loop: {e}")

    def cleanup(self):
        """主动清理资源"""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
