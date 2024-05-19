import os
import sys
import shutil


def main(local_path):
    print("Checking if executable was built...")
    if os.path.exists(os.path.join(local_path, "dist", "ChannelExtract")):
        print("Executable built successfully")

        # Determine the application directory based on the operating system
        if sys.platform == "darwin":
            app_dir = "/Applications"
        elif sys.platform == "win32":
            app_dir = os.path.join(os.environ["PROGRAMFILES"], "ChannelExtract")
        else:
            raise Exception("Unsupported operating system")

        # Remove the existing application in the Applications folder if it exists
        old_app_path = os.path.join(app_dir, "ChannelExtract.app")
        if os.path.exists(old_app_path):
            shutil.rmtree(old_app_path)

        # Move the newly built application to the Applications folder
        new_app_path = os.path.join(local_path, "dist", "ChannelExtract.app")
        shutil.move(new_app_path, app_dir)
        print("Application moved to the Applications folder")


if __name__ == "__main__":
    local_path = sys.argv[1]
    main(local_path)
