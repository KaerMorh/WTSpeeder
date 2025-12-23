import requests

def get_telemetry():
    """获取所有必要的遥测数据: {status, army, type, ias, mach, airbrake, ...}"""
    data = {
        'running': False,
        'army': '',
        'type': '',
        'ias_kmh': None,
        'tas_kmh': None,
        'altitude': None,
        'mach': None,
        'airbrake': None,
        'throttle_in': None,  # 输入
        'throttle_out': None  # 输出
    }
    
    try:
        # 1. Check Mission Status
        r_mission = requests.get('http://127.0.0.1:8111/mission.json', timeout=0.05)
        if r_mission.ok:
            mission = r_mission.json()
            data['running'] = (mission.get('status') == 'running')
        
        if data['running']:
            # 2. Check Indicators
            r_ind = requests.get('http://127.0.0.1:8111/indicators', timeout=0.05)
            if r_ind.ok:
                ind = r_ind.json()
                if ind.get('valid'):
                    data['army'] = ind.get('army', '')
                    data['type'] = ind.get('type', '')
                    # throttle input (0.0 - 1.0 or >1.0 for WEP)
                    # Note: API might return 'throttle' or similar
                    t_val = ind.get('throttle')
                    if t_val is not None:
                        data['throttle_in'] = float(t_val)
            
            # 3. Check State (IAS, Mach, Airbrake)
            r_state = requests.get('http://127.0.0.1:8111/state', timeout=0.05)
            if r_state.ok:
                state = r_state.json()
                if state.get('valid'):
                    val = state.get('IAS, km/h')
                    if val is not None:
                        data['ias_kmh'] = float(val)
                    
                    tas_val = state.get('TAS, km/h')
                    if tas_val is not None:
                        data['tas_kmh'] = float(tas_val)

                    h_val = state.get('H, m')
                    if h_val is not None:
                        data['altitude'] = float(h_val)
                        
                    m_val = state.get('M')
                    if m_val is not None:
                        data['mach'] = float(m_val)
                        
                    ab_val = state.get('airbrake, %')
                    if ab_val is not None:
                        data['airbrake'] = int(ab_val)

                    # Engine 1 output as reference
                    t_out = state.get('throttle 1, %')
                    if t_out is not None:
                        data['throttle_out'] = int(t_out)
    except:
        pass
        
    return data

