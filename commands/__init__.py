# Here you define the commands that will be added to your add-in.

# Import the modules corresponding to the commands.
# To add a new command, duplicate an existing directory and import it here.
from .createBendSheet import entry as createBendSheet
from .manageBenders import entry as manageBenders
from .manageTubes import entry as manageTubes

# Fusion will automatically call the start() and stop() functions.
commands = [
    createBendSheet,
    manageBenders,
    manageTubes,
]


# Assumes you defined a "start" function in each of your modules.
# The start function will be run when the add-in is started.
def start():
    for command in commands:
        command.start()


# Assumes you defined a "stop" function in each of your modules.
# The stop function will be run when the add-in is stopped.
def stop():
    for command in commands:
        command.stop()
