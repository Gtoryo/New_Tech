from src.extract import extraire_tout
from src.load import charger_brut

dfs = extraire_tout()
charger_brut(dfs)
