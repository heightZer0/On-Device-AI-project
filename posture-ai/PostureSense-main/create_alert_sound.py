import numpy as np
import pygame
import time
from scipy.io.wavfile import write

def generate_alert_sound(filename="alert.wav", duration=1.0, frequency=440):
    """Generate a simple alert sound and save it as a WAV file"""
    # Set parameters
    sample_rate = 44100  # CD quality audio
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # Generate a simple sine wave tone
    tone = np.sin(frequency * 2 * np.pi * t)
    
    # Add a second tone for more attention-grabbing sound
    tone2 = np.sin((frequency * 1.5) * 2 * np.pi * t)
    
    # Combine tones
    combined = tone + tone2
    
    # Normalize to prevent clipping
    combined = combined / np.max(np.abs(combined)) * 0.9
    
    # Convert to 16-bit PCM
    audio = (combined * 32767).astype(np.int16)
    
    # Save as WAV file
    write(filename, sample_rate, audio)
    print(f"Alert sound saved as {filename}")
    
    return filename

def play_sound(filename="alert.wav"):
    """Play the generated sound"""
    pygame.mixer.init()
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
    pygame.mixer.quit()

if __name__ == "__main__":
    try:
        from scipy.io.wavfile import write
    except ImportError:
        print("SciPy not found. Installing required package...")
        import subprocess
        subprocess.check_call(["pip", "install", "scipy"])
        from scipy.io.wavfile import write
    
    print("Generating alert sound...")
    filename = generate_alert_sound()
    
    print("Playing alert sound for preview...")
    play_sound(filename)
    
    print("\nAlert sound created successfully!")
    print("You can now run the posture monitor with sound alerts.")