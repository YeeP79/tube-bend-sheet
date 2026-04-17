"""
Pytest configuration for TubeFabrication tests.

This conftest.py sets up the Python path and module aliases so that tests can
import project modules using simple names (e.g., `from core.x import y`) while
the production code uses relative imports for Fusion 360 compatibility.

How it works:
1. Adds the parent of TubeFabrication to sys.path
2. Imports TubeFabrication as a package (triggering __init__.py)
3. Creates module aliases so `import core` resolves to `TubeFabrication.core`
"""
import sys
from pathlib import Path

# Add the parent directory of TubeFabrication to sys.path
# This allows `import TubeFabrication` to work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root.parent))

# Also keep the project root in path for any direct imports
sys.path.insert(0, str(project_root))

# Import package submodules and create aliases
# This allows tests to use simple imports like `from core.x import y`
# while the production code uses relative imports for Fusion 360 compatibility
import TubeFabrication.core as core
import TubeFabrication.core.compensation as _core_compensation
import TubeFabrication.core.tolerances as _core_tolerances
import TubeFabrication.core.protocols as _core_protocols
import TubeFabrication.core.conventions as _core_conventions
import TubeFabrication.core.cope_math as _core_cope_math
import TubeFabrication.core.cope_template as _core_cope_template
import TubeFabrication.core.cope_path as _core_cope_path
import TubeFabrication.core.combined_output as _core_combined_output
import TubeFabrication.core.body_profile as _core_body_profile
import TubeFabrication.core.body_path as _core_body_path
import TubeFabrication.core.sketch_matching as _core_sketch_matching
import TubeFabrication.models as models
import TubeFabrication.models.cope_data as _models_cope_data
import TubeFabrication.models.cope_input as _models_cope_input
import TubeFabrication.models.body_path_data as _models_body_path_data
import TubeFabrication.models.match_data as _models_match_data
import TubeFabrication.models.tube as _models_tube
import TubeFabrication.models.compensation as _models_compensation
import TubeFabrication.models.constants as _models_constants
import TubeFabrication.storage as storage

sys.modules['core'] = core
sys.modules['models'] = models
sys.modules['storage'] = storage

# Also alias the submodules for imports like `from core.calculations import x`
sys.modules['core.geometry'] = core.geometry
sys.modules['core.geometry_extraction'] = core.geometry_extraction
sys.modules['core.path_ordering'] = core.path_ordering
sys.modules['core.calculations'] = core.calculations
sys.modules['core.formatting'] = core.formatting
sys.modules['core.html_generator'] = core.html_generator
sys.modules['core.grip_tail'] = core.grip_tail
sys.modules['core.direction_validation'] = core.direction_validation
sys.modules['core.compensation'] = _core_compensation
sys.modules['core.tolerances'] = _core_tolerances
sys.modules['core.protocols'] = _core_protocols
sys.modules['core.conventions'] = _core_conventions
sys.modules['core.cope_math'] = _core_cope_math
sys.modules['core.cope_template'] = _core_cope_template
sys.modules['core.cope_path'] = _core_cope_path
sys.modules['core.combined_output'] = _core_combined_output
sys.modules['core.body_profile'] = _core_body_profile
sys.modules['core.body_path'] = _core_body_path
sys.modules['core.sketch_matching'] = _core_sketch_matching

sys.modules['models.bender'] = models.bender
sys.modules['models.bend_data'] = models.bend_data
sys.modules['models.types'] = models.types
sys.modules['models.units'] = models.units
sys.modules['models.tube'] = _models_tube
sys.modules['models.compensation'] = _models_compensation
sys.modules['models.constants'] = _models_constants
sys.modules['models.cope_data'] = _models_cope_data
sys.modules['models.cope_input'] = _models_cope_input
sys.modules['models.body_path_data'] = _models_body_path_data
sys.modules['models.match_data'] = _models_match_data

sys.modules['storage.profiles'] = storage.profiles

# Import and alias test helpers module
import TubeFabrication.tests.helpers as helpers
sys.modules['helpers'] = helpers
