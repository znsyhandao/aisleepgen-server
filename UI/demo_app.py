import asyncio
import streamlit as st

# Add this before any PyTorch imports
if not hasattr(asyncio, '_get_running_loop'):
    asyncio._get_running_loop = asyncio.get_event_loop

# ... rest of your imports ...
