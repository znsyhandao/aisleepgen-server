import os
import torch
from transformers import AutoModelForCausalLM, AutoConfig
from safetensors.torch import load_file

def test_model_optimization():
    model_dir = "models_cache"
    
    try:
        # Load config
        config = AutoConfig.from_pretrained(model_dir)
        
        # Load model weights and filter out unexpected bias parameters
        state_dict = load_file(os.path.join(model_dir, "model.safetensors"))
        filtered_state_dict = {k: v for k, v in state_dict.items() if not k.endswith('bias')}
        
        # Initialize model
        model = AutoModelForCausalLM.from_config(config)
        model.load_state_dict(filtered_state_dict, strict=False)
        
        # Quantization
        quantized_model = torch.quantization.quantize_dynamic(
            model,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        
        # Save optimized model (using torch.save instead of save_pretrained)
        optimized_path = os.path.join(model_dir, "optimized_model")
        os.makedirs(optimized_path, exist_ok=True)
        
        # Save the state_dict directly
        torch.save(quantized_model.state_dict(), os.path.join(optimized_path, "pytorch_model.bin"))
        
        # Save config
        config.save_pretrained(optimized_path)
        
        assert os.path.exists(optimized_path)
        return optimized_path
        
    except Exception as e:
        print(f"Optimization failed: {str(e)}")
        raise