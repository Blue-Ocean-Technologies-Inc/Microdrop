from traits.has_traits import Interface
from traits.trait_types import Str, Callable, Any, List, Dict, Int


class IPGSService(Interface):
    #: task_name
    id = Str

    #: name
    name = Str

    #: steps in the protocol
    steps = List

    #: electrodes_on currently for the step
    electrodes_on = Dict(key_trait=Str, value_trait=List(Str))

    #: directory to save files
    file_save_dir = Str

    #: name of the file
    file_name = Str

    def add_step(self, step: str, electrodes_on: List(Str)):
        """Adds the list of electrodes on for the given step to the dictionary with key being the step"""

    def save_protocol(self, file_name: str):
        """initiates saving the current protocol data in a file with the given name"""

    def load_protocol(self, file_path: str):
        """
        load the data from a file and publish it to the load_queue
        This will be sent to frontend to modify view which will call backend
        thus updating data in backend due to cell changed
        """

    def save_to_file(self, table_data_json, file_name):
        """Saves the protocol data to a specific file"""

    def on_cell_changed(self, args):
        """Update data stored in protocol structure when cell data is modified in GUI"""

    def on_electrode_clicked(self, args, kwargs):
        """When device viewer is clicked it should fire message signal to GUI and
        this will be activated to modify stored data structure to key track of triggered/untriggered electrode"""