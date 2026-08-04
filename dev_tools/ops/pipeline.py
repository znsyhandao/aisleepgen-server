# -*- coding: utf-8 -*-
"""Pipeline wrapper — redirects to project root pipeline.py"""
import sys, os, subprocess
root = r'D:\AISleepGen_Optimized'
script = os.path.join(root, 'pipeline.py')
args = [sys.executable, script] + sys.argv[1:]
r = subprocess.run(args)
sys.exit(r.returncode)
