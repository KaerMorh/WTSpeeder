这是一个基于 Python 开发的**《战争雷霆》（War Thunder）战局辅助工具**，专注于为空战历史（Air RB）玩家提供实时的**友军存活数量统计**。

该工具不依赖任何注入手段，完全合规地通过游戏官方提供的本地 Web 接口（`127.0.0.1:8111`）获取数据，并以**透明悬浮窗**的形式显示在游戏画面之上。它是为了替代 WTRTI 无法直接读取地图对象数量而开发的轻量级解决方案。

---

### 🛠️ 项目功能列表

#### 1. 核心功能 (Core Features)
*   **实时友军统计**：通过轮询游戏本地 API，实时计算当前地图上存活的友军飞机数量（包括蓝色队友和绿色小队成员）。
*   **自动排除干扰**：算法自动过滤掉玩家自己、地面单位（AI防空炮、车辆）以及非活跃的飞机对象，确保数据准确反映“有效空战力量”。
*   **智能状态显示**：当游戏未运行或未进入战局时，显示 "?" ，进入战局后自动显示数字。 TODO:存疑

#### 2. 视觉与交互 (Visuals & UX)
*   **无边框透明悬浮窗**：采用 Tkinter 实现背景全透明（透视）效果，只显示数字和拖拽手柄，不遮挡游戏视野。
*   **拖拽式布局**：
    *   左侧设计了一个**隐形/空心圆形手柄**（视觉上是透明的，但可以点击）。
    *   按住圆圈或数字即可随意拖动悬浮窗位置。
*   **位置记忆**：程序会自动记录用户上次拖拽停留的坐标，下次启动自动复位（配置文件存储在 `%APPDATA%`）。
*   **置顶显示**：始终保持在游戏窗口最上层（支持“全屏窗口”或“窗口化”模式）。

#### 3. 个性化设置 (Customization)
提供了完整的图形化设置面板（右键 -> 设置），支持即时预览：
*   **自定义文本前缀**：可自由修改显示的文字（如 `Friends: ` 或 `队友: `），也可以留空只显示数字。
*   **字体大小调节**：支持 10px - 60px 的无级调节。
*   **颜色自定义**：
    *   支持 Hex 十六进制颜色代码输入（如 `#FF0000`）。
    *   内置调色盘拾色器。
    *   设置面板带有颜色实时预览块。
*   **刷新频率调节**：可调整数据读取间隔（0.1秒 - 2.0秒），平衡实时性与性能。
*   **一键恢复默认**：设置乱了可以一键重置（保留窗口位置，仅重置样式参数），且不会强制关闭设置窗口。

#### 4. 系统集成 (System Integration)
*   **系统托盘图标**：程序运行时在任务栏右下角显示绿色圆点图标。
*   **双重控制菜单**：
    *   **悬浮窗右键菜单**：支持快速进入设置、隐藏窗口、退出程序。
    *   **托盘右键菜单**：支持显示/隐藏、重置位置（防丢失）、退出程序。
*   **规范化存储**：配置文件严格遵循 Windows 规范，保存在 `%APPDATA%\WTFriendCounter\config.json`，避免权限问题。

#### 5. 安全性与性能 TODO:存疑
*   **无注入 (External)**：不读取游戏内存，不注入 DLL，仅进行 HTTP GET 请求，不会触发 Easy Anti-Cheat (EAC)。
*   **轻量化**：基于 Python 标准库 + Tkinter 开发，占用系统资源极低。 
---
TODO: 增加战雷不在运行、不在对局、不在空历对局的情况的处理  （可以从gamestats里判断），并在设置添加是否在非对局时不显示计数器的逻辑（默认为隐藏。这个隐藏逻辑应该和当前存在的手动的隐藏逻辑分开。）

TODO: 增加小队队友的独立逻辑。小队队友应该和普通队友的颜色不一样。采用N+n的显示逻辑。左边是非小队的队友数量 右边是小队队友数量。没有小队队友则不显示，有的话就是要减少到0.

TODO: 增加处理战雷自定义颜色的设置情况：先根据几个可能的战雷目录检索是否启用了自定义颜色（敌人 队友 小队 自己），并询问用户。 并在设置界面加一个自定义颜色填写区域（这个区域要独立于之前的界面，有独立的恢复默认的逻辑，并且能够留存之前保留的颜色记录，这些记录要有颜色示例，并可以对其进行增删改）

---
# 无法实现的梦
现在这个程序有一个缺陷：程序在开局可以读取到数量正确的全部我方友机，但是在比赛持续一段时间后场上会生成ai机型，8111提供的接口里，无法从场上的单位分辨一个飞机是真人还是ai，因此会导致统计到ai。
我现在有一个想法：开局两分钟以内是不会生成ai的，且能确保大家都加载进来。也许可以通过“http://localhost:8111/mission.json” 来读取到当前是否处于比赛的状态，然后利用”http://127.0.0.1:8111/hudmsg?lastEvt=0&lastDmg=0“读到的shot down记录来减少玩家。


*（因为shotdown记录里不包含阵营只是而放弃。）*

mission.json
```
{
   "objectives" : [
      {
         "primary" : true,
         "status" : "in_progress",
         "text" : "Assist the ground forces"
      },
      {
         "primary" : true,
         "status" : "undefined",
         "text" : "Assist the ground forces"
      }
   ],
   "status" : "running"
}
```
hudmsg?lastEvt=0&lastDmg=0
```
{"events":[

],
"damage":[
{ "id": 1, "msg": "^LUNAS^ Passpirin (Su-30SM) destroyed weapons/su_r_77_1_default/short", "sender": "", "enemy": false, "mode": "", "time": 138 },
{ "id": 2, "msg": "=1917= 物质与意识何者为本源 (Su-30SM) critically damaged [RPros] rakaMPro (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 146 },
{ "id": 3, "msg": "=1917= 物质与意识何者为本源 (Su-30SM) severely damaged [RPros] rakaMPro (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 146 },
{ "id": 4, "msg": "=1917= 物质与意识何者为本源 (Su-30SM) shot down [RPros] rakaMPro (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 146 },
{ "id": 5, "msg": "=1917= 物质与意识何者为本源 (Su-30SM) has delivered the first strike!", "sender": "", "enemy": false, "mode": "", "time": 147 },
{ "id": 6, "msg": "=SEALS= Pancakeboy (F/A-18E) critically damaged =HMSHD= 飞天虚化犬 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 158 },
{ "id": 7, "msg": "=SEALS= Pancakeboy (F/A-18E) severely damaged =HMSHD= 飞天虚化犬 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 158 },
{ "id": 8, "msg": "=SEALS= Pancakeboy (F/A-18E) set afire =HMSHD= 飞天虚化犬 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 158 },
{ "id": 9, "msg": "=SEALS= Pancakeboy (F/A-18E) shot down =HMSHD= 飞天虚化犬 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 158 },
{ "id": 10, "msg": "[RPros] rakaMPro (Su-30SM2) critically damaged =1917= 物质与意识何者为本源 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 159 },
{ "id": 11, "msg": "=HMSHD= 飞天虚化犬 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 162 },
{ "id": 12, "msg": "飞天虚化犬td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 162 },
{ "id": 13, "msg": "[RPros] rakaMPro (Su-30SM2) shot down =1917= 物质与意识何者为本源 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 163 },
{ "id": 14, "msg": "[RPros] rakaMPro (Su-30SM2) has achieved \"Eye for Eye\"", "sender": "", "enemy": false, "mode": "", "time": 163 },
{ "id": 15, "msg": "[RPros] rakaMPro has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 170 },
{ "id": 16, "msg": "rakaMProtd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 170 },
{ "id": 17, "msg": "=1917= 物质与意识何者为本源 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 174 },
{ "id": 18, "msg": "物质与意识何者为本源td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 174 },
{ "id": 19, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) severely damaged =NA1VE= Samuil2186 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 200 },
{ "id": 20, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) critically damaged =NA1VE= Samuil2186 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 200 },
{ "id": 21, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) set afire =NA1VE= Samuil2186 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 200 },
{ "id": 22, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) shot down =NA1VE= Samuil2186 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 202 },
{ "id": 23, "msg": "=NA1VE= Samuil2186 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 205 },
{ "id": 24, "msg": "Samuil2186td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 205 },
{ "id": 25, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) critically damaged -TABAK- StarboardSards (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 212 },
{ "id": 26, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) set afire -TABAK- StarboardSards (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 212 },
{ "id": 27, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) shot down -TABAK- StarboardSards (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 212 },
{ "id": 28, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) has achieved \"Double strike!\"", "sender": "", "enemy": false, "mode": "", "time": 213 },
{ "id": 29, "msg": "梅川库茶子嘎嘎 (Su-30SM) critically damaged _porthos (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 217 },
{ "id": 30, "msg": "梅川库茶子嘎嘎 (Su-30SM) severely damaged _porthos (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 217 },
{ "id": 31, "msg": "梅川库茶子嘎嘎 (Su-30SM) set afire _porthos (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 217 },
{ "id": 32, "msg": "梅川库茶子嘎嘎 (Su-30SM) critically damaged -Chftn- ⋇DavidBMX177 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 221 },
{ "id": 33, "msg": "-TABAK- StarboardSards has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 224 },
{ "id": 34, "msg": "StarboardSardstd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 224 },
{ "id": 35, "msg": "梅川库茶子嘎嘎 (Su-30SM) shot down _porthos (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 229 },
{ "id": 36, "msg": "_porthos has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 231 },
{ "id": 37, "msg": "_porthostd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 231 },
{ "id": 38, "msg": "=CLAS= GUUED (Su-30SM) critically damaged [AIM54] 中國臺灣省婦女聯合會主任 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 233 },
{ "id": 39, "msg": "=CLAS= GUUED (Su-30SM) shot down [AIM54] 中國臺灣省婦女聯合會主任 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 234 },
{ "id": 40, "msg": "[FEARG] ⋇xStarDestroyerx4 (Su-30SM2) has crashed.", "sender": "", "enemy": false, "mode": "", "time": 235 },
{ "id": 41, "msg": "梅川库茶子嘎嘎 (Su-30SM) shot down -Chftn- ⋇DavidBMX177 (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 237 },
{ "id": 42, "msg": "梅川库茶子嘎嘎 (Su-30SM) has achieved \"Double strike!\"", "sender": "", "enemy": false, "mode": "", "time": 238 },
{ "id": 43, "msg": "-LADF- ⋇VaporousStorm6 (F/A-18E) critically damaged =CPVAN= 神圣的BWD亲妈之力连接着我们 (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 239 },
{ "id": 44, "msg": "-LADF- ⋇VaporousStorm6 (F/A-18E) shot down =CPVAN= 神圣的BWD亲妈之力连接着我们 (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 239 },
{ "id": 45, "msg": "-GSV- cl0udk1d75 (◄EF-2000) shot down =RCT9= ⋇HALFONSO_pro (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 241 },
{ "id": 46, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) critically damaged [THEBC] xGOxAWAY (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 242 },
{ "id": 47, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) severely damaged [THEBC] xGOxAWAY (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 242 },
{ "id": 48, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) set afire [THEBC] xGOxAWAY (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 242 },
{ "id": 49, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) shot down [THEBC] xGOxAWAY (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 242 },
{ "id": 50, "msg": "-TSTF- FN2625 (Su-30SM) destroyed Howitzer", "sender": "", "enemy": false, "mode": "", "time": 244 },
{ "id": 51, "msg": "[FEARG] ⋇xStarDestroyerx4 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 244 },
{ "id": 52, "msg": "⋇xStarDestroyerx4td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 244 },
{ "id": 53, "msg": "-TSTF- FN2625 (Su-30SM) destroyed Howitzer", "sender": "", "enemy": false, "mode": "", "time": 245 },
{ "id": 54, "msg": "[AIM54] 中國臺灣省婦女聯合會主任 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 245 },
{ "id": 55, "msg": "中國臺灣省婦女聯合會主任td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 245 },
{ "id": 56, "msg": ".Ooara. HansUndPotato (Su-30SM) critically damaged =CLAS= GUUED (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 250 },
{ "id": 57, "msg": ".Ooara. HansUndPotato (Su-30SM) shot down =CLAS= GUUED (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 250 },
{ "id": 58, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) critically damaged .Ooara. HansUndPotato (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 59, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) severely damaged .Ooara. HansUndPotato (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 60, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) shot down .Ooara. HansUndPotato (Su-30SM)", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 61, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) has achieved \"Fighter Rescuer\"", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 62, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) has achieved \"Avenger\"", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 63, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) has achieved \"Shadow strike streak: x3!\"", "sender": "", "enemy": false, "mode": "", "time": 252 },
{ "id": 64, "msg": "[THEBC] xGOxAWAY has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 253 },
{ "id": 65, "msg": "xGOxAWAYtd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 253 },
{ "id": 66, "msg": "-BOOGS- XpertNoob69 (Rafale C) critically damaged -LADF- ⋇VaporousStorm6 (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 254 },
{ "id": 67, "msg": "=CPVAN= 神圣的BWD亲妈之力连接着我们 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 256 },
{ "id": 68, "msg": "神圣的BWD亲妈之力连接着我们td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 256 },
{ "id": 69, "msg": "⋇AntoniR8 (◄EF-2000) shot down -CNXY2- ⋇melodic-caveat99 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 257 },
{ "id": 70, "msg": "=RCT9= ⋇HALFONSO_pro has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 258 },
{ "id": 71, "msg": "⋇HALFONSO_protd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 258 },
{ "id": 72, "msg": "-Chftn- ⋇DavidBMX177 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 259 },
{ "id": 73, "msg": "⋇DavidBMX177td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 259 },
{ "id": 74, "msg": "=CLAS= GUUED has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 261 },
{ "id": 75, "msg": "GUUEDtd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 261 },
{ "id": 76, "msg": ".Ooara. HansUndPotato has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 267 },
{ "id": 77, "msg": "HansUndPotatotd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 267 },
{ "id": 78, "msg": "-CNXY2- ⋇melodic-caveat99 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 269 },
{ "id": 79, "msg": "⋇melodic-caveat99td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 269 },
{ "id": 80, "msg": "┾MiRav┿ ⋇spookyLuvKFC (Su-30SM2) critically damaged ⋇AntoniR8 (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 270 },
{ "id": 81, "msg": "┾MiRav┿ ⋇spookyLuvKFC (Su-30SM2) shot down ⋇AntoniR8 (◄EF-2000)", "sender": "", "enemy": false, "mode": "", "time": 270 },
{ "id": 82, "msg": "┾MiRav┿ ⋇Rocketdog5294 (JAS39C) has achieved \"Supporting Fire x1\"", "sender": "", "enemy": false, "mode": "", "time": 270 },
{ "id": 83, "msg": "-TSTF- FN2625 (Su-30SM) has crashed.", "sender": "", "enemy": false, "mode": "", "time": 283 },
{ "id": 84, "msg": "梅川库茶子嘎嘎 (Su-30SM) has crashed.", "sender": "", "enemy": false, "mode": "", "time": 284 },
{ "id": 85, "msg": "⋇AntoniR8 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 284 },
{ "id": 86, "msg": "⋇AntoniR8td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 284 },
{ "id": 87, "msg": "=CPVAN= 神圣的BWD亲妈之力连接着我们 (◄EF-2000) severely damaged A-4B", "sender": "", "enemy": false, "mode": "", "time": 287 },
{ "id": 88, "msg": "=CPVAN= 神圣的BWD亲妈之力连接着我们 (◄EF-2000) critically damaged A-4B", "sender": "", "enemy": false, "mode": "", "time": 287 },
{ "id": 89, "msg": "=CPVAN= 神圣的BWD亲妈之力连接着我们 (◄EF-2000) set afire A-4B", "sender": "", "enemy": false, "mode": "", "time": 287 },
{ "id": 90, "msg": "-3TC- ThatKidTorres (▄Su-30MK) critically damaged -LADF- ⋇VaporousStorm6 (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 290 },
{ "id": 91, "msg": "-3TC- ThatKidTorres (▄Su-30MK) shot down -LADF- ⋇VaporousStorm6 (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 290 },
{ "id": 92, "msg": "-BOOGS- XpertNoob69 (Rafale C) has achieved \"Supporting Fire x1\"", "sender": "", "enemy": false, "mode": "", "time": 291 },
{ "id": 93, "msg": "-3TC- ThatKidTorres (▄Su-30MK) has achieved \"Rank does not matter\"", "sender": "", "enemy": false, "mode": "", "time": 291 },
{ "id": 94, "msg": "-TSTF- FN2625 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 291 },
{ "id": 95, "msg": "FN2625td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 291 },
{ "id": 96, "msg": "-TSA- STRIDER 1 (Rafale C) critically damaged .Lyco. 待会見する才怪 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 293 },
{ "id": 97, "msg": "-LADF- ⋇VaporousStorm6 (F/A-18E) critically damaged -BOOGS- XpertNoob69 (Rafale C)", "sender": "", "enemy": false, "mode": "", "time": 297 },
{ "id": 98, "msg": "^LUNAS^ Passpirin (Su-30SM) critically damaged =SEALS= Pancakeboy (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 299 },
{ "id": 99, "msg": "Centaurea37 (Su-30SM) critically damaged =SEALS= Pancakeboy (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 304 },
{ "id": 100, "msg": "Centaurea37 (Su-30SM) set afire =SEALS= Pancakeboy (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 304 },
{ "id": 101, "msg": "Centaurea37 (Su-30SM) severely damaged =SEALS= Pancakeboy (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 304 },
{ "id": 102, "msg": "Centaurea37 (Su-30SM) shot down =SEALS= Pancakeboy (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 311 },
{ "id": 103, "msg": "=SEALS= Pancakeboy has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 317 },
{ "id": 104, "msg": "Pancakeboytd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 317 },
{ "id": 105, "msg": "-LADF- ⋇VaporousStorm6 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 321 },
{ "id": 106, "msg": "⋇VaporousStorm6td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 321 },
{ "id": 107, "msg": "-TSA- STRIDER 1 (Rafale C) severely damaged .Lyco. 待会見する才怪 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 331 },
{ "id": 108, "msg": "-TSA- STRIDER 1 (Rafale C) shot down .Lyco. 待会見する才怪 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 334 },
{ "id": 109, "msg": "梅川库茶子嘎嘎 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 335 },
{ "id": 110, "msg": "梅川库茶子嘎嘎td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 335 },
{ "id": 111, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) critically damaged -BOOGS- XpertNoob69 (Rafale C)", "sender": "", "enemy": false, "mode": "", "time": 339 },
{ "id": 112, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) set afire -BOOGS- XpertNoob69 (Rafale C)", "sender": "", "enemy": false, "mode": "", "time": 339 },
{ "id": 113, "msg": ".Lyco. 待会見する才怪 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 346 },
{ "id": 114, "msg": "待会見する才怪td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 346 },
{ "id": 115, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) severely damaged -BOOGS- XpertNoob69 (Rafale C)", "sender": "", "enemy": false, "mode": "", "time": 351 },
{ "id": 116, "msg": "-BOOGS- XpertNoob69 (Rafale C) destroyed weapons/su_r_27et/short", "sender": "", "enemy": false, "mode": "", "time": 363 },
{ "id": 117, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) critically damaged ┾MiRav┿ ⋇spookyLuvKFC (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 365 },
{ "id": 118, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) shot down ┾MiRav┿ ⋇spookyLuvKFC (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 365 },
{ "id": 119, "msg": "Centaurea37 (Su-30SM) critically damaged ^V4DER^ Kale_MSIA (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 365 },
{ "id": 120, "msg": "Centaurea37 (Su-30SM) severely damaged ^V4DER^ Kale_MSIA (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 365 },
{ "id": 121, "msg": "Centaurea37 (Su-30SM) set afire ^V4DER^ Kale_MSIA (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 365 },
{ "id": 122, "msg": "Centaurea37 (Su-30SM) shot down ^V4DER^ Kale_MSIA (F/A-18E)", "sender": "", "enemy": false, "mode": "", "time": 368 },
{ "id": 123, "msg": "-BOOGS- XpertNoob69 (Rafale C) severely damaged =KAIST= 수도서울 절대사수 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 373 },
{ "id": 124, "msg": "-BOOGS- XpertNoob69 (Rafale C) critically damaged =KAIST= 수도서울 절대사수 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 373 },
{ "id": 125, "msg": "┾MiRav┿ ⋇spookyLuvKFC has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 376 },
{ "id": 126, "msg": "⋇spookyLuvKFCtd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 376 },
{ "id": 127, "msg": "^V4DER^ Kale_MSIA has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 389 },
{ "id": 128, "msg": "Kale_MSIAtd! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 389 },
{ "id": 129, "msg": "^LUNAS^ Passpirin (Su-30SM) shot down =KAIST= 수도서울 절대사수 (Su-30SM2)", "sender": "", "enemy": false, "mode": "", "time": 396 },
{ "id": 130, "msg": "-BOOGS- XpertNoob69 (Rafale C) has achieved \"Avenger\"", "sender": "", "enemy": false, "mode": "", "time": 397 },
{ "id": 131, "msg": "⋇ LUNAS^ Passpirin (Su-30SM) has achieved \"Fighter Rescuer\"", "sender": "", "enemy": false, "mode": "", "time": 397 },
{ "id": 132, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) shot down -BOOGS- XpertNoob69 (Rafale C)", "sender": "", "enemy": false, "mode": "", "time": 414 },
{ "id": 133, "msg": "-GSV- cl0udk1d75 (◄EF-2000) has achieved \"The Best Squad\"", "sender": "", "enemy": false, "mode": "", "time": 415 },
{ "id": 134, "msg": "-BOOGS- XpertNoob69 (Rafale C) has achieved \"The Best Squad\"", "sender": "", "enemy": false, "mode": "", "time": 415 },
{ "id": 135, "msg": "-3TC- ThatKidTorres (▄Su-30MK) has achieved \"The Best Squad\"", "sender": "", "enemy": false, "mode": "", "time": 415 },
{ "id": 136, "msg": "-3TC- ThatKidTorres (▄Su-30MK) has achieved \"Balancer\"", "sender": "", "enemy": false, "mode": "", "time": 415 },
{ "id": 137, "msg": "-TSTF- FN2625 (Su-30SM) has achieved \"Antimech\"", "sender": "", "enemy": false, "mode": "", "time": 416 },
{ "id": 138, "msg": "[THEBC] xGOxAWAY (Su-30SM) has achieved \"The Best Squad\"", "sender": "", "enemy": false, "mode": "", "time": 416 },
{ "id": 139, "msg": "-TSA- STRIDER 1 (Rafale C) has achieved \"On Hand\"", "sender": "", "enemy": false, "mode": "", "time": 416 },
{ "id": 140, "msg": "=KAIST= 수도서울 절대사수 (Su-30SM2) has delivered the final blow!", "sender": "", "enemy": false, "mode": "", "time": 416 },
{ "id": 141, "msg": "-CNXY2- ⋇melodic-caveat99 (Su-30SM2) has achieved \"Terror of the Sky\"", "sender": "", "enemy": false, "mode": "", "time": 416 },
{ "id": 142, "msg": "=KAIST= 수도서울 절대사수 has disconnected from the game.", "sender": "", "enemy": false, "mode": "", "time": 420 },
{ "id": 143, "msg": "수도서울 절대사수td! kd?NET_PLAYER_DISCONNECT_FROM_GAME", "sender": "", "enemy": false, "mode": "", "time": 420 }
]}
```