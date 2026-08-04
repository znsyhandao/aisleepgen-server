import pytest
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def pytest_configure(config):
    # Register all test markers
    markers = [
        "integration: integration tests (require external services)",
        "zope: zope interface tests",
        "peft: parameter-efficient fine-tuning tests",
        "modelarts: Huawei ModelArts service tests",
        "obs: Huawei OBS storage tests"
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)

    # Add environment verification
    print("\n=== Test Environment ===")
    print(f"Python: {sys.version.split()[0]}")
    print(f"PyTorch: available" if 'torch' in sys.modules else "PyTorch: not available")

@pytest.fixture(autouse=True)
def matplotlib_cleanup():
    """Ensure clean matplotlib state for each test"""
    yield
    plt.close('all')

@pytest.fixture
def modelarts_credentials():
    """Fixture for ModelArts credentials"""
    from settings import settings
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    return BasicCredentials(
        settings.obs_access_key,
        settings.obs_secret_key,
        settings.HUAWEI_PROJECT_ID
    )