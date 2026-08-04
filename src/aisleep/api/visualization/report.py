import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages

def generate_report(predictions, hr=None, spo2=None):
    """生成PDF格式的睡眠报告"""
    with PdfPages("sleep_report.pdf") as pdf:
        # 睡眠阶段分布图
        plt.figure(figsize=(10, 6))
        sns.barplot(x=["W", "N1", "N2", "N3", "REM"], 
                   y=predictions.mean(0))
        plt.title("Sleep Stage Distribution")
        pdf.savefig()
        
        # 多模态数据融合图
        if hr and spo2:
            plt.figure(figsize=(12, 4))
            plt.plot(hr, label='Heart Rate')
            plt.plot(spo2, label='SpO2')
            plt.legend()
            pdf.savefig()
