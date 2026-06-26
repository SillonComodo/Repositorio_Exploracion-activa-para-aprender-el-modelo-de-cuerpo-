import os
import sys
import subprocess

# Find explauto install location using pip show
result = subprocess.check_output(["pip", "show", "explauto"]).decode("utf-8")
location = None
for line in result.split("\n"):
    if line.startswith("Location:"):
        location = line.split(":", 1)[1].strip()
        break

if not location:
    print("Error: Could not find explauto installation location.")
    sys.exit(1)

explauto_dir = os.path.join(location, "explauto")
print("Found explauto at: " + explauto_dir)

# 1. Patch tree.py
tree_path = os.path.join(explauto_dir, 'interest_model', 'tree.py')
print("Patching tree.py at: " + tree_path)
with open(tree_path, 'r') as f:
    tree_content = f.read()

target_tree = """        else:
            self.lower.plot_grid(ax, progress_colors, progress_max, depth - 1, plot_dims)
            self.greater.plot_grid(ax, progress_colors, progress_max, depth - 1, plot_dims)"""

replacement_tree = """        else:
            self.lower.plot_grid(ax, progress_colors, progress_max, depth - 1, plot_dims)
            self.greater.plot_grid(ax, progress_colors, progress_max, depth - 1, plot_dims)

    def plot_to_file(self, fh, progress_max=1., depth=10, plot_dims=[0,1]):
        if self.leafnode or depth == 0:
            mins = self.bounds_x[0,plot_dims]
            maxs = self.bounds_x[1,plot_dims]
            prog_min = 0.
            p = (self.max_leaf_progress - prog_min) / (progress_max - prog_min) if progress_max > prog_min else 0
            fh.write(str(mins[0]) + ' ' + str(mins[1]) + ' ' + str(maxs[0]) + ' ' + str(maxs[1]) + ' ' + str(p) + '\\n')
        else:
            self.lower.plot_to_file(fh, progress_max, depth - 1, plot_dims)
            self.greater.plot_to_file(fh, progress_max, depth - 1, plot_dims)"""

if target_tree in tree_content:
    tree_content = tree_content.replace(target_tree, replacement_tree)
    with open(tree_path, 'w') as f:
        f.write(tree_content)
    print("Successfully patched tree.py")
elif "def plot_to_file" in tree_content:
    print("tree.py is already patched")
else:
    print("Warning: Target for tree.py not found")

# 2. Patch cma.py
cma_path = os.path.join(explauto_dir, 'sensorimotor_model', 'inverse', 'cma.py')
print("Patching cma.py at: " + cma_path)
with open(cma_path, 'r') as f:
    cma_content = f.read()

target_cma = """    def has_bounds(self):
        \"\"\"return True, if any variable is bounded\"\"\"
        bounds = self.bounds
        if bounds in (None, [None, None]):
            return False"""

replacement_cma = """    def has_bounds(self):
        \"\"\"return True, if any variable is bounded\"\"\"
        bounds = self.bounds
        #if bounds in (None, [None, None]):
        #    return False"""

if target_cma in cma_content:
    cma_content = cma_content.replace(target_cma, replacement_cma)
    with open(cma_path, 'w') as f:
        f.write(cma_content)
    print("Successfully patched cma.py")
elif "#if bounds in (None, [None, None]):" in cma_content:
    print("cma.py is already patched")
else:
    print("Warning: Target for cma.py not found")

# 3. Install adaptive_linear_interest.py
# ----------------------------------------
# The source file is placed by the Dockerfile at /adaptive_linear_interest.py
import shutil

alim_src  = '/adaptive_linear_interest.py'
alim_dest = os.path.join(explauto_dir, 'interest_model', 'adaptive_linear_interest.py')
print("Installing adaptive_linear_interest.py to: " + alim_dest)

if os.path.exists(alim_src):
    shutil.copyfile(alim_src, alim_dest)
    print("Successfully copied adaptive_linear_interest.py")
else:
    print("Warning: Source file not found at " + alim_src)

# 4. Register adaptive_linear in interest_model/__init__.py
# ----------------------------------------------------------
init_path = os.path.join(explauto_dir, 'interest_model', '__init__.py')
print("Patching interest_model/__init__.py at: " + init_path)
with open(init_path, 'r') as f:
    init_content = f.read()

target_init = "for mod_name in ['random', 'gmm_progress', 'discrete_progress', 'tree']:"
replacement_init = "for mod_name in ['random', 'gmm_progress', 'discrete_progress', 'tree', 'adaptive_linear_interest']:"

if target_init in init_content:
    init_content = init_content.replace(target_init, replacement_init)
    with open(init_path, 'w') as f:
        f.write(init_content)
    print("Successfully patched interest_model/__init__.py")
elif 'adaptive_linear_interest' in init_content:
    print("interest_model/__init__.py is already patched")
else:
    print("Warning: Target for __init__.py not found")

