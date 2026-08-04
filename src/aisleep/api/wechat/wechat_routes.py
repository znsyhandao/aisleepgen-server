from flask import Blueprint, request, jsonify
from aisleep.services.wechat_service import WeChatService

wechat_bp = Blueprint('wechat', __name__, url_prefix='/api/wechat/v1')
service = WeChatService()

@wechat_bp.route('/lite_analysis', methods=['POST'])
def lite_analysis():
    try:
        data = request.get_json()
        return jsonify(service.process_lite_analysis(
            openid=data['openid'],
            signals=data['signals']
        )), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@wechat_bp.route('/daily_checkin', methods=['POST'])
def daily_checkin():
    try:
        return jsonify(service.process_check_in(
            user_id=request.json['user_id']
        )), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400