# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = False

# Gets the name of the add-in from the name of the folder the py file is in.
# This is used when defining unique internal names for various UI elements 
# that need a unique name. It's also recommended to use a company name as 
# part of the ID to better ensure the ID is unique.
ADDIN_NAME = os.path.basename(os.path.dirname(__file__))
COMPANY_NAME = 'Custom'

# Panel configuration - custom panel in Tools tab
PANEL_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_Panel'
PANEL_NAME = 'Tube Bending'
TAB_ID = 'ToolsTab'
WORKSPACE_ID = 'FusionSolidEnvironment'

# Default values for new benders/dies (stored in centimeters)
DEFAULT_MIN_GRIP_CM = 15.24      # 6 inches
DEFAULT_TUBE_OD_CM = 4.445       # 1.75 inches
DEFAULT_CLR_CM = 13.97           # 5.5 inches
DEFAULT_DIE_OFFSET_CM = 1.74625  # 0.6875 inches
DEFAULT_MIN_TAIL_CM = 5.08       # 2 inches