from src.aggregate import alimenter_series
from src.extract import extraire_tout
from src.load import charger_analytics, charger_brut
from src.transform import transformer_tout

dfs    = extraire_tout()
charger_brut(dfs)

propres = transformer_tout(dfs)
charger_analytics(propres)

alimenter_series()
