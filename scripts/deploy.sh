#!/bin/bash
# 商业化部署脚本
gunicorn api.commercial:app -b 0.0.0.0:8000 &
python monitoring/dashboard.py &