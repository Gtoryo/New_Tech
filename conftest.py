import sys
import pathlib

# Garantit que les modules src/ et model/ sont importables depuis tests/
sys.path.insert(0, str(pathlib.Path(__file__).parent))
