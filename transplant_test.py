import numpy as np
from collections import Counter
from scipy.stats import chi2_contingency, ttest_ind

def transplant_test_sleep(sleep_stages, transplant_indices, control_indices, alpha=0.05):
    """
    Perform a statistical test comparing sleep stage distributions between a transplant group and a control group.
    Uses chi-square test for categorical sleep stages and t-test for continuous sleep metrics.

    Parameters
    ----------
    sleep_stages : numpy.ndarray
        1D array of sleep stage labels (integers 0-4 representing Wake, N1, N2, N3, REM).
    transplant_indices : numpy.ndarray
        1D array of indices corresponding to the transplant group.
    control_indices : numpy.ndarray
        1D array of indices corresponding to the control group.
    alpha : float, optional
        Significance level for hypothesis tests (default 0.05).

    Returns
    -------
    dict
        Dictionary containing:
        - 'chi2_statistic': float, chi-square test statistic
        - 'chi2_p_value': float, p-value from chi-square test
        - 'chi2_significant': bool, whether chi-square test is significant
        - 't_statistic': float, t-test statistic for mean sleep stage comparison
        - 't_p_value': float, p-value from t-test
        - 't_significant': bool, whether t-test is significant
        - 'transplant_stage_counts': dict, stage counts in transplant group
        - 'control_stage_counts': dict, stage counts in control group
        - 'transplant_mean_stage': float, mean sleep stage in transplant group
        - 'control_mean_stage': float, mean sleep stage in control group
    """
    # Input validation
    if not isinstance(sleep_stages, np.ndarray) or sleep_stages.ndim != 1:
        raise TypeError("sleep_stages must be a 1D numpy array")
    if not isinstance(transplant_indices, np.ndarray) or transplant_indices.ndim != 1:
        raise TypeError("transplant_indices must be a 1D numpy array")
    if not isinstance(control_indices, np.ndarray) or control_indices.ndim != 1:
        raise TypeError("control_indices must be a 1D numpy array")
    if not isinstance(alpha, (int, float)) or alpha <= 0 or alpha >= 1:
        raise ValueError("alpha must be a float between 0 and 1")
    if len(transplant_indices) == 0 or len(control_indices) == 0:
        raise ValueError("transplant_indices and control_indices must not be empty")
    if np.max(transplant_indices) >= len(sleep_stages) or np.max(control_indices) >= len(sleep_stages):
        raise ValueError("Indices out of bounds for sleep_stages")
    if np.any(transplant_indices < 0) or np.any(control_indices < 0):
        raise ValueError("Indices must be non-negative")
    if np.any(np.isin(transplant_indices, control_indices)):
        raise ValueError("transplant_indices and control_indices must be disjoint")

    # Extract sleep stage data for each group
    transplant_stages = sleep_stages[transplant_indices]
    control_stages = sleep_stages[control_indices]

    # Validate stage labels are integers 0-4
    all_stages = np.concatenate([transplant_stages, control_stages])
    if not np.all(np.isin(all_stages, [0, 1, 2, 3, 4])):
        raise ValueError("Sleep stages must be integers 0-4")

    # Compute stage counts for each group
    transplant_counts = Counter(transplant_stages)
    control_counts = Counter(control_stages)

    # Build contingency table for chi-square test
    all_stage_labels = np.arange(5)
    transplant_freq = np.array([transplant_counts.get(s, 0) for s in all_stage_labels])
    control_freq = np.array([control_counts.get(s, 0) for s in all_stage_labels])
    contingency_table = np.vstack([transplant_freq, control_freq])

    # Chi-square test of independence
    chi2_stat, chi2_p, _, _ = chi2_contingency(contingency_table)
    chi2_significant = chi2_p < alpha

    # T-test comparing mean sleep stage between groups
    t_stat, t_p = ttest_ind(transplant_stages, control_stages, equal_var=False)
    t_significant = t_p < alpha

    # Compute mean sleep stages
    transplant_mean = float(np.mean(transplant_stages))
    control_mean = float(np.mean(control_stages))

    # Prepare output dictionary
    result = {
        'chi2_statistic': float(chi2_stat),
        'chi2_p_value': float(chi2_p),
        'chi2_significant': bool(chi2_significant),
        't_statistic': float(t_stat),
        't_p_value': float(t_p),
        't_significant': bool(t_significant),
        'transplant_stage_counts': {int(k): int(v) for k, v in transplant_counts.items()},
        'control_stage_counts': {int(k): int(v) for k, v in control_counts.items()},
        'transplant_mean_stage': transplant_mean,
        'control_mean_stage': control_mean
    }

    return result