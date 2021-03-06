"""Functionality to check that the input provided by the user is valid.

Index
-----
.. currentmodule:: nanoqm.workflows.input_validation
.. autosummary:: process_input

API
---
.. autofunction:: process_input

"""
import logging
import os
import warnings
from os.path import join
from pathlib import Path
from typing import Any, Dict, Union

import yaml
from schema import SchemaError
from scm.plams import Molecule

from qmflows.settings import Settings
from qmflows.type_hints import PathLike

from ..common import DictConfig, UniqueSafeLoader
from .schemas import (schema_absorption_spectrum, schema_coop,
                      schema_cp2k_general_settings,
                      schema_derivative_couplings,
                      schema_distribute_absorption_spectrum,
                      schema_distribute_derivative_couplings,
                      schema_distribute_single_points, schema_ipr,
                      schema_single_points)
from .templates import create_settings_from_template, valence_electrons

logger = logging.getLogger(__name__)


schema_workflows = {
    'absorption_spectrum': schema_absorption_spectrum,
    'derivative_couplings': schema_derivative_couplings,
    'single_points': schema_single_points,
    'cp2k_general_settings': schema_cp2k_general_settings,
    'distribute_derivative_couplings': schema_distribute_derivative_couplings,
    'distribute_absorption_spectrum': schema_distribute_absorption_spectrum,
    'distribute_single_points': schema_distribute_single_points,
    'ipr_calculation': schema_ipr,
    'coop_calculation': schema_coop
}


def process_input(input_file: PathLike, workflow_name: str) -> DictConfig:
    """Read the `input_file` in YAML format and validate it.

    Use the corresponding `workflow_name` schema and return a nested
    dictionary with the input.

    Parameters
    ----------
    input_file
        path to the input

    Returns
    -------
    dict
        Configuration to run the given workflow
    Raises
    ------
    SchemaError
        If the input is not valid

    """
    schema = schema_workflows[workflow_name]

    with open(input_file, 'r') as f:
        dict_input = yaml.load(f.read(), Loader=UniqueSafeLoader)

    try:
        d = schema.validate(dict_input)
        return DictConfig(InputSanitizer(d).sanitize())

    except SchemaError as e:
        msg = f"There was an error in the input yaml provided:\n{e}"
        print(msg)
        raise


class InputSanitizer:
    """Class to sanitize the input."""

    def __init__(self, input_dict: Dict):
        """Set the class properties."""
        self.user_input = input_dict
        self.general = input_dict["cp2k_general_settings"]

    def sanitize(self) -> Dict:
        """Apply all the sanity check on the input."""
        self.create_settings()
        self.apply_templates()
        self.add_missing_keywords()
        self.add_executable()
        self.print_final_input()

        return self.user_input

    def create_settings(self) -> None:
        """Transform the CP2K input dict into :class:`QMFLows.Settings`."""
        self.general['cp2k_settings_main'] = Settings(self.general['cp2k_settings_main'])
        self.general['cp2k_settings_guess'] = Settings(self.general['cp2k_settings_guess'])

    def apply_templates(self) -> None:
        """Apply a template for CP2K if the user requested it."""
        for s in [
                self.general[x] for x in ('cp2k_settings_main', 'cp2k_settings_guess')]:
            val = s['specific']

            if "template" in val:
                cp2k_template = create_settings_from_template(
                    self.general, val['template'], self.user_input["path_traj_xyz"])
                # remove template
                del s['specific']['template']

                # Add other keywords
                s['specific'] = cp2k_template.overlay(s['specific'])

    def add_executable(self) -> None:
        """Add executable to the job settings."""
        self.general['cp2k_settings_main']['executable'] = self.general['executable']
        self.general['cp2k_settings_guess']['executable'] = self.general['executable']

    def add_missing_keywords(self) -> None:
        """Add missing input data using the defaults."""
        # Add the `added_mos` and `mo_index_range` keywords
        if self.user_input.get('nHOMO') is None:
            self.user_input["nHOMO"] = self.compute_homo_index()

        # Added_mos keyword
        if self.user_input.get('compute_orbitals'):
            self.add_mo_index_range()
        else:
            logger.info("Orbitals are neither print nor store!")

        # Add restart point provided by the user
        self.add_restart_point()

        # Add basis sets
        self.add_basis()

        # add cell parameters
        self.add_cell_parameters()

        # Add Periodic properties
        self.add_periodic()

        # Add charge
        self.add_charge()

        # Add multiplicity
        self.add_multiplicity()

    def compute_homo_index(self) -> int:
        """Compute the HOMO index."""
        basis = self.general['basis']
        charge = self.general['charge']
        mol = Molecule(self.user_input["path_traj_xyz"], 'xyz')

        number_of_electrons = sum(
            valence_electrons['-'.join((at.symbol, basis))] for at in mol.atoms)

        # Correct for total charge of the system
        number_of_electrons = number_of_electrons - charge

        if (number_of_electrons % 2) != 0:
            warnings.warn(
                "Unpair number of electrons detected when computing the HOMO")

        return (number_of_electrons // 2) + (number_of_electrons % 2)

    def add_basis(self) -> None:
        """Add path to the basis and potential."""
        setts = [self.general[p] for p in ['cp2k_settings_main', 'cp2k_settings_guess']]

        # add basis and potential path
        if self.general["path_basis"] is not None:
            logger.info("path to basis added to cp2k settings")
            for x in setts:
                x.basis = self.general['basis']
                x.potential = self.general['potential']
                x.specific.cp2k.force_eval.dft.potential_file_name = os.path.abspath(
                    join(self.general['path_basis'], "GTH_POTENTIALS"))

                # Choose the file basis to use
                self.select_basis_file(x)

    def select_basis_file(self, sett: Settings) -> None:
        """Choose the right basis set based on the potential and basis name."""
        dft = sett.specific.cp2k.force_eval.dft

        dft["basis_set_file_name"] = [os.path.abspath(
            join(self.general['path_basis'], "BASIS_MOLOPT"))]

        if dft.xc.get("xc_functional pbe") is None:
            # USE ADMM
            dft["basis_set_file_name"].append(os.path.abspath(
                join(self.general['path_basis'], "BASIS_ADMM_MOLOPT")))
            dft["basis_set_file_name"].append(os.path.abspath(
                join(self.general['path_basis'], "BASIS_ADMM")))

    def add_cell_parameters(self) -> None:
        """Add the Unit cell information to both the main and the guess settings."""
        # Search for a file containing the cell parameters
        for s in (self.general[p] for p in [
                'cp2k_settings_main',
                'cp2k_settings_guess']):
            if self.general["file_cell_parameters"] is None:
                s.cell_parameters = self.general['cell_parameters']
                s.cell_angles = None
            else:
                s.cell_parameters = None
            s.cell_angles = None

    def add_periodic(self) -> None:
        """Add the keyword for the periodicity of the system."""
        for s in (
            self.general[p] for p in [
                'cp2k_settings_main',
                'cp2k_settings_guess']):
            s.specific.cp2k.force_eval.subsys.cell.periodic = self.general['periodic']

    def add_charge(self) -> None:
        """Add the keyword for the charge of the system."""
        for s in (
            self.general[p] for p in [
                'cp2k_settings_main',
                'cp2k_settings_guess']):
            s.specific.cp2k.force_eval.dft.charge = self.general['charge']

    def add_multiplicity(self) -> None:
        """Add the keyword for the multiplicity of the system only if greater than 1."""
        if self.general['multiplicity'] > 1:
            for s in (
                    self.general[p] for p in ('cp2k_settings_main', 'cp2k_settings_guess')):
                s.specific.cp2k.force_eval.dft.multiplicity = self.general['multiplicity']
                s.specific.cp2k.force_eval.dft.uks = ""

    def add_restart_point(self) -> None:
        """Add a restart file if the user provided it."""
        guess = self.general['cp2k_settings_guess']
        wfn = self.general['wfn_restart_file_name']
        if wfn is not None and wfn:
            dft = guess.specific.cp2k.force_eval.dft
            dft.wfn_restart_file_name = Path(wfn).absolute().as_posix()

    def add_mo_index_range(self) -> None:
        """Compute the MO range to print."""
        active_space = self.user_input["active_space"]
        nHOMO = self.user_input["nHOMO"]
        mo_index_range = nHOMO - active_space[0], nHOMO + active_space[1]
        self.user_input["mo_index_range"] = mo_index_range

        # mo_index_range keyword
        cp2k_main = self.general['cp2k_settings_main']
        dft_main_print = cp2k_main.specific.cp2k.force_eval.dft.print
        dft_main_print.mo.mo_index_range = "{} {}".format(
            mo_index_range[0] + 1, mo_index_range[1])

        # added_mos
        cp2k_main.specific.cp2k.force_eval.dft.scf.added_mos = mo_index_range[1] - nHOMO

        # Add section to Print the orbitals
        mo = cp2k_main.specific.cp2k.force_eval.dft.print.mo
        mo.add_last = "numeric"
        mo.each.qs_scf = 0
        mo.eigenvalues = ""
        mo.eigenvectors = ""
        mo.ndigits = 36

    def print_final_input(self) -> None:
        """Print the input after post-processing."""
        xs = self.user_input.copy()

        for k, v in self.user_input.items():
            xs[k] = recursive_traverse(v)

        with open("input_parameters.yml", "w") as f:
            yaml.dump(xs, f, indent=4)


def recursive_traverse(val: Union[Dict, Settings, Any]) -> Union[Dict, Settings, Any]:
    """Check if the value of a key is a Settings instance a transform it to plain dict."""
    if isinstance(val, dict):
        if isinstance(val, Settings):
            return val.as_dict()
        else:
            return {k: recursive_traverse(v) for k, v in val.items()}
    else:
        return val
