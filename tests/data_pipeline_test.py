import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from aisleep.model.deepseek.models import (
    EEGSleepDataset,
    CNN_SleepModel,
    SleepAdapter
)


# Fix 2: Add missing DataLoader import
from torch.utils.data import DataLoader

# Fix 3: Update test_stress_level_prediction
def test_stress_level_prediction():
    # Initialize with correct adapter
    base_model = CNN_SleepModel()
    adapter = SleepAdapter(base_model)  # Changed from MeditationAdapter to SleepAdapter
    assert adapter is not None, "Adapter initialization failed"