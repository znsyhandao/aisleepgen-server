#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sleep_similarity.py -- user similarity search (FAISS vector search)"""
import os, json, numpy as np
_user_embeddings = {}

def index_user(openid, profile_vector):
    _user_embeddings[openid] = np.array(profile_vector, dtype=np.float32)

def find_similar_users(openid, top_k=5):
    if openid not in _user_embeddings or len(_user_embeddings) < 2:
        return []
    return _bruteforce_search(openid, top_k)

def _bruteforce_search(openid, top_k):
    vec = _user_embeddings[openid]
    scores = []
    for uid, uvec in _user_embeddings.items():
        if uid == openid:
            continue
        sim = float(np.dot(vec, uvec) / (np.linalg.norm(vec) * np.linalg.norm(uvec) + 1e-8))
        scores.append((uid, sim))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]
