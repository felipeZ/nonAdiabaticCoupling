from nac.common import (
    Matrix, compute_center_of_mass, retrieve_hdf5_data, search_data_in_hdf5,
    store_arrays_in_hdf5)
from os.path import join
from typing import (Dict, List)


def get_multipole_matrix(i: int, mol: List, config: Dict, multipole: str) -> Matrix:
    """
    Retrieve the `multipole` number `i` from the trajectory. Otherwise compute it.
    """
    root = join(config['project_name'], 'multipole', 'point_{}'.format(i))
    path_hdf5 = config['path_hdf5']
    path_multipole_hdf5 = join(root, multipole)
    matrix_multipole = search_multipole_in_hdf5(path_hdf5, path_multipole_hdf5, multipole)

    if matrix_multipole is None:
        matrix_multipole = compute_matrix_multipole(mol, config, multipole)

    store_arrays_in_hdf5(path_hdf5, path_multipole_hdf5, matrix_multipole)

    return matrix_multipole


def search_multipole_in_hdf5(path_hdf5: str, path_multipole_hdf5: str, multipole: str):
    """
    Search if the multipole is already store in the HDFt
    """
    if search_data_in_hdf5(path_hdf5, path_multipole_hdf5):
        print("retrieving multipole: {} from the hdf5".format(multipole))
        return retrieve_hdf5_data(path_hdf5, path_multipole_hdf5)
    else:
        print("computing multipole: {}".format(multipole))
        return None


def compute_matrix_multipole(
        mol: List, config: Dict, multipole: str) -> Matrix:
    """
    Compute the some `multipole` matrix: overlap, dipole, etc. for a given geometry `mol`.
    Compute the Multipole matrix in cartesian coordinates and
    expand it to a matrix and finally convert it to spherical coordinates.

    :returns: Matrix with entries <ψi | x y z | ψj>
    """
    path_hdf5 = config['path_hdf5']

    if multipole == 'overlap':
        matrix_multipole = None
        # rs = calcMtxOverlapP(mol, dictCGFs, runner)
        # mtx_overlap = triang2mtx(rs, n_cart_funcs)
        # matrix_multipole = transf_mtx.dot(sparse.csr_matrix.dot(mtx_overlap, transpose))

    else:
        rc = compute_center_of_mass(mol)
        exponents = {
            'dipole': [
                {'e': 1, 'f': 0, 'g': 0}, {'e': 0, 'f': 1, 'g': 0}, {'e': 0, 'f': 0, 'g': 1}],
            'quadrupole': [
                {'e': 2, 'f': 0, 'g': 0}, {'e': 0, 'f': 2, 'g': 0}, {'e': 0, 'f': 0, 'g': 2}]
        }
        matrix_multipole = None
        # mtx_integrals_triang = tuple(calcMtxMultipoleP(mol, dictCGFs, runner, rc, **kw)
        #                              for kw in exponents[multipole])
        # mtx_integrals_cart = tuple(triang2mtx(xs, n_cart_funcs)
        #                            for xs in mtx_integrals_triang)
        # matrix_multipole = np.stack(
        #     transf_mtx.dot(sparse.csr_matrix.dot(x, transpose)) for x in mtx_integrals_cart)

    return matrix_multipole