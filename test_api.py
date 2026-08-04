import tempfile
import os
import sys
import time
import requests
import json
import numpy as np
from pydantic import BaseModel, Field
from io import BytesIO
import pyedflib
from fastapi import FastAPI, UploadFile, File, HTTPException,Body
import logging
from scipy import signal  # 新增导入
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='server.log'
)

class Config:
    PORT = 8002
    TIMEOUT = 30
    MAX_FILE_SIZE = 1024 * 1024 * 100  # 100MB限制
    CHUNK_SIZE = 1024 * 1024  # 1MB分块

def check_server_logs(log_file="server.log", lines=100):
    try:
        if os.path.exists(log_file):
            print(f"\n=== 服务器日志最后{lines}行 ===")
            if os.name == 'nt':
                # 修复Windows命令
                logs = os.popen(f'powershell -command "Get-Content {log_file} -Tail {lines}"').read()
            else:
                logs = os.popen(f'tail -n {lines} {log_file}').read()
            print(logs)
        else:
            print(f"警告: 日志文件未找到 - {log_file}")
    except Exception as e:
        print(f"读取日志失败: {str(e)}")

def analyze_sleep_stages(eeg_signal, sample_rate=100):
    """分析睡眠分期
    参数:
        eeg_signal: EEG信号数据(numpy数组)
        sample_rate: 采样率(Hz)
    返回:
        list: 睡眠分期结果列表
    """
    try:
        from scipy import signal
        import numpy as np
        
        # 参数设置
        epoch_length = 30 * sample_rate  # 30秒一个epoch
        num_epochs = len(eeg_signal) // epoch_length
        
        if num_epochs == 0:
            return []
        
        stages = []
        
        for i in range(num_epochs):
            start = i * epoch_length
            end = start + epoch_length
            epoch = eeg_signal[start:end]
            
            # 计算特征
            mean_amp = np.mean(np.abs(epoch))
            std_amp = np.std(epoch)
            
            # 计算频带能量
            freqs, psd = signal.welch(epoch, fs=sample_rate)
            delta = np.sum(psd[(freqs >= 0.5) & (freqs <= 4)])
            theta = np.sum(psd[(freqs > 4) & (freqs <= 8)])
            alpha = np.sum(psd[(freqs > 8) & (freqs <= 12)])
            beta = np.sum(psd[(freqs > 12) & (freqs <= 30)])
            
            # 简单规则判断睡眠分期
            if alpha > theta and alpha > delta:
                stage = "W"  # 清醒
            elif theta > alpha and theta > delta:
                stage = "N1"  # N1期
            elif delta > theta and delta > alpha:
                if beta > 0.1 * delta:
                    stage = "N2"  # N2期
                else:
                    stage = "N3"  # N3期
            else:
                stage = "N1"  # 默认N1期
                
            stages.append(stage)
            
        return stages
        
    except Exception as e:
        logging.error(f"睡眠分期分析失败: {str(e)}")
        return []

def calculate_sleep_efficiency(sleep_stages):
    """计算睡眠效率
    参数:
        sleep_stages: 睡眠分期结果列表
    返回:
        float: 睡眠效率(0-1之间)
    """
    if not sleep_stages:
        return 0.0
        
    total_epochs = len(sleep_stages)
    sleep_epochs = sum(1 for stage in sleep_stages if stage != "W")
    
    return sleep_epochs / total_epochs


app = FastAPI()

edf_file_path = "data/edf/sc4002e0.rec"

def read_edf_file(filepath, debug=False):
    try:
        with pyedflib.EdfReader(filepath) as f:
            if debug:
                print(f"File contains {f.signals_in_file} signals")
                print(f"Signal labels: {f.getSignalLabels()}")
                print(f"Sample frequency: {f.getSampleFrequency(0)} Hz")
                print(f"Duration: {f.file_duration} seconds")
                
                signal_data = f.readSignal(0)
                print(f"First channel data samples: {len(signal_data)}")
                
            return f  # 返回reader对象以便后续操作
            
    except Exception as e:
        if debug:
            print(f"Error reading EDF file: {str(e)}")
        raise


def check_server_health():
    endpoints = [
        ("GET", "/docs", "文档端点"),
        ("GET", "/openapi.json", "OpenAPI配置"),
        ("POST", "/analyze", "分析端点"),
        ("POST", "/predict", "预测端点")
    ]
    
    server_ok = False
    
    for method, endpoint, desc in endpoints:
        try:
            if method == "GET":
                response = requests.get(f"http://localhost:{PORT}{endpoint}", timeout=2)
            else:
                response = requests.post(f"http://localhost:{PORT}{endpoint}", json={}, timeout=2)
                
            print(f"{desc}({method})状态: {response.status_code}")
            if response.status_code == 200:
                server_ok = True
                
        except requests.exceptions.RequestException as e:
            print(f"{desc}不可访问 - 错误: {str(e)}")
    
    if not server_ok:
        print("\n警告: 服务器端点检查失败")
        print("建议检查:")
        print("1. 服务器是否运行 (ps aux | grep uvicorn)")
        print("2. 端口是否被占用 (netstat -tulnp | grep 8000)")
        print("3. 防火墙设置 (sudo ufw status)")
        
    return server_ok

def check_server_config():
    try:
        config_response = requests.get(f"http://localhost:{PORT}/openapi.json", timeout=2)
        if config_response.status_code == 200:
            config = config_response.json()
            print("\n服务器配置信息:")
            print(f"API版本: {config.get('info', {}).get('version')}")
            print(f"可用端点: {', '.join(config.get('paths', {}).keys())}")
    except Exception as e:
        print(f"\n获取服务器配置失败: {str(e)}")

def validate_edf_file(filepath):
    with open(filepath, 'rb') as f:
        header = f.read(256)
        if len(header) < 256 or not header.startswith(b'0       '):
            raise ValueError("无效的EDF文件头")
        print("EDF文件头验证通过")

def send_edf_to_api(filepath, endpoint="/analyze"):
    try:
        validate_edf_file(filepath)
        
        with open(filepath, 'rb') as f:
            start_time = time.time()
            response = requests.post(
                f"http://localhost:{PORT}{endpoint}",
                files={'edf_file': (os.path.basename(filepath), f)},
                timeout=TIMEOUT
            )
            
            latency = (time.time() - start_time) * 1000
            file_size = os.path.getsize(filepath)
            
            print("\n=== API响应 ===")
            print(f"文件: {filepath} ({file_size/1024:.2f}KB)")
            print(f"耗时: {latency:.2f}ms")
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print("响应JSON:", json.dumps(result, indent=2))
                    return result
                except ValueError:
                    print("警告: 响应不是有效JSON")
                    print("原始响应:", response.text[:500])
            else:
                print("错误详情:", response.text)
                check_server_logs()
                
    except FileNotFoundError:
        print(f"错误: EDF文件不存在 - {filepath}")
    except Exception as e:
        print(f"请求失败: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return None





@app.post("/analyze")
async def analyze_edf(edf_file: UploadFile = File(...)):
    try:
        # 创建临时文件处理大文件
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.edf') as tmp:
            # 分块读取上传的文件内容
            while True:
                chunk = await edf_file.read(Config.CHUNK_SIZE)
                if not chunk:
                    break
                tmp.write(chunk)
            tmp_path = tmp.name


        

        try:
            # 验证EDF文件头
            with open(tmp_path, 'rb') as f:
                header = f.read(256)
                if len(header) < 256 or not header.startswith(b'0       '):
                    raise ValueError("无效的EDF文件头")
            # 统一使用临时文件处理
            with pyedflib.EdfReader(tmp_path) as f:
                signal_labels = f.getSignalLabels()
                sample_frequencies = [f.getSampleFrequency(i) for i in range(f.signals_in_file)]
                durations = [f.getNSamples()[i]/sample_frequencies[i] for i in range(f.signals_in_file)]
                
                sample_data = {}
                for i in range(min(5, f.signals_in_file)):
                    sample_data[signal_labels[i]] = f.readSignal(i)[:100].tolist()
                
                return {
                    "status": "success",
                    "channels": f.signals_in_file,
                    "duration": max(durations),
                    "sample_rates": sample_frequencies,
                    "labels": signal_labels,
                    "sample_data": sample_data,
                    "annotations": f.readAnnotations()
                }
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"EDF处理错误: {str(e)}")

        finally:
            try:
             os.unlink(tmp_path)
            except Exception as e:
             logging.error(f"删除临时文件失败: {str(e)}")           

   
            
        # 验证EDF文件头
        if len(contents) < 256 or not contents.startswith(b'0       '):
            raise ValueError("无效的EDF文件头")
            
        try:
            with pyedflib.EdfReader(tmp_path) as f:
                # 检查信号通道
                signal_labels = f.getSignalLabels()
                if not signal_labels:
                    raise ValueError("EDF文件中未检测到任何信号通道")
                
                # 睡眠分析(如果有EEG信号)
                sleep_stages = []
                if f.signals_in_file > 0:
                    try:
                        sleep_stages = analyze_sleep_stages(f.readSignal(0))
                    except Exception as e:
                        logging.warning(f"睡眠分析失败: {str(e)}")
                
                # 获取信号信息
                sample_frequencies = [f.getSampleFrequency(i) for i in range(f.signals_in_file)]
                durations = [f.getNSamples()[i]/sample_frequencies[i] for i in range(f.signals_in_file)]
                
                # 读取样本数据
                sample_data = {}
                for i in range(min(5, f.signals_in_file)):
                    try:
                        signal = f.readSignal(i)
                        sample_data[signal_labels[i]] = {
                            "values": signal[:100].tolist(),
                            "unit": f.getPhysicalDimension(i) or "unknown",
                            "stats": {
                                "min": float(np.min(signal)),
                                "max": float(np.max(signal)),
                                "mean": float(np.mean(signal))
                            }
                        }
                    except Exception as e:
                        logging.warning(f"读取通道 {signal_labels[i]} 失败: {str(e)}")
                        sample_data[signal_labels[i]] = {"error": str(e)}
                
                # 获取文件元数据
                file_info = {
                    "patient_id": f.getPatientCode() or "unknown",
                    "recording_id": f.getRecordingAdditional() or "unknown",
                    "start_time": f.getStartdatetime().isoformat(),
                    "duration": float(f.file_duration)
                }
                
                # 增强的睡眠阶段分析
                annotations = f.readAnnotations()
                sleep_stages = {
                    "timestamps": annotations[0].tolist(),
                    "durations": annotations[1].tolist(),
                    "descriptions": annotations[2],
                    "stage_stats": {}
                }
                # 计算各睡眠阶段统计信息
                stage_counts = {}
                for stage in set(annotations[2]):
                    stage_mask = [s == stage for s in annotations[2]]
                    stage_counts[stage] = sum(stage_mask)
                    sleep_stages["stage_stats"][stage] = {
                        "count": stage_counts[stage],
                        "total_duration": sum(
                            dur for dur, s in zip(annotations[1], annotations[2]) 
                            if s == stage
                        ),
                        "avg_duration": np.mean([
                            dur for dur, s in zip(annotations[1], annotations[2]) 
                            if s == stage
                        ])
                    }
                
                # 睡眠质量指标
                total_sleep_time = sum(annotations[1])
                sleep_efficiency = (
                    sum(d for d, s in zip(annotations[1], annotations[2]) 
                    if s not in ["Wake", "Movement time"])
                    / total_sleep_time * 100
                )
                
                # 读取EEG信号进行频段分析
                eeg_signals = {
                    label: f.readSignal(i) 
                    for i, label in enumerate(signal_labels) 
                    if 'EEG' in label
                }
                return {
                    "status": "success",
                    "sleep_metrics": {
                    "total_sleep_time": total_sleep_time,
                    "sleep_efficiency": round(sleep_efficiency, 2),
                    "stage_percentages": {
                        stage: round(count/sum(stage_counts.values())*100, 2)
                        for stage, count in stage_counts.items()
                    }
                },
                "sleep_stages": sleep_stages,
                "eeg_channels": list(eeg_signals.keys()),
                    "metadata": file_info,
                    "channels": f.signals_in_file,
                    "sample_rates": sample_frequencies,
                    "sample_data": sample_data,
                    "annotations": f.readAnnotations(),
                    "sleep_analysis": {
                        "stages": sleep_stages,
                        "efficiency": calculate_sleep_efficiency(sleep_stages) if sleep_stages else None
                    }
                }
                
        finally:
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logging.error(f"删除临时文件失败: {str(e)}")
                
    except pyedflib.EDFException as e:
        raise HTTPException(status_code=400, detail=f"EDF文件格式错误: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据验证失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")





# 添加predict端点
@app.post("/predict")
async def predict_features(
    request_data: dict = Body(..., example={
        "signal": [0.5, -0.2, 0.8],
        "signal_type": "eeg",
        "text": "测试信号样本"
    })
):
    try:
         
        # 统一信号数据获取方式
        signal = np.array(request_data.get("signal", []))
        sample_rate = request_data.get("sample_rate", 100)  # 添加默认采样率
        # 添加频段能量计算函数调用
        bands = {
            "delta": (0.5, 4),
            "theta": (4, 8), 
            "alpha": (8, 12),
            "beta": (12, 30)
        }

        if len(signal) == 0:
            raise ValueError("信号数据不能为空")
        
        # 添加信号长度验证
        if len(signal) < 100:
            raise ValueError("信号长度至少需要100个采样点")
            
        signal_type = request_data.get("signal_type", "eeg")
        
        # 基础特征计算
        features = {
            **{f"{band}_energy": calculate_band_energy(signal, sample_rate, low, high)
               for band, (low, high) in bands.items()},
            "mean": float(np.mean(signal)),
            "std": float(np.std(signal)),
            "max": float(np.max(signal)),
            "min": float(np.min(signal))
        }
        
        # 频域特征(对所有信号类型)
        fft = np.abs(np.fft.fft(signal))
        freqs = np.fft.fftfreq(len(signal))
        dominant_idx = np.argmax(fft[1:]) + 1  # 忽略直流分量
        features.update({
            "dominant_freq": abs(freqs[dominant_idx]),
            "spectrum_energy": float(np.sum(fft**2))
        })

        # 根据信号类型添加特定特征
        if signal_type == "eeg":
            features["is_eeg"] = True
        elif signal_type == "audio":
            features["is_audio"] = True
        # 添加频段能量分析
        if signal_type == "eeg":
            bands = {
                "delta": (0.5, 4),
                "theta": (4, 8),
                "alpha": (8, 12),
                "beta": (12, 30)
            }
            for band, (low, high) in bands.items():
                features[f"{band}_energy"] = calculate_band_energy(signal, sample_rate, low, high)
            
        return {
            "status": "success",
            "signal_type": signal_type,
            "features": features,
            "sample_count": len(signal)
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def calculate_band_energy(signal, sample_rate, low, high):
    """计算特定频段的能量"""
    freqs, psd = signal.welch(signal, fs=sample_rate)
    band_mask = (freqs >= low) & (freqs <= high)
    return float(np.sum(psd[band_mask]))

def test_feature_extraction():
    test_cases = [
        {"name": "零信号", "signal": np.zeros(3000), "expected": {"zero": True}, "signal_type": "eeg"},
        {"name": "直流信号", "signal": np.ones(3000) * 100, "expected": {"dc_offset": True}, "signal_type": "eeg"},
        {"name": "10Hz正弦波", "signal": np.sin(2 * np.pi * 10 * np.arange(3000)/100), "expected": {"dominant_freq": 10}, "signal_type": "audio"},
        {"name": "δ波(1Hz)", "signal": 50 * np.sin(2 * np.pi * 1 * np.arange(3000)/100), "expected": {"band": "delta"}, "signal_type": "eeg"},
        {"name": "θ波(4Hz)", "signal": 30 * np.sin(2 * np.pi * 4 * np.arange(3000)/100), "expected": {"band": "theta"}, "signal_type": "eeg"},
        {"name": "α波(8Hz)", "signal": 20 * np.sin(2 * np.pi * 8 * np.arange(3000)/100), "expected": {"band": "alpha"}, "signal_type": "eeg"},
        {"name": "β波(12Hz)", "signal": 10 * np.sin(2 * np.pi * 12 * np.arange(3000)/100), "expected": {"band": "beta"}, "signal_type": "eeg"}
    ]

    for case in test_cases:
        try:
            print(f"\n测试: {case['name']}")
            response = requests.post(
                f"http://localhost:{PORT}/api/predict",
                json={
                    "signal": case["signal"].tolist(),
                    "signal_type": case["type"],
                    "text": case["name"]
                },
                timeout=TIMEOUT
            )
            
            print(f"状态码: {response.status_code}")
            if response.status_code == 200:
                result = response.json()
                print("响应结果:", json.dumps(result, indent=2))
                if "features" in result:
                    print("提取特征:", result["features"].keys())
                else:
                    print("警告: 响应中缺少特征字段")
            else:
                print("错误详情:", response.text)
                
        except Exception as e:
            print(f"测试失败: {str(e)}")

# 在test_feature_extraction()函数后添加错误处理增强




# 修改predict端点的测试代码
# 统一测试函数
# ... 保留原有导入和配置 ...

def test_predict_features():
    """统一测试predict端点的功能"""
    # 添加服务器健康检查
    try:
        health_response = requests.get(f"http://localhost:{PORT}/", timeout=2)
        if health_response.status_code != 200:
            raise ConnectionError("服务器未启动或未响应")
    except Exception as e:
        print(f"❌ 服务器连接失败: {str(e)}")
        print("请先启动API服务器: python api_server.py")
        assert False, "服务器未启动"

    test_cases = [
        {
            "name": "零信号",
            "signal": np.zeros(1000).tolist(),
            "type": "eeg",
            "expected": {
                "mean": 0,
                "std": 0,
                "max": 0,
                "min": 0,
                "dominant_freq": 0,
                "is_eeg": True  # 添加缺失的预期字段    
            }
        },
        {
            "name": "10Hz正弦波",
            "signal": np.sin(2*np.pi*10*np.arange(1000)/1000).tolist(),
            "type": "audio",
            "expected": {
                "dominant_freq": 10,
                "spectrum_energy": 500  # 近似值
            }
        },
        {
            "name": "EEG混合波",
            "signal": (0.5*np.sin(2*np.pi*8*np.arange(1000)/1000) + 
                     0.3*np.sin(2*np.pi*12*np.arange(1000)/1000)).tolist(),
            "type": "eeg",
            "expected": {
                "is_eeg": True,
                "dominant_freq": 8,
                "spectrum_energy": 425  # 近似值
            }
        }
    ]
    
    passed = failed = 0
    for case in test_cases:
        print(f"\n=== 测试: {case['name']} ===")
        try:
            # 发送请求
            response = requests.post(
                f"http://localhost:{PORT}/predict",
                json={
                    "signal": case["signal"],
                    "signal_type": case["type"],
                    "text": case["name"]
                },
                timeout=TIMEOUT
            )
            
            # 验证响应
            if response.status_code != 200:
                print(f"❌ 请求失败 - 状态码: {response.status_code}")
                print(f"错误详情: {response.text[:200]}")
                failed += 1
                continue
                
            result = response.json()
            print(f"✅ 请求成功 - 样本数: {result.get('sample_count')}")
            
            # 验证特征
            features = result.get("features", {})
            case_passed = True
            for k, expected in case["expected"].items():
                actual = features.get(k)
                if actual is None:
                    print(f"❌ 缺少特征: {k}")
                    case_passed = False
                elif isinstance(expected, (int, float)):
                    if not np.isclose(actual, expected, rtol=0.1):
                        print(f"❌ {k} 不匹配: 期望 {expected}, 实际 {actual}")
                        case_passed = False
                else:
                    if actual != expected:
                        print(f"❌ {k} 不匹配: 期望 {expected}, 实际 {actual}")
                        case_passed = False
            
            if case_passed:
                print("✅ 所有特征验证通过")
                passed += 1
            else:
                failed += 1
                
            # 打印详细特征
            print("\n特征详情:")
            for k, v in features.items():
                print(f"- {k}: {v}")
                
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
            failed += 1
    
    print(f"\n=== 测试结果: 通过 {passed}, 失败 {failed} ===")
    assert passed == len(test_cases)



def test_commercial_features():
    print("\n=== 商业化功能测试 ===")
    
    # 测试睡眠分析
    try:
        with open(edf_file_path, 'rb') as f:
            response = requests.post(
                f"http://localhost:{PORT}/analyze",
                files={'edf_file': f},
                timeout=TIMEOUT
            )
            print("睡眠分析结果:", response.json().get('sleep_analysis', {}))
            
            if response.status_code != 200:
                print(f"睡眠分析失败: {response.status_code}")
            
                return False
        # 测试推荐系统
        try:
            rec_response = requests.post(
                f"http://localhost:{PORT}/recommend",
                json={
                    "user_id": "test_user",
                    "sleep_data": {"sleep_efficiency": 0.75},
                    "stress_level": 3
                },
                timeout=TIMEOUT
            )
            if rec_response.status_code != 200:
                print(f"推荐系统失败: {rec_response.status_code}")
                    # And replace return False with:
                assert False, "Test failed message"
                
            print("推荐结果:", json.dumps(rec_response.json(), indent=2))
            assert True
            
        except Exception as e:
            print(f"推荐系统测试异常: {str(e)}")
                # And replace return False with:
            assert False, "Test failed message"

    except Exception as e:
            print(f"商业化功能测试异常: {str(e)}")
                # And replace return False with:
            assert False, "Test failed message"

def test_api_performance():
    """测试API性能的完整函数"""
    try:
        # 1. 小文件测试
        test_small_file = "data/edf/SC4001EC-Hypnogram.edf"
        if os.path.exists(test_small_file):
            print("\n测试小文件上传...")
            if not send_edf_to_api(test_small_file):
                print("小文件测试失败，终止后续测试")
                assert False, "Test failed message"

        # 2. EDF文件验证
        print("\n验证EDF文件...")
        with open(edf_file_path, 'rb') as f:
            header = f.read(256)
            if len(header) < 256 or not header.startswith(b'0       '):
                raise ValueError("无效的EDF文件头")

        with pyedflib.EdfReader(edf_file_path) as f:
            if f.signals_in_file == 0:
                raise ValueError("EDF文件不包含任何信号通道")
            print(f"EDF验证通过 - 通道数: {f.signals_in_file}, 时长: {f.file_duration}s")

        # 3. 服务器健康检查
        if not check_server_health():
            check_server_config()
            assert False, "Test failed message"

        # 4. 分块上传测试
        print("\n测试文件分块上传...")
        with open(edf_file_path, 'rb') as f:
            test_chunk = f.read(1024)
            test_response = requests.post(
                f"http://localhost:{PORT}/analyze",
                files={'edf_file': ('test_chunk.edf', BytesIO(test_chunk))},
                timeout=TIMEOUT
            )
            if test_response.status_code != 200:
                print(f"分块上传失败: {test_response.text[:200]}")
                assert False, "Test failed message"

        # 5. 完整文件性能测试
        print("\n开始完整文件测试...")
        start_time = time.time()
        with open(edf_file_path, 'rb') as f:
            response = requests.post(
                f"http://localhost:{PORT}/analyze",
                files={'edf_file': (os.path.basename(edf_file_path), f)},
                timeout=TIMEOUT
            )
        
        print(f"\n请求耗时: {(time.time()-start_time):.2f}s")
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n服务器错误详情:")
            print(response.headers)
            print(response.text[:500])
            check_server_logs()
            print("\n调试建议:")
            print("- 检查服务器内存")
            print("- 验证EDF文件格式")
            print("- 尝试小文件测试")
            print("性能测试结果:", result)
            assert True, "Performance test passed"
        else:
            assert False, "Test failed message"
            
    

    except Exception as e:
        print(f"\n性能测试失败: {str(e)}")
        print("调试建议:")
        print("1. 检查服务器日志 (tail -f server.log)")
        print("2. 验证EDF文件完整性 (pyedflib.EdfReader)")
        print("3. 测试小文件 (1MB以下)")
        check_server_logs()
        assert False, "Test failed message"



class RecommendationRequest(BaseModel):
    user_id: str
    sleep_data: dict
    stress_level: int = Field(ge=1, le=5)
    preferences: dict = None

@app.post("/recommend")
async def get_recommendations(request: RecommendationRequest):
    recommendations = {
        "sleep": generate_sleep_recommendations(request.sleep_data),
        "stress": generate_stress_recommendations(request.stress_level),
        "premium": {
            "available": True,
            "services": ["1对1睡眠教练", "个性化减压方案"]
        }
    }
    
    return {
        "status": "success",
        "user_id": request.user_id,
        "recommendations": recommendations
    }


if __name__ == "__main__":
     
      

    # 检查端口是否可用
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", PORT))
        sock.close()

        # 确保服务器线程正确启动和关闭
        server_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={"app": app, "host": "0.0.0.0", "port": PORT},
            daemon=True
        )
        server_thread.start()
    
    except OSError:
        sock.close()
        print(f"\n错误: 端口{PORT}已被占用，请先关闭占用该端口的程序")
        print("解决方法:")
        print("1. 查找占用端口的进程: netstat -ano | findstr :{PORT}")
        print("2. 终止进程: taskkill /PID <PID> /F")
        sys.exit(1)

        import uvicorn
        import threading
        
        # 在子线程中启动服务器
        server_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={"app": app, "host": "0.0.0.0", "port": PORT}
        )
        server_thread.daemon = True
        server_thread.start()
        
        # 等待服务器启动
        time.sleep(2)
        
        print("\n=== API测试系统 ===")
        print("1. 自动运行完整测试套件")
        print("2. 手动上传EDF文件测试") 
        print("3. 运行特征提取测试")
        print("4. 测试商业化功能")  # 新增选项
        print("5. 退出")
        
        choice = input("请选择操作(1-4): ").strip()
        
        if choice == "1":
            print("\n=== 运行完整测试套件 ===")
            print("\n[阶段1] 基础EDF文件测试")
            send_edf_to_api(edf_file_path)
            print("\n[阶段2] 特征测试")
            test_feature_extraction()
            print("\n[阶段3] 性能测试")
            test_api_performance()
        elif choice == "2":
            try:
                from tkinter import Tk, filedialog
                root = Tk()
                root.withdraw()  # 隐藏主窗口
                filepath = filedialog.askopenfilename(
                    title="选择EDF文件",
                    filetypes=[("EDF文件", "*.edf *.rec"), ("所有文件", "*.*")]
                )
                root.destroy()
                
                if filepath:
                    send_edf_to_api(filepath)
                else:
                    print("未选择文件")
            except ImportError:
                print("警告: 缺少tkinter支持，将使用命令行输入")
                filepath = input("请输入EDF文件完整路径: ").strip()
                if os.path.exists(filepath):
                    send_edf_to_api(filepath)
                else:
                    print(f"错误: 文件不存在 - {filepath}")
        elif choice == "3":
            test_feature_extraction()
        elif choice == "4":
            test_commercial_features()
        else:
            print("无效选择")
        
        # 保持主线程运行
        while True:
            time.sleep(1)
            
    except OSError:
        print(f"\n错误: 端口{PORT}已被占用，请先关闭占用该端口的程序")
        print("解决方法:")
        print("1. 查找占用端口的进程: netstat -ano | findstr :8000")
        print("2. 终止进程: taskkill /PID <PID> /F")
        sys.exit(1)