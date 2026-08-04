import os
import logging
from typing import Optional, Dict, Any
import torch
import boto3
from botocore.exceptions import ClientError
try:
    from alibabacloud_pai import Client as AliyunClient
    from alibabacloud_tea_openapi import models as open_api_models
except ImportError:
    AliyunClient = None

logger = logging.getLogger(__name__)

class CloudModelLoader:
    """云端模型加载工具类"""
    
    @staticmethod
    async def load(provider: str, model_path: str, config: Optional[Dict] = None) -> torch.nn.Module:
        """
        加载云端模型
        :param provider: 云服务商 (aws/aliyun)
        :param model_path: 模型路径
        :param config: 配置参数
        :return: 加载的PyTorch模型
        """
        if provider.lower() == "aws":
            return await AWSModelLoader.load(model_path, config or {})
        elif provider.lower() == "aliyun":
            return await AliyunPAILoader.load(model_path, config or {})
        else:
            raise ValueError(f"不支持的云服务商: {provider}")

class AWSModelLoader:
    """AWS SageMaker模型加载实现"""
    
    @staticmethod
    async def load(model_path: str, config: Dict[str, Any]) -> torch.nn.Module:
        try:
            # 从环境变量获取凭证或使用传入配置
            aws_config = {
                'aws_access_key_id': config.get('aws_access_key') or os.getenv('AWS_ACCESS_KEY_ID'),
                'aws_secret_access_key': config.get('aws_secret_key') or os.getenv('AWS_SECRET_ACCESS_KEY'),
                'region_name': config.get('region', 'us-west-2')
            }
            
            runtime = boto3.client('sagemaker-runtime', **aws_config)
            
            # 调用SageMaker端点
            response = runtime.invoke_endpoint(
                EndpointName=model_path,
                ContentType='application/json',
                Body=config.get('input_data', '{}')
            )
            
            # 将响应转换为模型
            return CloudModelWrapper(response, provider='aws')
            
        except ClientError as e:
            logger.error(f"AWS SageMaker调用失败: {str(e)}")
            raise RuntimeError(f"AWS服务错误: {e.response['Error']['Message']}")

class AliyunPAILoader:
    """阿里云PAI模型加载实现"""
    
    @staticmethod
    async def load(model_path: str, config: Dict[str, Any]) -> torch.nn.Module:
        if AliyunClient is None:
            raise RuntimeError("未安装阿里云SDK，请运行: pip install alibabacloud_pai")
            
        try:
            # 配置阿里云客户端
            aliyun_config = open_api_models.Config(
                access_key_id=config.get('access_key') or os.getenv('ALIYUN_ACCESS_KEY'),
                access_key_secret=config.get('secret_key') or os.getenv('ALIYUN_SECRET_KEY'),
                endpoint=config.get('endpoint', 'pai.cn-beijing.aliyuncs.com')
            )
            
            client = AliyunClient(aliyun_config)
            response = await client.predict(
                model_path=model_path,
                input_data=config.get('input_data', {})
            )
            
            return CloudModelWrapper(response, provider='aliyun')
            
        except Exception as e:
            logger.error(f"阿里云PAI调用失败: {str(e)}")
            raise RuntimeError(f"阿里云服务错误: {str(e)}")

class CloudModelWrapper(torch.nn.Module):
    """云端模型包装器"""
    
    def __init__(self, cloud_response, provider: str):
        super().__init__()
        self.cloud_response = cloud_response
        self.provider = provider
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def forward(self, *args, **kwargs):
        """重写forward方法以调用云端推理"""
        # 将输入数据转换为云端API需要的格式
        input_data = self._prepare_input(*args, **kwargs)
        
        if self.provider == 'aws':
            # AWS SageMaker响应处理
            result = self.cloud_response['Body'].read().decode('utf-8')
            return torch.tensor(eval(result), device=self.device)
        else:
            # 阿里云PAI响应处理
            return torch.tensor(self.cloud_response['predictions'], device=self.device)
    
    def _prepare_input(self, *args, **kwargs):
        """准备云端API输入数据"""
        # 实现您的数据预处理逻辑
        return {
            'tensor_data': args[0].cpu().numpy().tolist(),
            **kwargs
        }

def check_cloud_credentials(provider: str) -> bool:
    """检查云服务凭证是否配置"""
    if provider == 'aws':
        return bool(os.getenv('AWS_ACCESS_KEY_ID')) or ('aws_access_key' in os.environ)
    elif provider == 'aliyun':
        return bool(os.getenv('ALIYUN_ACCESS_KEY')) or ('aliyun_access_key' in os.environ)
    return False
