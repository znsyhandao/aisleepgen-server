# -*- coding: utf-8 -*-
"""Wrapper for cross_night_pipeline.py"""
import sys, os, subprocess
root = r'D:\AISleepGen_Optimized'
script = os.path.join(root, 'cross_night_pipeline.py')
args = [sys.executable, script] + sys.argv[1:]
r = subprocess.run(args)
sys.exit(r.returncode)
