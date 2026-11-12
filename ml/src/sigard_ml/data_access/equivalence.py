"""Cell-level comparison for explicit historical audits, with no file readers.

Callers may load frozen historical files ONLY in a separate audit/reproduction
tool. Operational training does not import that tool or accept its files.
The report never sets the database equivalence flag or manufactures labels.
"""

import numpy as np
import pandas as pd


def compare_frames(historical, reconstructed, *, keys, features, labels=(), temporal=()):
    columns = list(dict.fromkeys([*features, *labels, *temporal]))
    result = dict(historical_rows=len(historical), postgres_rows=len(reconstructed),
                  keys=list(keys), features=list(features), labels=list(labels),
                  missing_columns={}, column_differences={}, duplicate_keys=False, missing_keys=False)
    for name, frame in [('historical', historical), ('postgres', reconstructed)]:
        result['missing_columns'][name] = sorted(set([*keys, *columns]) - set(frame.columns))
        result['duplicate_keys'] |= bool(set(keys) <= set(frame.columns) and frame.duplicated(keys).any())
        result['missing_keys'] |= bool(set(keys) <= set(frame.columns) and frame[keys].isna().any().any())
    if any(result['missing_columns'].values()) or result['duplicate_keys'] or result['missing_keys']:
        result['equivalent'] = False
        return result
    left = historical.set_index(keys).sort_index()
    right = reconstructed.set_index(keys).sort_index()
    result['historical_only_keys'] = len(left.index.difference(right.index))
    result['postgres_only_keys'] = len(right.index.difference(left.index))
    common = left.index.intersection(right.index)
    result['compared_rows'] = len(common)
    for key in keys:
        a, b = historical[key], reconstructed[key]
        result[key + '_distinct'] = dict(historical=int(a.nunique()), postgres=int(b.nunique()))
    for column in columns:
        a, b = left.loc[common, column], right.loc[common, column]
        missing = a.isna() ^ b.isna()
        both = a.notna() & b.notna()
        numeric = pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)
        if numeric and column in features and column not in labels and column not in temporal:
            # No tolerance for labels, masks or temporal keys; only SQL/Python
            # floating trig/averages can differ at round-off precision.
            equal = np.isclose(a[both].astype(float), b[both].astype(float), rtol=0,
                               atol=1e-12)
            different = int((~equal).sum())
        else:
            different = int(a[both].ne(b[both]).sum())
        result['column_differences'][column] = dict(
            historical_missing=int(historical[column].isna().sum()),
            postgres_missing=int(reconstructed[column].isna().sum()),
            missingness_mismatches=int(missing.sum()), value_mismatches=different)
    result['equivalent'] = bool(len(historical) and len(common) == len(left) == len(right)
        and not any(v['missingness_mismatches'] or v['value_mismatches'] for v in result['column_differences'].values()))
    return result
