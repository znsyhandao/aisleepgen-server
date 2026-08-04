import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter
import sounddevice as sd
from dataclasses import dataclass
from enum import Enum

class AudioType(Enum):
    BINAURAL = 1
    NATURE = 2
    PINK_NOISE = 3 
    GUIDED = 4
    NEW_TYPE = 5  # 新增自定义类型


@dataclass
class AudioEffect:
    volume: float = 0.7
    pan: float = 0.0  # -1(left) to 1(right)
    fade_in: float = 2.0  # seconds

class AudioPlayer:
    def __init__(self, sample_rate=44100):
        
        self.sample_rate = sample_rate
        self.active_streams = {}
        
        # 专业音频库
        self.library = {
            AudioType.BINAURAL: {
                'alpha': self._gen_binaural(10, 14),
                'theta': self._gen_binaural(4, 7)
            },
            AudioType.NATURE: {
                'forest': 'assets/nature/forest.wav',
                'rain': 'assets/nature/rain.wav'
            },
            # ... 原有音频库 ...
            AudioType.NEW_TYPE: {
                'custom1': self._gen_custom_audio('param1'),  # 动态生成的音频
                'custom2': 'assets/custom/audio2.wav'  # 预录制的音频文件
            }
        }

    def _gen_binaural(self, base_freq, delta_freq):
        """生成双耳节拍音频"""
        t = np.linspace(0, 10, 10 * self.sample_rate, False)
        left = np.sin(2 * np.pi * base_freq * t)
        right = np.sin(2 * np.pi * (base_freq + delta_freq) * t)
        return np.column_stack((left, right))

    def _gen_custom_audio(self, params):
        """生成自定义音频"""
        t = np.linspace(0, 10, 10 * self.sample_rate, False)
        # 自定义音频生成逻辑
        left_channel = np.sin(2 * np.pi * params * t) 
        right_channel = np.cos(2 * np.pi * params * t)
        return np.column_stack((left_channel, right_channel))
    async def play(self, audio_type: AudioType, name: str, effect: AudioEffect):
        """播放专业音频"""
        if audio_type not in self.library or name not in self.library[audio_type]:
            raise ValueError("不支持的音频类型或名称")

        audio = self._load_audio(audio_type, name)
        audio = self._apply_effects(audio, effect)
        
        stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=2,
            callback=lambda *args: self._audio_callback(audio, *args)
        )
        self.active_streams[(audio_type, name)] = stream
        stream.start()

    def _load_audio(self, audio_type: AudioType, name: str):
        """加载音频数据"""
        if audio_type == AudioType.NATURE:
            return wavfile.read(self.library[audio_type][name])[1]
        return self.library[audio_type][name]

    def _apply_effects(self, audio, effect):
        """应用音频效果"""
        # 淡入处理
        if effect.fade_in > 0:
            fade_samples = int(effect.fade_in * self.sample_rate)
            fade_curve = np.linspace(0, 1, fade_samples)
            audio[:fade_samples] *= fade_curve[:, np.newaxis]
        
        # 声道平衡
        if effect.pan != 0:
            audio[:, 0] *= (1 - effect.pan) if effect.pan > 0 else 1
            audio[:, 1] *= (1 + effect.pan) if effect.pan < 0 else 1
        
        return audio * effect.volume

    def stop(self, audio_type: AudioType, name: str):
        """停止特定音频"""
        if (audio_type, name) in self.active_streams:
            self.active_streams[(audio_type, name)].stop()
            del self.active_streams[(audio_type, name)]

    def stop_all(self):
        """停止所有音频"""
        for stream in self.active_streams.values():
            stream.stop()
        self.active_streams.clear()

    async def apply_intervention(self, intervention: Dict):
        if intervention['type'] == 'audio':
            from audio.player import AudioPlayer, AudioEffect
            player = AudioPlayer()
            effect = AudioEffect(
                volume=intervention.get('volume', 0.7),
                pan=intervention.get('pan', 0),
                fade_in=intervention.get('fade_in', 2)
            )
            await player.play(
                audio_type=AudioType[intervention['subtype'].upper()],
                name=intervention['track'],
                effect=effect
            )


# 使用示例
if __name__ == "__main__":
    player = AudioPlayer()
    effect = AudioEffect(volume=0.8, pan=-0.3, fade_in=3.0)
    
    # 播放α波双耳节拍
    asyncio.run(player.play(
        audio_type=AudioType.BINAURAL,
        name='alpha',
        effect=effect
    ))
