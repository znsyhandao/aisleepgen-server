import pytest
from main import some_background_task
from unittest.mock import patch

@pytest.fixture
def mock_background_tasks():
    return patch("main.BackgroundTasks").start()

def test_background_task(mock_background_tasks):
    some_background_task(mock_background_tasks)
    mock_background_tasks.add_task.assert_called_once()
