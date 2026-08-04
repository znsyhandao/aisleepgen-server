import tkinter as tk
from tkinter import ttk, messagebox
from .meditation import AITestInterface, MeditationGuide
from .config import cfg


class MeditationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI减压助眠系统")
        self.root.geometry("800x600")
        
        # 初始化AI核心
        self.guide = MeditationGuide()
        self.interface = AITestInterface.create_default()
        
        # 创建UI
        self.create_widgets()
        
    def create_widgets(self):
        # 顶部控制面板
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X)
        
        ttk.Label(control_frame, text="选择模式:").grid(row=0, column=0, padx=5)
        self.mode_var = tk.StringVar()
        self.mode_combobox = ttk.Combobox(
            control_frame, 
            textvariable=self.mode_var,
            values=[cfg['name'] for cfg in self.interface.get_test_configurations()]
        )
        self.mode_combobox.grid(row=0, column=1, padx=5)
        self.mode_combobox.current(0)
        
        ttk.Label(control_frame, text="持续时间(秒):").grid(row=0, column=2, padx=5)
        self.duration_var = tk.StringVar(value="300")
        ttk.Entry(control_frame, textvariable=self.duration_var, width=8).grid(row=0, column=3, padx=5)
        
        ttk.Button(control_frame, text="开始测试", command=self.start_session).grid(row=0, column=4, padx=10)
        ttk.Button(control_frame, text="查看报告", command=self.show_report).grid(row=0, column=5, padx=10)
        
        # 实时反馈面板
        feedback_frame = ttk.LabelFrame(self.root, text="实时生物反馈", padding="10")
        feedback_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 心率图表
        self.hr_canvas = tk.Canvas(feedback_frame, height=150, bg="white")
        self.hr_canvas.pack(fill=tk.X, pady=5)
        ttk.Label(feedback_frame, text="心率 (BPM)").pack()
        
        # 压力水平图表
        self.stress_canvas = tk.Canvas(feedback_frame, height=150, bg="white")
        self.stress_canvas.pack(fill=tk.X, pady=5)
        ttk.Label(feedback_frame, text="压力水平 (0-1)").pack()
        
        # 日志输出
        log_frame = ttk.LabelFrame(self.root, text="系统日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def start_session(self):
        try:
            duration = int(self.duration_var.get())
            mode = self.mode_var.get()
            
            # 获取配置
            configs = self.interface.get_test_configurations()
            pattern = next(cfg['pattern'] for cfg in configs if cfg['name'] == mode)
            
            self.log("开始测试会话...")
            self.log(f"模式: {mode}, 持续时间: {duration}秒")
            
            # 启动会话
            session = self.interface.start_test_session(duration, pattern)
            self.log("测试完成!")
            
            # 更新图表
            self.update_charts(session)

                    
            # 在记录会话数据前添加验证
            if feedback := self.get_current_biofeedback():
                feedback.validate()  # 验证数据有效性
                
            session_data = {
                # ... 现有字段 ...
                'analysis_valid': True  # 标记数据已验证
            }
            
        except Exception as e:
            messagebox.showerror("错误", f"启动会话失败: {str(e)}")
            self.log(f"错误: {str(e)}")
    
    def show_report(self):
        if not self.interface.test_sessions:
            messagebox.showinfo("提示", "还没有测试会话记录")
            return
            
        report = self.interface.generate_report(0)
        messagebox.showinfo("测试报告", report)
        self.log("已生成测试报告")
    
    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
    
    def update_charts(self, session):
        # 这里应该实现图表更新逻辑
        # 实际项目中会连接真实生物反馈数据
        self.log("更新生物反馈图表...")
        # 示例: 绘制简单的心率曲线
        self.hr_canvas.delete("all")
        self.stress_canvas.delete("all")
        
        # 模拟数据
        hr_data = [70, 72, 68, 65, 63, 62]
        stress_data = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        
        # 绘制心率图表
        width = self.hr_canvas.winfo_width()
        height = self.hr_canvas.winfo_height()
        x_step = width / (len(hr_data)-1)
        
        for i in range(len(hr_data)-1):
            x1 = i * x_step
            y1 = height - (hr_data[i] - 60) * 5
            x2 = (i+1) * x_step
            y2 = height - (hr_data[i+1] - 60) * 5
            self.hr_canvas.create_line(x1, y1, x2, y2, fill="red", width=2)
        
        # 绘制压力图表
        for i in range(len(stress_data)-1):
            x1 = i * x_step
            y1 = height - stress_data[i] * height
            x2 = (i+1) * x_step
            y2 = height - stress_data[i+1] * height
            self.stress_canvas.create_line(x1, y1, x2, y2, fill="blue", width=2)

def run_gui():
    root = tk.Tk()
    app = MeditationApp(root)
    root.mainloop()

if __name__ == "__main__":


    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        run_gui()
    except ImportError:
        print("tkinter未安装！")


