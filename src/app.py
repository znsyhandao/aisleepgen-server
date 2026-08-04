from flask import Flask
from aisleep.api.wechat.wechat_routes import wechat_bp

app = Flask(__name__)

# 注册蓝图
app.register_blueprint(wechat_bp)

# 添加配置
app.config.update({
    'JSON_AS_ASCII': False,
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024  # 16MB
})

# ... 原有代码 ...

def create_app():
    app = Flask(__name__)
    
    # 配置加载
    app.config.from_pyfile('config.py')
    
    # 蓝图注册
    from aisleep.api.wechat.wechat_routes import wechat_bp
    app.register_blueprint(wechat_bp)
    
    # 健康检查路由
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy'}), 200
    
    return app

# 兼容直接运行
if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
