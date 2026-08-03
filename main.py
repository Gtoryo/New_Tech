from src.extract import extraire_tout
from src.transform import transformer_tout
from src.load import charger_brut, charger_analytics
from src.aggregate import alimenter_series

dfs    = extraire_tout()
charger_brut(dfs)

propres = transformer_tout(dfs)
charger_analytics(propres)

alimenter_series()
