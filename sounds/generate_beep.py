import wave
import math
import struct
import os

def generate_beep(filename="sounds/beep.wav", frequency=1000, duration=0.15, volume=0.5):
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    amplitude = int(32767 * volume)
    
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit PCM)
        wav_file.setframerate(sample_rate)
        
        data = []
        for i in range(n_samples):
            # Generate a sine wave
            t = float(i) / sample_rate
            value = int(amplitude * math.sin(2 * math.pi * frequency * t))
            
            # Simple fade out to avoid clicks
            if i > n_samples - 500:
                fade = (n_samples - i) / 500.0
                value = int(value * fade)
                
            data.append(struct.pack('<h', value))
            
        wav_file.writeframes(b''.join(data))
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_beep()
