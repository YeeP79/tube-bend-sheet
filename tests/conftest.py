"""
Pytest configuration for TubeBendSheet tests.

This conftest.py sets up the Python path and module aliases so that tests can
import project modules using simple names (e.g., `from core.x import y`) while
the production code uses relative imports for Fusion 360 compatibility.

How it works:
1. Adds the parent of TubeBendSheet to sys.path
2. Imports TubeBendSheet as a package (triggering __init__.py)
3. Creates module aliases so `import core` resolves to `TubeBendSheet.core`
"""
import sys
from pathlib import Path

# Add the parent directory of TubeBendSheet to sys.path
# This allows `import TubeBendSheet` to work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root.parent))

# Also keep the project root in path for any direct imports
sys.path.insert(0, str(project_root))

# Import package submodules and create aliases
# This allows tests to use simple imports like `from core.x import y`
# while the production code uses relative imports for Fusion 360 compatibility
import TubeBendSheet.core as core
import TubeBendSheet.models as models
import TubeBendSheet.storage as storage

sys.modules['core'] = core
sys.modules['models'] = models
sys.modules['storage'] = storage

# Also alias the submodules for imports like `from core.calculations import x`
sys.modules['core.geometry'] = core.geometry
sys.modules['core.geometry_extraction'] = core.geometry_extraction
sys.modules['core.path_analysis'] = core.path_analysis
sys.modules['core.path_ordering'] = core.path_ordering
sys.modules['core.calculations'] = core.calculations
sys.modules['core.formatting'] = core.formatting
sys.modules['core.html_generator'] = core.html_generator
sys.modules['core.grip_tail'] = core.grip_tail

sys.modules['models.bender'] = models.bender
sys.modules['models.bend_data'] = models.bend_data
sys.modules['models.types'] = models.types
sys.modules['models.units'] = models.units

sys.modules['storage.profiles'] = storage.profiles

# Import and alias test helpers module
import TubeBendSheet.tests.helpers as helpers
sys.modules['helpers'] = helpers
