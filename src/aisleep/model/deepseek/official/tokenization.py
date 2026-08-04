import torch
from transformers import AutoTokenizer

import os
from transformers import AutoTokenizer

class Tokenizer:
    def __init__(self, local_path="models/tokenizer"):
        try:
            # First try loading from local path
            if os.path.exists(local_path):
                self.tokenizer = AutoTokenizer.from_pretrained(
                    local_path,
                    local_files_only=True
                )
            else:
                # If local path doesn't exist, try online with timeout
                self.tokenizer = AutoTokenizer.from_pretrained(
                    "deepseek-ai/deepseek-llm",
                    trust_remote_code=True,
                    timeout=30  # Increase timeout
                )
                # Save for future offline use
                os.makedirs(local_path, exist_ok=True)
                self.tokenizer.save_pretrained(local_path)
                
        except Exception as e:
            raise Exception(
                f"Tokenizer initialization failed. Please ensure:\n"
                f"1. You have internet connection to download the tokenizer\n"
                f"2. Or manually place tokenizer files in {os.path.abspath(local_path)}\n"
                f"Original error: {str(e)}"
            )

    def encode(self, text, return_tensors='pt'):
        return self.tokenizer.encode(text, return_tensors=return_tensors)
        
    def decode(self, tokens, skip_special_tokens=True):
        return self.tokenizer.decode(tokens, skip_special_tokens=skip_special_tokens)

