"""Package de services pour ``stockapp``.

Ne pas importer les sous-modules ici pour éviter les importations circulaires
entre ``models`` et les services (les sous-modules doivent être importés
explicitement là où ils sont utilisés).
"""

# Les sous-modules sont importés de façon explicite par les consommateurs.
__all__ = []
