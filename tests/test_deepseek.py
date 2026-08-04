from integrations.deepseek_integration import load_deepseek_model, generate_text
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

try:
    from integrations.deepseek_integration import load_deepseek_model, generate_text
except ImportError as e:
    print(f"导入错误: {str(e)}")
    sys.exit(1)



def test_model_loading():
    try:
        model = load_deepseek_model()
        print("[OK] 模型加载测试通过")
        return model
    except Exception as e:
        print(f"[FAIL] 模型加载失败: {str(e)}")
        return None

def test_text_generation(model):
    if not model:
        return
        
    try:
        response = generate_text(model, "生成一个冥想指导")
        print("[OK] 文本生成测试通过")
        print("生成结果:", response)
    except Exception as e:
        print(f"[FAIL] 文本生成失败: {str(e)}")

if __name__ == "__main__":
    model = test_model_loading()
    test_text_generation(model)
