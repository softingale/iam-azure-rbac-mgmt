#!/usr/bin/env python
# Validates if files have proper YAML and schemas

import sys
import os
import yaml
import tempfile
import re
from schema import Schema, And, Optional, SchemaError, Regex, Or

# Global constants and variables
Red = "\033[1;31m"
Yel = "\033m[1;33m"
Grn = "\033[1;32m"
Rst = "\033[0m"
temp_dir = ""
status_file_path = ""
DEBUG = False
ENCOUNTERED_ERROR = False
allowed_environments = ["englab", "qa", "dev", "pat", "prod"]
# Note: Hyphen is escaped, and there's a space also
valid_name_pattern = r'^[a-zA-Z][a-zA-Z0-9\- _]*$' # Note: Hyphen is escaped, and there's a space also
allowed_api_permissions_types = ["Delegated", "Application"]
p = os.getcwd()
service_list = [name for name in os.listdir(p) if (
    os.path.isdir(os.path.join(p, name)) and not name.startswith(".git"))]
service_list = service_list + ["gcpsa", "appsp"]

# === GLOBAL SCHEMA DEFINITIONS ===
rbac_definition_schema = Schema({
    "roleName": And(str, Regex(r'^[a-zA-Z][a-zA-Z0-9\- _]*$')),
    "description": str,
    "assignableScopes": [str],
    "permissions": [
        {
            "actions": [str],
            "notActions": [str],
            "dataActions": [str],
            "notDataActions": [str]
        }
    ]
})

repo_structure_schema = Schema({
    "dev": {
        "assignments": Or([], None),
        "definitions": Or([], None)
    },
    "pat": {
        "assignments": Or([], None),
        "definitions": Or([], None)
    },
    "prod": {
        "assignments": Or([], None),
        "definitions": Or([], None)
    }
})

# rbac_assignment_schema = Schema({
# })

# ==== FUNCTIONS ===


def die(msg):
    print(msg)
    sys.exit(1)


def write_error_status(status_file_path):
    """Writes 'error' to the specified validation status file."""
    with open(status_file_path, "w") as status_file:
        status_file.write("error")


def validate_filename(filename):
    """
    Validate the filename against the specified rules.
    """
    # Rule 1: Filename must start with 'td-
    if not filename.startswith("td-"):
        return False, f"Filename '{filename}' must start with 'td-'"
    
    # Rule 2: Filename must end with '.yaml' or '.yml'
    if not (filename.endswith(".yaml") or (filename.endswith(".yml"))):
        return False, f"Filename '{filename} must end with '.yaml' or '.yml'"

    # Rule 3: Filename must not contain any number or special characters (except for hyphens -)
    name_part = filename[3:-5] if filename.endswith(".yaml") else filename[3:-4]
    if any(not (char.isalpha() or char== '-') for char in name_part):
        return False, f"Filename '{filename}' must not contain numbers or special characters (except for hyphens -)"
    
    return True, ""



def get_folder_structure(base_dir):
    structure = {}
    for item in os.listdir(base_dir):
        if item.startswith('.'):
            continue
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            sub_structure = get_folder_structure(item_path)
            structure[item] = sub_structure if sub_structure else []
        else:
            parent_folder = os.path.basename(os.path.dirname(item_path))
            if parent_folder in ["assignments", "definitions"] and item.lower().endswith((".yaml", ".yml")):

                # Validate the filename
                is_valid, error_msg = validate_filename(item)
                if not is_valid:
                    print(f"{Red}Error: {error_msg}{Rst}")
                    sys.exit(1)
            else:
                print(f"{Red}Error: Unexpected file found: {item_path}{Rst}")
                print(f"{Yel}Only YAML files are allowed in 'assignments' and 'definitions' folders.{Rst}")
                sys.exit(1)
    return structure



def validate_repo_structure(base_dir, repo_schema):
    global ENCOUNTERED_ERROR, status_file_path
    actual_structure = get_folder_structure(base_dir)
    print(f"Actual folder structure: {actual_structure}")
    print(f"Contents of base_dir: {os.listdir(base_dir)}")
    try:
        repo_schema.validate(actual_structure)
        print(f"{Grn}PASS{Rst}: Repository folder structure is valid.")
    except SchemaError as e:
        if not ENCOUNTERED_ERROR:
            print(f"{Red}FAILURE{Rst}")
            ENCOUNTERED_ERROR = True
            write_error_status(status_file_path)
        print(f"{Rst}Error: Repository forlder structure validation failed:\n{e}{Rst}")


def validate_rbac_definition(data, rbac_schema):
    global ENCOUNTERED_ERROR, status_file_path
    try:
        rbac_schema.validate(data)
        print(f"{Grn}PASS{Rst}: RBAC definition is valid.")
    except SchemaError as e:
        if not ENCOUNTERED_ERROR:
            print(f"{Red}FAILURE{Rst}")


def get_yaml_files(base_dir):
    skip_dir = "Archived"
    yaml_files = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d != skip_dir]
        for file in files:
            file_path = os.path.join(root, file)
            if file_path.endswith(os.path.join(".github", "workflows", "validate_control_files.yml")):
                continue
            if file.lower().endswith(".yml") or file.lower().endswith(".yaml"):
                yaml_files.append(file_path)
    with tempfile.NamedTemporaryFile(mode="w", dir=temp_dir, delete=False) as temp_file:
        for file_path in yaml_files:
            temp_file.write(file_path + "\n")
        return temp_file.name

def validate(file_path, this_schema):
    global ENCOUNTERED_ERROR, status_file_path
    try:
        with open(file_path, 'r') as stream:
            data = yaml.safe_load(stream)
            this_schema.validate(data)
    except yaml.YAMLError as e:
        if not ENCOUNTERED_ERROR:
            print(f"{Red}FAILURE{Rst}")
            ENCOUNTERED_ERROR = True
            write_error_status(status_file_path)
        msg = f"==> Error: YAML parsing error:\n{e}"
        print(msg)

    except SchemaError as e:
        if not ENCOUNTERED_ERROR:
            print(f"{Red}FAILURE{Rst}")
            ENCOUNTERED_ERROR = True
            write_error_status(status_file_path)
        msg = f"===> Error: Schema validation error:\n{e}"
        print(msg)

    if not ENCOUNTERED_ERROR:
        print(f"{Grn}PASS{Rst}")



def validate_file(file_path):
    global ENCOUNTERED_ERROR, status_file_path
    print(f"ENCOUNTERED_ERROR: {ENCOUNTERED_ERROR}")
    colorized_msg = f"==> Validating: {Yel}{file_path}{Rst} "
    print(colorized_msg.ljust(120), end="")

    folder, file_name = os.path.split(file_path)
    # Note this is needed to avoid the getting the full path
    folder_name = os.path.basename(folder)
    #  parts = file_name.splie('-')
    parts = re.split(r'[-_]', file_name)
    file_prefix = parts[0]

    if file_prefix != "td":
        if not ENCOUNTERED_ERROR:
            print(f"{Red}FAILURE{Rst}")
            ENCOUNTERED_ERROR = True
            write_error_status(status_file_path)

        msg = f"===> Error: Filename prefix\n'{file_prefix}' must start with 'td-'."
        print(msg)
    
    # ASSUME role permissions file is the only option remaining
    validate(file_path, rbac_definition_schema)
    # Other optional schema type checks can be added here...

# ===   MAIN   ===


def main():
    global temp_dir, status_file_path

    temp_dir = tempfile.mkdtemp(prefix="validation_temp_", dir=tempfile.gettempdir())

    
    if len(sys.argv) != 2:
        die(f"{Red}Usage{Rst}: python3 .github/validate_control_files.py [-d] | <files_list.txt>")

    
    if sys.argv[1] == "-d":
        # For optional local debugging with '-d' arg, to then check ALL qualifying repo files
        DEBUG = True
        
        # We only care to validate specfiles under infrastructure
        files_list_path = get_yaml_files("infrastructure/")

        with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as temp_status:
            status_file_path = temp_status.name
    else:
        files_list_path = sys.argv[1]
        status_file_path = os.getenv("VALIDATION_STATUS")
        if not status_file_path:
            die(f"{Red}Error. VALIDATION_STATUS environment variable is not set.")

    if not os.path.isfile(files_list_path):
        die(f"Error: {Red}{files_list_path}:{Rst} is not a valid file.")

    # Validate repository folder structure
    validate_repo_structure("infrastructure/", repo_structure_schema)

    # with open(files_list_path, "r") as files_list:
    #     files_paths = files_list.read().strip().split('\n')
    #     if not files_paths or files_paths == ['']:
    #         die(f"File {Red}{files_list_path}{Rst} is empty. No YAML files to validate.")
    #     for f in files_paths:
    #         if ("appconfig" not in f):
    #             validate_file(f)
    #         ENCOUNTERED_ERROR = False # Reset for next check during DEBUG run

    if sys.argv[1] == "-d":
        os.remove(status_file_path)
        os.remove(files_list_path)
        os.rmdir(temp_dir)

if __name__ == "__main__":
    main()