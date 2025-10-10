# system imports
import filecmp
from pathlib import Path
from shutil import copy2
from typing import Union

# traits imports
from traits.api import HasTraits, Str, File, Directory, Button
from traitsui.api import View, UItem, Item, FileEditor, VGroup
from pyface.api import FileDialog, confirm, YES, NO, OK

MASTER_FILE = Path(__file__).parent / "master_sample.txt"

class ResetDefaultFileLoadFileDemo(HasTraits):

    name = Str()
    file = File()
    repo_dir = Directory()
    reset_button = Button("Reset to Defaults")
    default_user_file = File()

    mod_text = Button("Modify")
    load_file = Button("Load File")

    ##------ Trait defaults--------------------------

    def _repo_dir_default(self) -> Path:
        default_dir = Path().home() / "Documents" / "microdrop_dev_tests" / "texts_repo"

        default_dir.mkdir(parents=True, exist_ok=True)

        print(f"Default repo directory is: {default_dir}")

        return default_dir

    def _default_user_file_default(self) -> str:
        return str(Path(self.repo_dir) / "sample.txt")

    def _file_default(self):
        """Sets the default file path and creates a sample file if needed."""

        # --- Define Master File Path (local to the script) ---
        print(f"Master file is located at: {MASTER_FILE}")
        if not MASTER_FILE.exists():
            print("Master file not found, creating it...")
            MASTER_FILE.write_text("This is the MASTER copy of the sample file.")

        # --- Ensure User's File is a Copy of Master on First Run ---
        default_user_file = Path(self.default_user_file)
        print(f"Checking for user's default file: {default_user_file}")
        should_overwrite = True
        if default_user_file.exists():
            # If the user's file exists, check if it's different from master
            if filecmp.cmp(MASTER_FILE, default_user_file, shallow=False):
                print("User's file already exists and matches master.")
                should_overwrite = False
            else:
                print("User's file exists but is different from master. Overwriting...")
        else:
            print("User's default file not found, creating it from master...")

        if should_overwrite:
            try:
                copy2(str(MASTER_FILE), str(default_user_file))
                print("User's file was successfully loaded")
            except Exception as e:
                print(f"User's file could not be loaded: {e}")

        return str(default_user_file)

    ##--------------------------------------------------------------------------####

    #####--------- Button Handlers----------------------------------######
    def _reset_button_fired(self):
        """
        Handles the user clicking the 'Reset to Defaults' button.
        This will reset the 'file' trait back to its default value.
        """
        print("\n--- Resetting traits to default values ---")
        self.reset_traits(traits=['file'])
        print(f"The 'file' trait has been reset to: {self.file}")
        print("----------------------------------------\n")

    def _mod_text_fired(self):
        Path(self.file).write_text("CHANGED FILE: No longer the master copy.")
        print("Modified Selected File")

    def _load_file_fired(self):
        """
        Handles the user clicking the 'Load File' button.

        This will copy the selected text file into the repo_dir (the text repo).

        It will then set the file trait to the repo copy of the selected file.

        If chosen file name already exists, in the repo, it will spawn a warning dialog requesting user input.
        """
        print("\n--- Loading external file into repo ---")

        # --- 1. Open a dialog for the user to select a source file ---
        # This is decoupled from self.file to allow loading any file at any time.
        dialog = FileDialog(action='open', wildcard='Texts (*.txt)')

        if dialog.open() != OK:
            print("File selection cancelled by user.")
            return

        src_file = Path(dialog.path)
        repo_dir = Path(self.repo_dir)

        # --- 3. Handle case where the selected file is already in the repo ---
        # We just select it in the UI and do not need to copy anything.
        if src_file.parent == repo_dir:
            print(f"File '{src_file.name}' is already in the repo. Selecting it.")
            self.file = src_file
            return

        print("Checking for chosen file in repo...")
        dst_file = repo_dir / src_file.name

        if not dst_file.exists():
            # --- 4a. No conflict: The file doesn't exist, copy it directly.

            self._load_new_file(dst_file, src_file)

            print(f"{dst_file.name} has been copied to {src_file.name}. It was not found in the repo before.")

        else:
            # --- 4b. Conflict: File exists. Ask the user what to do. ---
            print(f"File '{dst_file.name}' already exists. Confirm Overwriting.")

            confirm_overwrite = confirm(
                parent=None,
                message=f"A file named '{dst_file.name}' already exists in "
                        "the repository. What would you like to do?",
                title="Warning: File Already Exists",
                cancel=True,
                yes_label="Overwrite",
                no_label="Save As...",
            )

            if confirm_overwrite == YES:
                # --- Overwrite the existing file ---
                print(f"User chose to overwrite '{dst_file.name}'.")

                self._load_new_file(dst_file, src_file)

            elif confirm_overwrite == NO:
                # --- Open a 'Save As' dialog to choose a new name ---
                print("User chose 'Save As...'. Opening save dialog.")

                dialog = FileDialog(action='save as',
                                    default_directory=str(repo_dir),
                                    default_filename=src_file.stem + " - Copy",
                                    wildcard='Texts (*.txt)')

                ###### Handle Save As Dialog ######################
                if dialog.open() == OK:
                    dst_file = dialog.path

                    self._load_new_file(dst_file, src_file)

                else:
                    print("Save As dialog cancelled by user.")

                ####################################################

            else:  # result == CANCEL
                print("Load operation cancelled by user.")

    #### Protected Helper methods ##############
    def _load_new_file(self, dst_file: Union[Path, str], src_file: Union[Path, str]):
        try:
            copy2(src_file, dst_file)
            self.file = dst_file
            print(f"File '{self.file}' was loaded.")
        except Exception as e:
            print(f"Error loading file: {e}")
            raise

    ##############---------------------------------------------------------------###########

    view = View(
        VGroup(
            Item(
                'file',
                id='file1',
                label="File Path",
                editor=FileEditor(filter=['Texts (*.txt)']),
            ),
            # A simple button to trigger the reset action
            UItem('reset_button'),
            UItem('mod_text'),
            UItem("load_file"),
        ),
        width=500,
        resizable=True,
    )


# Create the demo:
demo = ResetDefaultFileLoadFileDemo()

if __name__ == '__main__':
    demo.configure_traits()

