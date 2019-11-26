from nac.workflows.input_validation import process_input
from nac.workflows.workflow_coop import workflow_crystal_orbital_overlap_population
from os.path import join

import pkg_resources as pkg
import os
import sys

# Environment data
file_path = pkg.resource_filename('nac', '')
root = os.path.split(file_path)[0]

def test_workflow_coop(tmp_path):
    file_path = join(root, 'test/test_files/input_test_coop.yml')
    config = process_input(file_path, 'coop_calculation')
    print("config: ", config)
    try:
        workflow_crystal_orbital_overlap_population(config)
    except BaseException:
        print("scratch_path: ", tmp_path)
        print("Unexpected error:", sys.exc_info()[0])
        raise