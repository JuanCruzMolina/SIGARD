"""Runtime assertion used by research runs/tests, never around ingestion."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from os import PathLike
from unittest.mock import patch
import builtins
import io

from .postgres import DatasetBlocked


@contextmanager
def forbid_tabular_reads():
    import pandas as pd
    import geopandas as gpd
    import openpyxl
    import pyarrow.parquet as pq
    import pyarrow.csv as pc
    import pyarrow.dataset as ds

    def forbidden(*args, **kwargs):
        raise DatasetBlocked('operational_tabular_source_read_forbidden')
    def guarded(original):
        def checked(file,*args,**kwargs):
            if isinstance(file,(str,PathLike)) and Path(file).suffix.lower() in ('.csv','.tsv','.xlsx','.xls','.parquet','.feather'):
                forbidden()
            return original(file,*args,**kwargs)
        return checked
    with ExitStack() as guards:
        for obj,names in [(pd,('read_csv','read_table','read_parquet','read_excel','read_feather')),
            (gpd,('read_parquet','read_file')),(openpyxl,('load_workbook',)),
            (pq,('read_table','ParquetFile')),(pc,('read_csv',)),(ds,('dataset',))]:
            for name in names:
                guards.enter_context(patch.object(obj,name,forbidden))
        guards.enter_context(patch.object(builtins,'open',guarded(builtins.open)))
        guards.enter_context(patch.object(io,'open',guarded(io.open)))
        yield
