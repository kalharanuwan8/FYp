import scipy.io as sio
import os
import sys

# Define the absolute path from the user's snippet
path = r"D:\uni\6th sem\IRP\distraction model\distraction_project\data\raw\mpiigaze\MPIIGaze\Data\Normalized\p00\day01.mat"

print(f"Checking path: {path}")

if not os.path.exists(path):
    print("Error: File not found at the specified path.")
    # Try finding it relative to project root just in case
    rel_path = r"data\raw\mpiigaze\MPIIGaze\Data\Normalized\p00\day01.mat"
    if os.path.exists(rel_path):
        print(f"Found file at relative path: {rel_path}")
        path = rel_path
    else:
        print("Could not find the file anywhere.")
        sys.exit(1)

try:
    print("Loading mat file...")
    m = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    print("Keys found:", m.keys())
    
    if "data" in m:
        d = m["data"]
        print(f"Type of 'data': {type(d)}")
        print("has left:", hasattr(d, "left"))
        print("has right:", hasattr(d, "right"))
        
        if hasattr(d, "right"):
             # inspect right eye data structure
             right_eye = d.right
             print(f"Right eye object: {right_eye}")
             # try to access fields
             try:
                 print("Right eye fields:", right_eye._fieldnames)
             except AttributeError:
                 print("Right eye does not have _fieldnames attribute. Dir:", dir(right_eye))
    else:
        print("'data' key not found in mat file.")

except Exception as e:
    print(f"An error occurred during loading: {e}")
