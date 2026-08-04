def __init__(self, model_path: str = "default"):
        """初始化基于神经可塑性的冥想引导系统
        
        参数:
            model_path: DeepSeek模型路径，默认为预训练模型
        """


        # 初始化基础参数
        self.session_history = []
        self.base_respiration_rate = 12
        self.current_audio = None  # 跟踪当前播放的音频


        if not torch.cuda.is_available():
            print("Optimizing for Intel CPU with MKL acceleration")
            torch.backends.mkldnn.enabled = True
            torch.set_flush_denormal(True)

        # 初始化生物反馈参数
        self.biofeedback_params = {
            'heart_rate': 70,  # 初始心率
            'breath_rate': 12,  # 初始呼吸频率  
        }
        self.neurofeedback_params = {
            'eeg_alpha': 0,
            'eeg_theta': 0,
            'update_interval': 5  # 秒
        }
        
        
        # 初始化呼吸模式（精简版）
        self.breath_patterns = {
            # 基础呼吸模式
            '4-7-8': (4, 7, 8),  # Andrew Weil博士推广的放松呼吸法
            'box': (4, 4, 4, 4),  # 军方常用的方形呼吸法
            'equal': (5, 5),      # 平衡呼吸法
            'coh': self._generate_coherent_pattern,  # 生理协调呼吸模式
            
            # 高级呼吸模式
            'resonance': {  # 心脏共振呼吸法
                'phases': [(6, BreathPhase.INHALE), (6, BreathPhase.EXHALE)],
                'optimal_hrv': 0.65
            },
            'physiological_sigh': {  # 生理叹息法
                'phases': [(2, BreathPhase.INHALE), (1, BreathPhase.INHALE), 
                          (10, BreathPhase.EXHALE)]
            },
            'cadence_478': {  # 节奏型4-7-8
                'phases': [(4, BreathPhase.INHALE), (7, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (2, BreathPhase.REST)]
            },
            'coherent_heart': {  # 心脏协调呼吸
                'phases': [(5, BreathPhase.INHALE), (5, BreathPhase.EXHALE)],
                'entrainment': True
            },
            
            # 睡眠相关模式
            'sleep_induce': {  # 助眠呼吸法
                'phases': [(4, BreathPhase.INHALE), (7, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (2, BreathPhase.REST)]
            },
            'deep_sleep': {  # 深度睡眠呼吸法
                'phases': [(6, BreathPhase.INHALE), (0, BreathPhase.HOLD)],
                'entrainment': False
            },
            
            # 通用冥想模式（合并了多个相同定义）
            'meditation': {  # 冥想呼吸（合并了breathing_techniques/stress_relief/anxiety_relief）
                'phases': [(4, BreathPhase.INHALE), (4, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (4, BreathPhase.REST)],
                'tags': ['meditation', 'stress_relief', 'anxiety_relief']
            }
        }

      
        # 添加睡眠管理参数
        self.sleep_params = {
            'optimal_sleep_duration': 7.5,  # 小时
            'sleep_stage_targets': {
                'N3': 0.2,  # 深度睡眠占比目标
                'REM': 0.25  # REM睡眠占比目标
            }
        }

        # 添加音频配置
        self.audio_config = {
            'background': 'assets/meditation_music.mp3',
            'voice': 'assets/voice_guidance.mp3',
            'inhale': 'assets/breath_in.wav',
            'exhale': 'assets/breath_out.wav',
            'bell': 'assets/bell.mp3'

        }

        # 初始化GuidanceGenerator
        from .deepseek_model import GuidanceGenerator
        self.guidance_generator = GuidanceGenerator()

        # 添加DeepSeek集成
        try:
            self.deepseek = DeepSeekIntegration()
        except Exception as e:
            print(f"DeepSeek-V3加载警告: {str(e)}")
            self.deepseek = None

        try:
            # 加载量子化优化的DeepSeek模型
            self.model = DeepSeekMeditationModel.load(
                model_path,
                quantized=True,
                quant_config={
                    'activation': 'per_tensor',
                    'weight': 'per_channel',
                    'quant_dtype': 'int8',
                    'calibration': 'min_max'
                },
                neuroplasticity_mode=True,
                pruning_ratio=0.4
            )
            # 模型配置
            self.model.set_mixed_precision({
                'attention_layers': 'fp16',
                'output_layer': 'fp16'
            })
            self.model.adjust_parameters({
                'learning_rate': 0.001,
                'batch_size': 32,
                'optimizer': 'adam',
                'loss_function': 'mse'
            })
        except Exception as e:
            raise RuntimeError(f"模型加载失败: {str(e)}")