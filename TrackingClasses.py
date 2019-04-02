#!/usr/bin/env python
# -*- coding: utf-8 -*-
# TrackingClasses.py
"""
Classes mainly storing and Parameters, current state and the results of phase retrieval algorithm.

Copyright (c) 2019, Martin Stoeckl
"""
import os
import time
import xlsxwriter
from io import BytesIO
import tkinter as tk
from tkinter import messagebox
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from pyOTF import zernike
from pyOTF import utils
import bioformats_helper


class PsfandFitParameters:
    """Stores and tracks the psf and fit parameters, retrieved from the PSF file or entered by the user.

        Attributes
        ----------
        PSF parameters --> used to populate (psf_parameters : dict) for phaseretrieval_gui.PhaseRetrievalThreaded

        self.em_wavelength: int
            Central emission wavelength (set by user)
        self.numerical_aperture: double
            Numerical aperture of the objective (read from OME entry)
        self.refractive_index: double
            Refractive index of the immersion (read from OME entry or inferred from Immersion entry)
        self.xy_res: int
            Voxel size in x and y (in nm)
        self.z_res: int
            Voxel size in z (in nm)

        PSF data --> used to prepare the PSF data (psf_parameters : dict) for phaseretrieval_gui.PhaseRetrievalThreaded

        self.psf_data : ndarray (3 dim)
            The experimentally measured PSF of a subdiffractive source
        self.psf_data_prepped : ndarray (3 dim)
            The raw data prepared for the phase retrieval by pyOTF.utils.prep_data_for_PR

        Image size in x, y and z

        self.xy_size: int
            Number of pixels in x and y
        self.z_size: int
            Number of pixels in z

        Fit parameters --> kwargs (max_iters, pupil_tol, mse_tol) for phaseretrieval_gui.PhaseRetrievalThreaded

        self.max_iterations: int
            Maximum iterations for the phase retrieval algorithm
        self.pupil_tolerance: double
            Iterations are aborted if minimal pupil difference between iterations is reached
        self.mse_tolerance: double
            Iterations are aborted if minimal mse or mse difference between iterations is reached
        self.phase_tolerance: double
            Tolerance level for the phase coefficient of the zernike polynoms (affects only display)
        """
    class PsfFitParameter:
        """Parameter entries for interaction with the GUI user.

            Attributes
            ----------
            self.name: string
                Name of the attribute, used for display and reports
            self.value: tk.Var
                Value stored in tkinter Var for tracking
            self.unit: string
                unit of stored value
        """
        def __init__(self, name, value, unit):
            self.name = name
            self.value = value
            self.unit = unit

    def __init__(self):
        self.em_wavelength = self.PsfFitParameter(name='Emission wavelength', value=tk.IntVar(), unit='nm')
        self.num_aperture = self.PsfFitParameter(name='Numerical aperture', value=tk.DoubleVar(), unit='')
        self.refractive_index = self.PsfFitParameter(name='Refractive index', value=tk.DoubleVar(), unit='')
        self.xy_res = self.PsfFitParameter(name='xy-Resolution', value=tk.IntVar(), unit='nm')
        self.z_res = self.PsfFitParameter(name='z-Resolution', value=tk.IntVar(), unit='nm')

        self.psf_data = None
        self.psf_data_prepped = None
        self.xy_size = None
        self.z_size = None

        self.max_iterations = self.PsfFitParameter(name='Maximum iterations', value=tk.IntVar(name='MAX_ITER'), unit='')
        self.max_iterations.value.set(100)
        self.pupil_tolerance = self.PsfFitParameter(name='Minimal pupil function difference', value=tk.DoubleVar(),
                                                    unit='')
        self.pupil_tolerance.value.set(float(1e-8))
        self.mse_tolerance = self.PsfFitParameter(name='Minimal relative MSE difference', value=tk.DoubleVar(), unit='')
        self.mse_tolerance.value.set(float(1e-6))
        self.phase_tolerance = self.PsfFitParameter(name='Tolerable phase deviation', value=tk.DoubleVar(), unit='λ')
        self.phase_tolerance.value.set(0.5)
        self.is_initiated = False

    def read_data_and_parameters(self, PSF_file_path):
        """Read PSF file and write acquisition parameters and PSF data to attributes and sets self.is_initiated flag.

            Arguments
            ----------
            PSF_file_path: string
                Full path of the PSF file
        """
        self.is_initiated = False
        try:
            psf_info = bioformats_helper.PsfImageDataAndParameters(PSF_file_path)
        except AssertionError as pop_up_alert:
            self.pop_up_error_window(pop_up_alert)
        except Exception as pop_up_alert:
            self.pop_up_error_window(pop_up_alert, title='Invalid PSF file path')
        else:
            self.num_aperture.value.set(psf_info.numerical_aperture)
            self.refractive_index.value.set(psf_info.refractive_index)
            self.xy_res.value.set(psf_info.pixel_size_xy)
            self.z_res.value.set(psf_info.pixel_size_z)
            self.xy_size = psf_info.image_size_xy
            self.z_size = psf_info.image_size_z
            self.psf_data = psf_info.image_data
            self.psf_data_prepped = utils.prep_data_for_PR(self.psf_data, self.xy_size * 2)
            self.is_initiated = True

    def verify(self):
        """Checks whether any psf or fit parameters is zero or PSF data is not shaped correctly.

            Returns
            ----------
            bool
                True, if no zero value in the parameters and correct PSF data shape
        """
        parameters_initialized = (self.em_wavelength.value.get(),
                                  self.num_aperture.value.get(),
                                  self.refractive_index.value.get(),
                                  self.xy_res.value.get(),
                                  self.z_res.value.get(),
                                  self.max_iterations.value.get(),
                                  self.pupil_tolerance.value.get(),
                                  self.mse_tolerance.value.get(),
                                  )
        try:
            assert all(parameters_initialized), \
                'Not all PSF or Fit parameters initialized correctly.'

            assert self.psf_data.shape == (self.z_size, self.xy_size, self.xy_size), \
                'PSF data array is not shaped correctly.'

        except AssertionError as pop_up_alert:
            self.pop_up_error_window(pop_up_alert, title='Invalid PSF parameters')
            return False
        else:
            return True

    def pop_up_error_window(self, error, title='Unsuitable PSF file loaded'):
        """Creates toplevel window with error message.
        """
        messagebox.showwarning(title, str(error))


class ZernikeDecomposition:
    """Stores the results of the Zernike Polynom Decomposition.

        Attributes
        ----------
        self.zernike_names_dict : dict
            A dict mapping polynom name to polynom order (Noll)
        self.ordered_coeff_names : list
            Sorted list of polynom names in raising order
        self.zernike_polynoms : list
            List of Zernike Polynom contributions (List of ZernikePolynom)
        self.important_coeff_orders : tuple
            Tuple of orders of Zernike Polynoms which are emphasised in GUI and reports
    """
    class ZernikePolynom:
        """Zernike Polynom object, stores the results of the decomposition for each polynom.

          Attributes
          ----------
            self.order: int
                Order of the polynom (Noll)
            self.name: string
                Name of the polynom (Noll)
            self.value: double
                Value of the phase coefficient (in units of wavelength)
            self.in_tolerance: bool
                Whether value is greater or smaller the set phase tolerance (PsfandFitParameters.phase_tolerance)
        """
        def __init__(self, order, name, value, in_tolerance):
            self.order = order
            self.name = name
            self.value = value
            self.in_tolerance = in_tolerance

    def __init__(self):
        self.zernike_names_dict = zernike.noll2name
        self.ordered_coeff_names = [self.zernike_names_dict[i + 1] for i in range(len(self.zernike_names_dict))]
        self.zernike_polynoms = []
        self.important_coeff_orders = (5, 6, 7, 8, 11)
        self.initialize_polynom_list()

    def initialize_polynom_list(self):
        """Populate initial Zernike Polynom list and sort it in ascending order."""
        self.zernike_polynoms = []
        for order, name in self.zernike_names_dict.items():
            self.zernike_polynoms.append(self.ZernikePolynom(order, name, 0, None))
        self.zernike_polynoms.sort(key=lambda p: p.order)

    def get_decomposition_from_PhaseRetrieval(self, pr_results, phase_tolerance):
        """ Run Zernike Decomposition on Phase Retrieval Results, update polynom list with phase coefficients

            Arguments
            ----------
            pr_results:  phaseretrieval_gui.PhaseRetrievalResult
                Results from the phase retrieval algorithm
            phase_tolerance: double
                Tolerance level for the phase coefficient of the zernike polynoms
        """
        ordered_phase_coefficients = pr_results.zd_result.pcoefs[:len(self.ordered_coeff_names)]
        for polynom, phase_coefficient in zip(self.zernike_polynoms, ordered_phase_coefficients):
            polynom.value = phase_coefficient
            polynom.in_tolerance = (abs(phase_coefficient) < phase_tolerance)


class PrState:
    """Stores the current state of the Phase Retrieval Algorithm.

        Attributes
        ----------
        self.current_state : tk.StringVar
            Verbose tracking of the current state (used for GUI display and reports)
        self.current_iter : tk.IntVar
            Current iteration of the Phase Retrieval Algorithm
        self.current_pupil_diff : tk.DoubleVar
            Current difference between subsequent pupil functions
        self.current_mse_diff : tk.DoubleVar
            Current difference between subsequent mean square error calculations
        self.pr_finished: tk.BooleanVar

    """
    def __init__(self):
        self.current_state = tk.StringVar()
        self.current_state.set("Phase retrieval not started yet")
        self.current_iter = tk.IntVar()
        self.current_pupil_diff = tk.DoubleVar()
        self.current_mse_diff = tk.DoubleVar()
        self.pr_finished = tk.BooleanVar()
        self.pr_finished.set(False)

    def reset_state(self):
        self.current_iter.set(0)
        self.current_pupil_diff.set(0)
        self.current_mse_diff.set(0)
        self.pr_finished.set(False)


class ResultImageStreams:
    """Provides Byte streams to store the figures as .png for display and reports.

        Attributes
        ----------
        self.psf_image_stream_xy: BytesIO
            Currently diplayed xy image of the loaded PSF
        self.psf_image_stream_xz: BytesIO
            Currently diplayed xz image of the loaded PSF
        self.pr_result_image_stream: BytesIO
            Current result image (phase and magnitude) of the phase retrieval algorithm
        self.pr_fiterror_image_stream: BytesIO
            Current fitting errors (pupil function and mse difference) of the phase retrieval algorithm
        self.zd_decomposition_image_stream: BytesIO
            Current results image from the Zernike Polynom Decomposition
    """
    def __init__(self):
        self.psf_image_stream_xy = BytesIO()
        self.psf_image_stream_xz = BytesIO()
        self.pr_result_image_stream = BytesIO()
        self.pr_fiterror_image_stream = BytesIO()
        self.zd_decomposition_image_stream = BytesIO()


    def reset_image_stream(self, stream, image):
        """Resets the image stream if the image changes

            Arguments
            ----------
                stream: BytesIO
                    Internal BytesIO to reset
                image: plt.Figure
                    New matplotlib.Figure to store in the Stream
            """
        stream.truncate()
        stream.seek(0)
        image.savefig(stream, dpi=300, format='png')


class ZdResultWorkbook(xlsxwriter.Workbook):
    """Creates a .xlsx-file to store the PSF and Fit parameters and the Zernike decomposition results

        Attributes
        ----------
        save_path: string
            Full path to store the .xlsx-file
        self.psf_path: string
            Full path to the PSF-file
        self.psf_parameters: PsfandFitParameters
            Parameters of the measured PSF and the Phase Retrieval Algorithm
        self.zernike_results: ZernikeDecomposition
            Results of the Zernike Decomposition
        self.pr_state: PrState
            State of the Phase Retrieval Algorithm

    """
    def __init__(self, save_path, psf_path, psf_parameters, zernike_results, pr_state):

        super(ZdResultWorkbook, self).__init__(save_path)

        self.psf_path = psf_path
        self.psf_parameters = psf_parameters
        self.zernike_results = zernike_results
        self.pr_state = pr_state

        self.bold_format = self.add_format({'bold': True})
        self.short_number_format = self.add_format()
        self.short_number_format.set_num_format('0.00')
        self.add_entries()

    def add_entries(self):
        worksheet = self.add_worksheet('Zernike decomposition')
        worksheet.write(0, 0, self.psf_path, self.bold_format)

        worksheet.write(2, 0, 'PSF Parameters', self.bold_format)
        worksheet.write(3, 0, self.psf_parameters.em_wavelength.name + ' in nm')
        worksheet.write(3, 1, self.psf_parameters.em_wavelength.value.get())
        worksheet.write(4, 0, self.psf_parameters.num_aperture.name)
        worksheet.write(4, 1, self.psf_parameters.num_aperture.value.get())
        worksheet.write(5, 0, self.psf_parameters.refractive_index.name)
        worksheet.write(5, 1, self.psf_parameters.refractive_index.value.get())
        worksheet.write(6, 0, self.psf_parameters.xy_res.name + ' in nm')
        worksheet.write(6, 1, self.psf_parameters.xy_res.value.get())
        worksheet.write(7, 0, self.psf_parameters.z_res.name + ' in nm')
        worksheet.write(7, 1, self.psf_parameters.z_res.value.get())

        worksheet.write(2, 2, 'Phase Retrieval Parameters', self.bold_format)
        worksheet.write(3, 2, self.psf_parameters.max_iterations.name)
        worksheet.write(3, 3, self.psf_parameters.max_iterations.value.get())
        worksheet.write(4, 2, self.psf_parameters.pupil_tolerance.name)
        worksheet.write(4, 3, self.psf_parameters.pupil_tolerance.value.get())
        worksheet.write(5, 2, self.psf_parameters.mse_tolerance.name)
        worksheet.write(5, 3, self.psf_parameters.mse_tolerance.value.get())

        current_iteration_string = "Phase retrieval stopped after iteration {} out of {}.".format(
            self.pr_state.current_iter.get(), self.psf_parameters.max_iterations.value.get())
        worksheet.write(6, 2, current_iteration_string)
        pr_state_string = self.pr_state.current_state.get().replace("\n", " ")
        worksheet.write(7, 2, pr_state_string, self.bold_format)

        worksheet.write(9, 0, 'Zernike Decomposition Results', self.bold_format)
        worksheet.write(10, 0, 'Noll Order', self.bold_format)
        worksheet.write(10, 1, 'Noll Name', self.bold_format)
        worksheet.write(10, 2, 'Value', self.bold_format)

        for polynom, row in zip(self.zernike_results.zernike_polynoms,
                                range(len(self.zernike_results.zernike_polynoms))):
            worksheet.write(row + 11, 0, polynom.order)
            worksheet.write(row + 11, 1, polynom.name)
            worksheet.write(row + 11, 2, polynom.value, self.short_number_format)

        self.close()


class PdfReport:
    """Creates a .xlsx-file to store the PSF and Fit parameters and the Zernike decomposition results

            Attributes
            ----------
            save_path: string
                Full path to store the .xlsx-file
            self.psf_path: string
                Full path of the PSF-file
            self.psf_parameters: PsfandFitParameters
                Parameters of the measured PSF and the Phase Retrieval Algorithm
            self.zernike_results: ZernikeDecomposition
                Results of the Zernike Decomposition
            self.image_streams: ResultImageStreams
                ByteStreams of the .png files generated from the respective plt.Figures
            self.pr_state: PrState
                State of the Phase Retrieval Algorithm

        """
    def __init__(self, save_path, psf_path, psf_parameters, zernike_results, image_streams, pr_state):
        self.save_path = save_path
        _, self.psf_filename = os.path.split(psf_path)
        self.psf_parameters = psf_parameters
        self.zernike_results = zernike_results
        self.image_streams = image_streams
        self.pr_state = pr_state

    def create_pdf_report(self):

        def generate_psf_entry(ypos, parameter):
            xpos_name = 370
            xpos_value = 545
            xpos_unit = 550

            c.drawString(xpos_name, ypos, parameter.name)
            c.drawRightString(xpos_value, ypos, str(parameter.value.get()))
            c.drawString(xpos_unit, ypos, parameter.unit)

        #read image data from Bytestream
        psf_xy_image = ImageReader(self.image_streams.psf_image_stream_xy)
        psf_xz_image = ImageReader(self.image_streams.psf_image_stream_xz)
        pr_res_image = ImageReader(self.image_streams.pr_result_image_stream)
        pr_mse_image = ImageReader(self.image_streams.pr_fiterror_image_stream)
        zd_res_image = ImageReader(self.image_streams.zd_decomposition_image_stream)

        #initialize Canvas
        c = canvas.Canvas(self.save_path)

        #draw Headers and add PSF-filename
        c.setFont('Helvetica-Bold', 16)
        c.drawString(100, 790, "Phase retrieval analysis")
        c.setFont('Helvetica-Bold', 12)
        c.drawString(100, 760, "PSF file: ")
        c.setFont('Helvetica', 10)
        c.drawString(155, 760, self.psf_filename)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(100, 730, "PSF previews")
        c.setFont('Helvetica-Bold', 10)
        c.drawString(370, 730, "PSF & Fit parameters")

        #list PSF and PR parameters
        c.setFont('Helvetica', 10)
        generate_psf_entry(710, self.psf_parameters.em_wavelength)
        generate_psf_entry(693, self.psf_parameters.num_aperture)
        generate_psf_entry(676, self.psf_parameters.refractive_index)
        generate_psf_entry(659, self.psf_parameters.xy_res)
        generate_psf_entry(642, self.psf_parameters.z_res)
        generate_psf_entry(617, self.psf_parameters.max_iterations)
        generate_psf_entry(600, self.psf_parameters.pupil_tolerance)
        generate_psf_entry(583, self.psf_parameters.mse_tolerance)
        generate_psf_entry(566, self.psf_parameters.phase_tolerance)

        #show PSFs
        c.setFont('Helvetica', 10)
        c.drawString(100, 710, "PSF x/y")
        c.drawString(230, 710, "PSF x/z")
        c.drawImage(psf_xy_image, 100, 585, width=120, height=120, mask=None)
        c.drawImage(psf_xz_image, 230, 585, width=120, height=120, mask=None)

        #show PR Results (Results and Errors)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(100, 550, "Phase retrieval results")
        c.drawImage(pr_res_image, 100, 390, width=360, height=150, mask=None)
        c.drawImage(pr_mse_image, 100, 325, width=288, height=72, mask=None)

        #setup description, why in which iteration the PR Algorithm terminated
        c.setFont('Helvetica', 8)
        condition_strings = self.pr_state.current_state.get().split('\n')
        max_iters = self.psf_parameters.max_iterations.value.get()
        if len(condition_strings) == 1:
            condition_string = "{} after {} iterations.".format(condition_strings[0][:-1],
                                                                self.pr_state.current_iter.get())
            c.drawString(395, 340, condition_string)
        if len(condition_strings) == 2 and self.pr_state.current_iter.get() == max_iters:
            c.drawString(395, 355, condition_strings[0])
            c.drawString(395, 340, condition_strings[1])
        if len(condition_strings) == 2 and self.pr_state.current_iter.get() < max_iters:
            condition_string = "During iteration {} / {} ".format(self.pr_state.current_iter.get(),
                                                                 max_iters)
            c.drawString(395, 355, condition_string)
            c.drawString(395, 340, condition_strings[1])

        #list results of the Zernike Polynom Decomposition
        c.setFont('Helvetica-Bold', 12)
        c.drawString(100, 310, "Zernike decomposition results")
        c.drawImage(zd_res_image, 100, 60, width=240, height=240, mask=None)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(350, 285, "Zernike Polynom")
        c.drawString(520, 285, "Value / λ")

        y_pos = 265
        for polynom in self.zernike_results.zernike_polynoms:
            c.setFillColorRGB(0, 0, 0)
            if polynom.order in self.zernike_results.important_coeff_orders:
                font = 'Helvetica-Bold'
            else:
                font = 'Helvetica'
            c.setFont(font, 10)
            c.drawString(350, y_pos, polynom.name)
            if polynom.in_tolerance:
                c.setFillColorRGB(0.22, 0.67, 0.15)
            else:
                c.setFillColorRGB(0.9, 0.07, 0.07)
            string_width = c.stringWidth("{:.2f}".format(polynom.value), font, 10)
            """ string_width pos value: 19.46, neg value = 22.79, needed for right alignment"""
            c.drawString(520 + 22.79 - string_width, y_pos, "{:.2f}".format(polynom.value))
            y_pos -= 17

        #print time at the end
        generation_time = time.strftime("%d.%m.%Y - %H:%M:%S ", time.localtime())
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(100, 10, "Report generated on: " + generation_time)

        #create page and save
        c.showPage()
        c.save()


