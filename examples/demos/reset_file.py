# system imports
import filecmp
from pathlib import Path
from shutil import copy2

# traits imports
from traits.api import HasTraits, Str, File, Directory, Button
from traitsui.api import View, Item, FileEditor, VGroup

MASTER_FILE = Path(__file__).parent / "master_sample.txt"

class ResetDefaultFileDemo(HasTraits):

    name = Str()
    file = File()
    default_dir = Directory()
    reset_button = Button("Reset to Defaults")
    mod_def_text = Button("Modify")

    def _default_dir_default(self) -> Path:
        default_dir = Path().home() / "Documents" / "scratch_tests" / "texts_repo"

        default_dir.mkdir(parents=True, exist_ok=True)

        print(f"Default directory is: {default_dir}")

        return default_dir

    def _file_default(self):
        """Sets the default file path and creates a sample file if needed."""

        # --- Define Master File Path (local to the script) ---
        print(f"Master file is located at: {MASTER_FILE}")
        if not MASTER_FILE.exists():
            print("Master file not found, creating it...")
            MASTER_FILE.write_text("This is the MASTER copy of the sample file.")

        # --- Ensure User's File is a Copy of Master on First Run ---
        user_file = Path(self.default_dir) / "sample.txt"
        print(f"Checking for user's default file: {user_file}")
        should_overwrite = True
        if user_file.exists():
            # If the user's file exists, check if it's different from master
            if filecmp.cmp(MASTER_FILE, user_file, shallow=False):
                print("User's file already exists and matches master.")
                should_overwrite = False
            else:
                print("User's file exists but is different from master. Overwriting...")
        else:
            print("User's default file not found, creating it from master...")

        if should_overwrite:
            # user_file.write_text(MASTER_FILE.read_text())
            copy2(str(MASTER_FILE), str(user_file))

        return str(user_file)

    def _reset_button_fired(self):
        """
        Handles the user clicking the 'Reset to Defaults' button.
        This will reset the 'file' trait back to its default value.
        """
        print("\n--- Resetting traits to default values ---")
        self.reset_traits(traits=['file'])
        print(f"The 'file' trait has been reset to: {self.file}")
        print("----------------------------------------\n")

    view = View(
        VGroup(
            Item(
                'file',
                id='file1',
                label="File Path",
                editor=FileEditor(root_path_name='file', filter=['Texts (*.txt)']),
            ),
            # A simple button to trigger the reset action
            Item('reset_button'),
            Item('mod_def_text'),
        ),
        width=500,
        resizable=True,
    )

    def _mod_def_text_fired(self):
        Path(self.file).write_text("CHANGED FILE: No longer the master copy.")
        print("Modified Selected File")


# Create the demo:
demo = ResetDefaultFileDemo()


if __name__ == '__main__':
    demo.configure_traits()

