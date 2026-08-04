cd /opt/aisleepgen
# 清理 requirements.txt
sed -i '/modelarts/d' requirements.txt
sed -i '/^#/d' requirements.txt
sed -i '/^\s*$/d' requirements.txt
pip3 install -r requirements.txt 2>&1 | tail -10
echo "=== IMPORT TEST ==="
python3 -c "import sys; sys.path.insert(0,'.'); exec(open('deepseek_proxy.py').read().split('if __name__')[0]); print('IMPORT OK')" 2>&1
