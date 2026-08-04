import sys
import os
from pathlib import Path
from aisleep.model.deepseek import models  # Or your actual module structure

from aisleep.model import deepseek  # 如果 deepseek 是模块而不是目录

print("Deepseek model loaded:", models.CNN_SleepModel.__name__)





#def test_initialization():
#    print("=== 参数初始化测试 ===")
#    model = Custom_Model(128, 256, 5)
#    for name, param in model.named_parameters():
#        print(f"{name:25} mean:{param.mean().item():.7f} std:{param.std().item():.7f}")

#if __name__ == "__main__":
    # 只保留与Custom_Model相关的测试
#    test_initialization()



import tkinter as tk
from tkinter import ttk, messagebox
import torch
import torchaudio

def load_model(model_name):
    # 代码：加载预训练模型
    pass


def main():
    root = tk.Tk()
    root.title("眠小兔AI智能体")
    root.geometry("800x600")

    frame = tk.Frame(root)
    frame.pack(pady=20)

    model_label = tk.Label(frame, text="选择模型")
    model_label.pack()

    model_options = [
        "Deepseek-R1-Distill-Qwen-7B",
        "Deepseek-R1-Distill-Qwen-32B",
        "Deepseek-R1-Distill-Qwen-70B"
    ]

    model_var = tk.StringVar()
    model_menu = ttk.Combobox(frame, textvariable=model_var, values=model_options)
    model_menu.pack()

    model_menu.bind("<<MenuChange>>", lambda e: print(f"选择了 {e.data}"))

    def open_dialogue():
        messagebox.showmessage(
            title="眠小兔AI智能体",
            message="请选择您想要的AI模型"
        )

    def open_file_dialog():
        file_path = tk.filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("音频文件", "*.wav *.mp3"), ("所有文件", "*.*")]
        )
        if file_path:
            result_label.config(text=f"已选择文件: {file_path}")

    def choose_color():
        color = tk.colorchooser.askcolor(title="选择主题色")
        if color[1]:
            result_label.config(text=f"选择颜色: {color[1]}", fg=color[1])

    def input_dialog():
        answer = tk.simpledialog.askstring("输入", "请输入您的睡眠问题")
        if answer:
            result_label.config(text=f"收到问题: {answer}")


 # 添加新的对话框按钮
    dialog_frame = tk.Frame(frame)
    dialog_frame.pack(pady=10)

    tk.Button(dialog_frame, text="文件选择", command=open_file_dialog).grid(row=0, column=0, padx=5)
    tk.Button(dialog_frame, text="颜色选择", command=choose_color).grid(row=0, column=1, padx=5)
    tk.Button(dialog_frame, text="输入对话框", command=input_dialog).grid(row=0, column=2, padx=5)
    tk.Button(dialog_frame, text="欢迎提示", command=open_dialogue).grid(row=0, column=3, padx=5)




    dialogue_button = tk.Button(frame, text="打开对话框", command=open_dialogue)
    dialogue_button.pack()

    root.mainloop()


