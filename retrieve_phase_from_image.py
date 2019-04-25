import os
import time
import copy

import argparse
import javabridge
import bioformats

import bioformats_helper
from TrackingClasses import ZdResultWorkbook, ZernikeDecomposition

from pyOTF import phaseretrieval_gui
from pyOTF import utils


class PrState:
    """ Stores the current state of the Phase Retrieval Algorithm. Emulates TrackingClasses.PrState
        without using tkinter Vars.

           Attributes
           ----------
           self.current_state : Variable
               Verbose tracking of the current state (used for GUI display and reports)
           self.current_iter : Variable
               Current iteration of the Phase Retrieval Algorithm
           self.current_pupil_diff : Variable
               Current difference between subsequent pupil functions
           self.current_mse_diff : Variable
               Current difference between subsequent mean square error calculations
           self.pr_finished: Variable
    """
    class Variable:
        """ Needed to emulate tk.Var behavior. """
        def __init__(self, value=None):
            self._value = value

        def get(self):
            return self._value

        def set(self, new_value):
            self._value = new_value

    def __init__(self):
        self.current_state = self.Variable("Phase retrieval not started yet")
        self.current_iter = self.Variable(0)
        self.current_pupil_diff = self.Variable(0)
        self.current_mse_diff = self.Variable(0)
        self.pr_finished = self.Variable(False)

    def reset_state(self):
        self.current_iter.set(0)
        self.current_pupil_diff.set(0)
        self.current_mse_diff.set(0)
        self.pr_finished.set(False)


def retrieve_pupil_phase():
    # Generate help and define parameters
    argument_parser = argparse.ArgumentParser(description='Retrieve the complex pupil function from a PSF by a '
                                                          'Phase Retrieval algorithm')
    argument_parser.add_argument("psf_file_path", type=str, help='PSF for analysis, OME-TIFF or bioformats supported')
    argument_parser.add_argument("em_wl", type=int, help='Central emission wavelength in nm')
    argument_parser.add_argument("--refr_index", type=float, help='Sample refractive index')
    argument_parser.add_argument("--num_aper", type=float, help='Numerical aperture of the objective')
    argument_parser.add_argument("--iters", type=int, help='Max number of PR iterations', default=100)
    argument_parser.add_argument("--pupil_diff", type=float, help='Stop PR at this relative pupil function difference',
                                 default=1e-8)
    argument_parser.add_argument("--mse_diff", type=float, help='Stop PR at this relative MSE', default=1e-6)

    arguments = argument_parser.parse_args()

    # Set_file_path
    psf_dir, psf_name = os.path.split(arguments.psf_file_path)

    # retrieve PSF parameters and PSF data from file
    javabridge.start_vm(class_path=bioformats.JARS)
    psf_parameters_data = bioformats_helper.PsfImageDataAndParameters(os.path.join(arguments.psf_file_path))
    javabridge.kill_vm()

    # Check if entered parameters are valid...
    assert arguments.em_wl > 0, "Emission wavelength must be greater than zero."
    assert arguments.refr_index is None or arguments.refr_index > 0, "Refractive index must be greater than zero."
    assert arguments.num_aper is None or arguments.num_aper > 0, "Numerical aperture must be greater than zero."
    assert arguments.iters is None or arguments.iters > 0, "Iterations must be greater than zero."
    assert arguments.pupil_diff is None or arguments.pupil_diff > 0, "Pupil function difference must be " \
                                                                     "greater than zero."
    assert arguments.mse_diff is None or arguments.mse_diff > 0, "MSE difference must be greater than zero."

    # ... and if all needed parameters are there.
    assert any((arguments.refr_index, psf_parameters_data.refractive_index)), "Please provide a value " \
                                                                              "for the refractive index."
    assert any((arguments.num_aper, psf_parameters_data.numerical_aperture)), "Please provide a value "\
                                                                              "for the numerical aperture."

    # prep psf data
    psf_data = psf_parameters_data.image_data
    psf_data_prepped = utils.prep_data_for_PR(psf_data, psf_parameters_data.image_size_xy * 2)

    # set up model params
    final_na = arguments.num_aper if arguments.num_aper is not None else psf_parameters_data.numerical_aperture
    final_ri = arguments.refr_index if arguments.refr_index is not None else psf_parameters_data.refractive_index

    psf_params = dict(wl=arguments.em_wl,
                      na=final_na,
                      ni=final_ri,
                      res=psf_parameters_data.pixel_size_xy,
                      zres=psf_parameters_data.pixel_size_z
                      )
    # make a copy which is not changed by phaseretrieval_gui.PhaseRetrievalThreaded
    psf_params_copy = copy.copy(psf_params)

    pr_params = dict(max_iters=arguments.iters,
                     pupil_tol=arguments.pupil_diff,
                     mse_tol=arguments.mse_diff
                     )

    # Instantiate the class tracking the state of the Phase Retrieval Algorithm
    phase_retrieval_state = PrState()

    # Instantiate the class tracking the Phase Retrieval Algorithm results
    phase_retrieval_results = phaseretrieval_gui.PhaseRetrievalResult()

    # Instantiate the class tracking the Zernike Decomposition results
    zernike_results = ZernikeDecomposition()

    pr_start = time.time()
    print("Starting phase retrieval")

    # Initialize the Phase Retrieval Thread and start it
    phase_retrieval_thread = phaseretrieval_gui.PhaseRetrievalThreaded(psf_data_prepped,
                                                                       psf_params,
                                                                       phase_retrieval_state,
                                                                       phase_retrieval_results,
                                                                       **pr_params,
                                                                       )
    phase_retrieval_thread.daemon = True
    phase_retrieval_thread.start()

    # Follow progress
    old_iteration = 0
    while phase_retrieval_thread.is_alive():
        current_iteration = phase_retrieval_state.current_iter.get()
        if current_iteration > old_iteration:
            print('Current iteration: {}/{}, Current pupil function diff: {:.2E}, Current mse diff: {:.2E}'.
                  format(
                        phase_retrieval_state.current_iter.get(),
                        arguments.iters,
                        phase_retrieval_state.current_pupil_diff.get(),
                        phase_retrieval_state.current_mse_diff.get()
                        )
            )
        time.sleep(0.25)
        old_iteration = copy.copy(current_iteration)
    print("It took {} seconds to retrieve the pupil function".format(time.time() - pr_start))
    print(phase_retrieval_state.current_state.get())

    # plot
    results, _ = phase_retrieval_results.plot()
    result_name = os.path.splitext(psf_name)[0] + '_pr_results.png'
    results.savefig(os.path.join(psf_dir, result_name))

    convergence, _ = phase_retrieval_results.plot_convergence()
    convergence_name = os.path.splitext(psf_name)[0] + '_pr_convergence.png'
    convergence.savefig(os.path.join(psf_dir, convergence_name))

    # fit to zernikes
    zd_start = time.time()
    print("Starting zernike decomposition")
    phase_retrieval_results.fit_to_zernikes(120)
    print("It took {} seconds to fit 120 Zernikes".format(time.time() - zd_start))

    zernike, _ = phase_retrieval_results.zd_result.plot_named_coefs()
    zernike_name = os.path.splitext(psf_name)[0] + '_zd_results.png'
    zernike.savefig(os.path.join(psf_dir, zernike_name))


    zernike_results.decomposition_from_phase_retrieval(phase_retrieval_results, 0.5)
    phase_coeff_name = os.path.splitext(psf_name)[0] + '_zd_results.xlsx'
    phase_coeff_path = os.path.join(psf_dir, phase_coeff_name)

    ZdResultWorkbook(phase_coeff_path,
                     arguments.psf_file_path,
                     zernike_results,
                     phase_retrieval_state,
                     psf_param_dict=psf_params_copy,
                     fit_param_dict=pr_params,
                    )

if __name__ == "__main__":
    retrieve_pupil_phase()

