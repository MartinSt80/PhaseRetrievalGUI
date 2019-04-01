# coding: utf-8

import os
import time
import xlsxwriter
from ctypes import *
from io import BytesIO
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import javabridge
import bioformats
import bioformats_helper

from pyOTF import phaseretrieval_gui
from pyOTF import utils
from pyOTF import zernike


class PsfParameters:

    class PsfFitParameter:
            def __init__(self, name, value, unit, initiated):
                self.name = name
                self.value = value
                self.unit = unit
                self.initiated = initiated

    def __init__(self, main_app):

        self.main_app = main_app

        self.em_wavelength = self.PsfFitParameter(name='Emission wavelength', value=tk.IntVar(), unit='nm',
                                                  initiated=False)
        self.num_aperture = self.PsfFitParameter(name='Numerical aperture', value=tk.DoubleVar(), unit='',
                                                 initiated=False)
        self.refractive_index = self.PsfFitParameter(name='Refractive index', value=tk.DoubleVar(), unit='',
                                                     initiated=False)
        self.xy_res = self.PsfFitParameter(name='xy-Resolution', value=tk.IntVar(), unit='nm',
                                           initiated=False)
        self.z_res = self.PsfFitParameter(name='z-Resolution', value=tk.IntVar(), unit='nm',
                                          initiated=False)
        self.is_initiated = False
        self.psf_data = None
        self.xy_size = None
        self.z_size = None

        self.max_iterations = self.PsfFitParameter(name='Maximum iterations', value=tk.IntVar(name='MAX_ITER'), unit='',
                                                   initiated=True)
        self.max_iterations.value.set(200)
        self.pupil_tolerance = self.PsfFitParameter(name='Minimal pupil function difference', value=tk.DoubleVar(), unit='',
                                                    initiated=True)
        self.pupil_tolerance.value.set(float(1e-8))
        self.mse_tolerance = self.PsfFitParameter(name='Minimal relative MSE difference', value=tk.DoubleVar(), unit='',
                                                  initiated=True)
        self.mse_tolerance.value.set(float(1e-8))
        self.phase_tolerance = self.PsfFitParameter(name='Tolerable phase deviation', value=tk.DoubleVar(), unit='λ',
                                                    initiated=True)
        self.phase_tolerance.value.set(0.5)

    def read_data_and_parameters(self):
        try:
            psf_info = bioformats_helper.PsfImageDataAndParameters(self.main_app.psf_file.get())
        except AssertionError as pop_up_alert:
            self.pop_up_error_window(pop_up_alert)
        except Exception as pop_up_alert:
            self.pop_up_error_window(pop_up_alert, title='Invalid PSF file path')
        else:
            self.num_aperture.value.set(psf_info.numerical_aperture)
            self.num_aperture.initiated = True
            self.refractive_index.value.set(psf_info.refractive_index)
            self.refractive_index.initiated = True
            self.xy_res.value.set(psf_info.pixel_size_xy)
            self.xy_res.initiated = True
            self.z_res.value.set(psf_info.pixel_size_z)
            self.z_res.initiated = True
            self.xy_size = psf_info.image_size_xy
            self.z_size = psf_info.image_size_z
            self.psf_data = psf_info.image_data
            self.is_initiated = True

    def verify(self):

        parameters_initialized = (self.em_wavelength.value.get(),
                                   self.num_aperture.value.get(),
                                   self.refractive_index.value.get(),
                                   self.xy_res.value.get(),
                                   self.z_res.value.get(),
                                   )
        try:
            assert all(parameters_initialized), \
                'Not all PSF parameters initialized correctly.'

            assert self.psf_data.shape == (self.z_size, self.xy_size, self.xy_size), \
                'PSF data array is not shaped correctly.'

        except AssertionError as pop_up_alert:
            self.pop_up_error_window(pop_up_alert, title='Invalid PSF parameters')
            return False

        else:
            return True

    def pop_up_error_window(self, error, title='Unsuitable PSF file loaded'):
       messagebox.showwarning(title, str(error))

class ZernikeDecomposition:

    class ZernikePolynom:

        def __init__(self, order, name, value, in_tolerance):
            self.order = order
            self.name = name
            self.value = value
            self.in_tolerance = in_tolerance


    def __init__(self, main_app):
        self.main_app = main_app
        self.zernike_names_dict = zernike.noll2name
        self.ordered_coeff_names = [self.zernike_names_dict[i + 1] for i in range(len(self.zernike_names_dict))]
        self.zernike_polynoms = []
        self.important_coeff_orders = [5, 6, 7, 8, 11]
        self.initialize_polynom_list()

    def initialize_polynom_list(self):
        self.zernike_polynoms = []
        for order, name in self.zernike_names_dict.items():
            temp_zp = self.ZernikePolynom(order, name, 0, None)
            self.zernike_polynoms.append(temp_zp)
        self.zernike_polynoms.sort(key=lambda p: p.order)

    def get_decomposition_from_PhaseRetrieval(self):
        ordered_phase_coefficients = self.main_app.phase_retrieval_results.zd_result.pcoefs[:len(self.ordered_coeff_names)]
        for polynom, phase_coefficient in zip(self.zernike_polynoms, ordered_phase_coefficients):
            polynom.value = phase_coefficient
            if abs(phase_coefficient) < self.main_app.psf_parameters.phase_tolerance.value.get():
                polynom.in_tolerance = True
            else:
                polynom.in_tolerance = False


class ResultImageStreams:

    def __init__(self):
        self.psf_image_stream_xy = BytesIO()
        self.psf_image_stream_xz = BytesIO()
        self.pr_result_image_stream = BytesIO()
        self.pr_fiterror_image_stream = BytesIO()
        self.zd_decomposition_image_stream = BytesIO()


    def reset_image_stream(self, stream, image):
        stream.truncate()
        stream.seek(0)
        image.savefig(stream, dpi=300, format='png')


class ZdResultWorkbook(xlsxwriter.Workbook):

    def __init__(self, main_app, save_path):

        super(ZdResultWorkbook, self).__init__(save_path)
        self.main_app = main_app
        self.psf_parameters = main_app.psf_parameters
        self.zernike_results = main_app.zernike_results
        self.bold_format = self.add_format({'bold': True})
        self.short_number_format = self.add_format()
        self.short_number_format.set_num_format('0.00')
        self.add_entries()

    def add_entries(self):
        worksheet = self.add_worksheet('Zernike decomposition')
        worksheet.write(0, 0, self.main_app.psf_file.get(), self.bold_format)

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

    def __init__(self, main_app, save_path):

        self.save_path = save_path
        self.psf_filename = os.path.splitext(main_app.psf_filename)[0]
        self.psf_parameters = main_app.psf_parameters
        self.zernike_results = main_app.zernike_results
        self.image_streams = main_app.image_streams
        self.pr_state = main_app.pr_state

    def create_pdf_report(self):

        def generate_psf_entry(ypos, parameter):
            xpos_name = 370
            xpos_value = 545
            xpos_unit = 550

            c.drawString(xpos_name, ypos, parameter.name)
            c.drawRightString(xpos_value, ypos, str(parameter.value.get()))
            c.drawString(xpos_unit, ypos, parameter.unit)

        psf_xy_image = ImageReader(self.image_streams.psf_image_stream_xy)
        psf_xz_image = ImageReader(self.image_streams.psf_image_stream_xz)
        pr_res_image = ImageReader(self.image_streams.pr_result_image_stream)
        pr_mse_image = ImageReader(self.image_streams.pr_fiterror_image_stream)
        zd_res_image = ImageReader(self.image_streams.zd_decomposition_image_stream)

        c = canvas.Canvas(self.save_path)
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

        c.setFont('Helvetica', 10)
        c.drawString(100, 710, "PSF x/y")
        c.drawString(230, 710, "PSF x/z")

        c.drawImage(psf_xy_image, 100, 585, width=120, height=120, mask=None)
        c.drawImage(psf_xz_image, 230, 585, width=120, height=120, mask=None)

        c.setFont('Helvetica-Bold', 12)
        c.drawString(100, 550, "Phase retrieval results")
        c.drawImage(pr_res_image, 100, 390, width=360, height=150, mask=None)
        c.drawImage(pr_mse_image, 100, 325, width=288, height=72, mask=None)

        c.setFont('Helvetica', 8)
        condition_strings = self.pr_state.current_state.get().split('\n')
        if len(condition_strings) == 1:
            condition_string = "{} after {} iterations.".format(condition_strings[0][:-1], self.pr_state.current_iter.get())
            c.drawString(395, 340, condition_string)
        if len(condition_strings) == 2 and self.pr_state.current_iter.get() == self.psf_parameters.max_iterations.value.get():
            c.drawString(395, 355, condition_strings[0])
            c.drawString(395, 340, condition_strings[1])
        if len(condition_strings) == 2 and self.pr_state.current_iter.get() < self.psf_parameters.max_iterations.value.get():
            condition_string = "During iteration {} / {} ".format(self.pr_state.current_iter.get(),
                                                                  self.psf_parameters.max_iterations.value.get())
            c.drawString(395, 355, condition_string)
            c.drawString(395, 340, condition_strings[1])


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

        generation_time = time.strftime("%d.%m.%Y - %H:%M:%S ", time.localtime())
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(100, 10, "Report generated on: " + generation_time)

        c.showPage()
        c.save()


class PrState:

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


class ParameterFrame(tk.Frame):

    def __init__(self, parent, main_app):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.main_app = main_app
        self.current_frame_width = None
        self.widgets()

    def widgets(self):

        self.filedialog_frame = FileDialogFrame(self, self.main_app, "Select PSF file & Result directory")
        self.filedialog_frame.grid(row=0, column=0, sticky=tk.W+tk.E, padx=5, pady=5)
        self.filedialog_frame.update()
        self.current_frame_width = self.filedialog_frame.winfo_width()

        self.psf_parameter_frame = PsfParamFrame(self, self.main_app, "PSF Acquisition Parameters")
        self.psf_parameter_frame.grid(row=1, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        self.pr_parameter_frame = PrParamFrame(self, self.main_app, "Phase Recovery Parameters")
        self.pr_parameter_frame.grid(row=2, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        self.action_button_frame = PsfButtonFrame(self, self.main_app)
        self.action_button_frame.grid(row=3, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        self.status_frame = PrStatusFrame(self, self.main_app, "Phase Retrieval Status")
        self.status_frame.grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)


class FileDialogFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, frame_text):
        tk.LabelFrame.__init__(self, parent, text=frame_text)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.psf_file_entry = tk.Entry(self, textvariable=self.main_app.psf_file,
                                       font=("Arial", self.main_app.font_size))
        self.psf_file_entry.grid(row=0, column=0)
        self.psf_button = tk.Button(self, text="Select PSF file", font=("Arial", self.main_app.font_size),
                                    command=self.select_PSF_file)
        self.psf_button.grid(row=0, column=1, sticky=tk.E+tk.W, padx=5, pady=5)
        self.result_dir_entry = tk.Entry(self, textvariable=self.main_app.result_directory,
                                         font=("Arial", self.main_app.font_size))
        self.result_dir_entry.grid(row=1, column=0)
        self.result_button = tk.Button(self, text="Select result directory", font=("Arial", self.main_app.font_size),
                                       command=self.select_result_dir)
        self.result_button.grid(row=1, column=1, sticky=tk.E+tk.W, padx=5, pady=5)
        self.parent.frame_width = self.winfo_reqwidth()

    def select_PSF_file(self):
        psf_path = filedialog.askopenfilename(initialdir=self.main_app.psf_directory, title="Select PSF file...",)
        self.main_app.psf_file.set(psf_path)
        self.main_app.psf_directory, self.main_app.psf_filename = os.path.split(psf_path)

    def select_result_dir(self):
        self.main_app.result_directory.set(filedialog.askdirectory(initialdir=self.main_app.result_directory, title="Select result directory...",))


class PsfParamFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, frame_text):
        tk.LabelFrame.__init__(self, parent, text=frame_text)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        def generate_parameter_entry(parameter, row_grid):
            name_label = tk.Label(self, text=parameter.name, font=("Arial", self.main_app.font_size), anchor=tk.E)
            name_label.grid(row=row_grid, column=0, sticky=tk.E, padx=2, pady=2)
            value_entry = tk.Entry(self, textvariable=parameter.value, font=("Arial", self.main_app.font_size),
                                   width=5, justify=tk.RIGHT)
            value_entry.grid(row=row_grid, column=1, padx=2, pady=2)
            unit_label = tk.Label(self, text=parameter.unit, font=("Arial", self.main_app.font_size), anchor=tk.E)
            unit_label.grid(row=row_grid, column=2, sticky=tk.E, padx=2, pady=2)

        generate_parameter_entry(self.main_app.psf_parameters.em_wavelength, 0)
        generate_parameter_entry(self.main_app.psf_parameters.num_aperture, 1)
        generate_parameter_entry(self.main_app.psf_parameters.refractive_index, 2)
        generate_parameter_entry(self.main_app.psf_parameters.xy_res, 3)
        generate_parameter_entry(self.main_app.psf_parameters.z_res, 4)


class PrParamFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, frame_text):
        tk.LabelFrame.__init__(self, parent, text=frame_text)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):

        def generate_parameter_entry(parameter, row_grid):
            name_label = tk.Label(self, text=parameter.name, font=("Arial", self.main_app.font_size), anchor=tk.E)
            name_label.grid(row=row_grid, column=0, sticky=tk.E, padx=2, pady=2)
            value_entry = tk.Entry(self, textvariable=parameter.value, font=("Arial", self.main_app.font_size),
                                   width=5, justify=tk.RIGHT)
            value_entry.grid(row=row_grid, column=1, padx=2, pady=2)
            unit_label = tk.Label(self, text=parameter.unit, font=("Arial", self.main_app.font_size), anchor=tk.E)
            unit_label.grid(row=row_grid, column=2, sticky=tk.E, padx=2, pady=2)

        generate_parameter_entry(self.main_app.psf_parameters.max_iterations, 0)
        generate_parameter_entry(self.main_app.psf_parameters.pupil_tolerance, 1)
        generate_parameter_entry(self.main_app.psf_parameters.mse_tolerance, 2)
        generate_parameter_entry(self.main_app.psf_parameters.phase_tolerance, 3)


class PsfButtonFrame(tk.Frame):

    def __init__(self, parent, main_app):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.load_psf_button = tk.Button(self, text="Load PSF", font=("Arial", self.main_app.font_size),
                                         command=self.load_PSF_file, width=18)
        self.load_psf_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.E+tk.W)

        self.pr_button = tk.Button(self, text="Start Phase Retrieval", font=("Arial", self.main_app.font_size),
                                         command=self.initiate_pr, width=18)
        self.pr_button.grid(row=0, column=1, padx=5, pady=5, sticky=tk.E+tk.W)

    def load_PSF_file(self):
        self.main_app.psf_parameters.read_data_and_parameters()
        if self.main_app.psf_parameters.is_initiated:
            starting_zpos = self.main_app.psf_parameters.z_size // 2
            self.main_app.middle_frame.psf_frame.zpos.set(starting_zpos)
            self.main_app.middle_frame.psf_frame.updatePsfXY(starting_zpos)
            starting_xypos = self.main_app.psf_parameters.xy_size // 2
            self.main_app.middle_frame.psf_frame.ypos.set(starting_xypos)
            self.main_app.middle_frame.psf_frame.updatePsfXZ(starting_xypos)

            self.main_app.phase_retrieval_results.reset_pr_result()
            self.main_app.middle_frame.pr_result_frame.reset()
            self.main_app.middle_frame.pr_mse_frame.reset()
            self.main_app.right_frame.zernike_frame.reset()
            self.main_app.zernike_results.initialize_polynom_list()
            self.main_app.right_frame.coefficient_frame.update_entries()

    def initiate_pr(self):
        if self.main_app.psf_parameters.verify():
            psf_data_prepped = utils.prep_data_for_PR(self.main_app.psf_parameters.psf_data,
                                                      self.main_app.psf_parameters.xy_size * 2)
            psf_parameters = dict(
                wl=self.main_app.psf_parameters.em_wavelength.value.get(),
                na=self.main_app.psf_parameters.num_aperture.value.get(),
                ni=self.main_app.psf_parameters.refractive_index.value.get(),
                res=self.main_app.psf_parameters.xy_res.value.get(),
                zres=self.main_app.psf_parameters.z_res.value.get(),
            )
            pr_parameters = dict(
                max_iters=self.main_app.psf_parameters.max_iterations.value.get(),
                pupil_tol=self.main_app.psf_parameters.pupil_tolerance.value.get(),
                mse_tol=self.main_app.psf_parameters.mse_tolerance.value.get(),
            )

            self.main_app.pr_state.reset_state()
            self.main_app.middle_frame.pr_result_frame.reset()
            self.main_app.middle_frame.pr_mse_frame.reset()
            self.main_app.right_frame.zernike_frame.reset()
            self.main_app.zernike_results.initialize_polynom_list()
            self.main_app.right_frame.coefficient_frame.update_entries()

            self.pr_thread = phaseretrieval_gui.PhaseRetrievalThreaded(psf_data_prepped, psf_parameters, self.main_app.pr_state,
                                                                       self.main_app.phase_retrieval_results, **pr_parameters)
            self.pr_thread.daemon = True
            self.pr_thread.start()
            self.pr_button.configure(text="Stop Phase Retrieval", command=self.stop_pr)
            self.main_app.pr_state.current_state.set("Phase retrieval running...")
            self.main_app.after(250, self.main_app.check_pr_results)

    def display_pr_results(self):

        result_figure, _ = self.main_app.phase_retrieval_results.plot(self.main_app.figure_dpi)
        self.main_app.image_streams.reset_image_stream(self.main_app.image_streams.pr_result_image_stream,
                                                       result_figure)
        self.main_app.middle_frame.pr_result_frame.show_results(result_figure)
        mse_figure, _ = self.main_app.phase_retrieval_results.plot_convergence_gui(self.main_app.figure_dpi,
                                                                                   self.main_app.psf_parameters.max_iterations.value.get())
        self.main_app.image_streams.reset_image_stream(self.main_app.image_streams.pr_fiterror_image_stream,
                                                       mse_figure)
        self.main_app.middle_frame.pr_mse_frame.show_results(mse_figure)

    def display_zd_results(self):
        self.main_app.phase_retrieval_results.fit_to_zernikes(120)
        self.main_app.zernike_fit_done.set(True)
        zernike, _ = self.main_app.phase_retrieval_results.zd_result.plot_named_coefs(self.main_app.figure_dpi)
        self.main_app.image_streams.reset_image_stream(self.main_app.image_streams.zd_decomposition_image_stream,
                                                       zernike)
        self.main_app.right_frame.zernike_frame.show_results(zernike)
        self.main_app.zernike_results.get_decomposition_from_PhaseRetrieval()
        self.main_app.right_frame.coefficient_frame.update_entries()

    def stop_pr(self):
        self.pr_thread.stop_pr.set()


class PrStatusFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, frame_text):
        tk.LabelFrame.__init__(self, parent, text=frame_text)
        self.parent = parent
        self.main_app = main_app
        self.iteration_text = tk.StringVar()
        self.iteration_text.set(" {} / {}".format(self.main_app.pr_state.current_iter.get(),
                                                  self.main_app.psf_parameters.max_iterations.value.get()))
        self.pupil_diff_text = tk.StringVar()
        self.pupil_diff_text.set(" {}".format(self.main_app.pr_state.current_pupil_diff.get()))
        self.mse_diff_text = tk.StringVar()
        self.mse_diff_text.set(" {}".format(self.main_app.pr_state.current_mse_diff.get()))
        self.widgets()

    def widgets(self):

        self.progress_bar = ttk.Progressbar(self, mode='determinate',
                                       max=self.main_app.psf_parameters.max_iterations.value.get(),
                                       variable=self.main_app.pr_state.current_iter,
                                       length=self.parent.current_frame_width)
        self.progress_bar.grid(row=0, column=0, columnspan=2, sticky=tk.E+tk.W, padx=5, pady=5)

        self.status_label = tk.Label(self, textvariable=self.main_app.pr_state.current_state,
                                     font=("Arial", self.main_app.font_size), anchor=tk.W, justify=tk.LEFT)
        self.status_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        self.main_app.psf_parameters.max_iterations.value.trace('w', self.update_status)
        self.main_app.pr_state.current_iter.trace('w', self.update_status)

        self.iterations_label = self.generate_status_entry("Current iteration",
                                                           self.iteration_text, 2)
        self.pupil_diff_label = self.generate_status_entry("Relative difference in the pupil function",
                                                           self.pupil_diff_text, 3)
        self.mse_diff_label = self.generate_status_entry("Relative difference in the MSE",
                                                         self.mse_diff_text, 4)



    def generate_status_entry(self, description, value_variable, row_grid):

        name_label = tk.Label(self, text=description, font=("Arial", self.main_app.font_size), anchor=tk.E)
        name_label.grid(row=row_grid, column=0, sticky=tk.E, padx=2, pady=2)

        value_label = tk.Label(self, textvariable=value_variable, font=("Arial", self.main_app.font_size),
                               justify=tk.RIGHT, anchor=tk.E)
        value_label.grid(row=row_grid, column=1, sticky=tk.E, padx=2, pady=2)

        return value_label

    def update_status(self, name, m, x):

        # throws exception if field is empty, because user deleted the entry
        try:
            if name == 'MAX_ITER':
                self.main_app.pr_state.current_iter.set(0)
                self.progress_bar.configure(max=self.main_app.psf_parameters.max_iterations.value.get())

            self.iteration_text.set("{} / {}".format(self.main_app.pr_state.current_iter.get(),
                                                     self.main_app.psf_parameters.max_iterations.value.get()))

            self.pupil_diff_text.set(" {:.2E}".format(self.main_app.pr_state.current_pupil_diff.get()))

            self.mse_diff_text.set(" {:.2E}".format(self.main_app.pr_state.current_mse_diff.get()))


        except tk._tkinter.TclError:
            pass


class ImageFrame(tk.Frame):
    def __init__(self, parent, main_app):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.psf_frame = PsfFrame(self, self.main_app, "PSF preview")
        self.psf_frame.grid(row=0, column=0, padx=5, pady=5)
        self.pr_result_frame = ResultFrame(self, self.main_app, 'Phase Retrieval Results', 'No phase retrieval results yet.',
                                      12, 5)
        self.pr_result_frame.grid(row=1, column=0, padx=5, pady=5, sticky=tk.E+tk.W)
        self.pr_mse_frame = ResultFrame(self, self.main_app, 'Phase Retrieval Error', 'No phase retrieval results yet.', 12, 3)
        self.pr_mse_frame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.E+tk.W)


class ZernikeFrame(tk.Frame):
    def __init__(self, parent, main_app):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.zernike_frame = ResultFrame(self, self.main_app, 'Zernike Decomposition Results',
                                         'No zernike decomposition results yet.', 6, 6)
        self.zernike_frame.grid(row=0, column=0, padx=5, pady=5)
        self.coefficient_frame = ZernikeCoefficientFrame(self, self.main_app, "Decomposed Zernike Coefficients")
        self.coefficient_frame.grid(row=1, column=0, padx=5, pady=5, sticky=tk.E+tk.W)
        self.result_button_frame = ResultButtonFrame(self, self.main_app, "Save Results")
        self.result_button_frame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.E+tk.W)


class PsfFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, label_text):
        tk.LabelFrame.__init__(self, parent, text=label_text)
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.zpos = tk.IntVar()
        self.zpos.set(0)
        self.ypos = tk.IntVar()
        self.ypos.set(0)

        self.psf_xy_figure = self.createDummyPsf()
        self.zstack_slider = tk.Scale(self, label="Z Position", orient=tk.HORIZONTAL,
                                      font=("Arial", self.main_app.font_size), command=self.updatePsfXY,
                                      variable=self.zpos, state=tk.DISABLED)
        self.psf_xy_figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        self.zstack_slider.grid(row=1, column=0, sticky=tk.W + tk.E, padx=5, pady=5)

        self.psf_xz_figure = self.createDummyPsf()
        self.ypos_slider = tk.Scale(self, label="Y Position", orient=tk.HORIZONTAL,
                                    font=("Arial", self.main_app.font_size),command=self.updatePsfXZ,
                                    variable=self.ypos, state=tk.DISABLED)
        self.psf_xz_figure._tkcanvas.grid(row=0, column=1, padx=5, pady=5)
        self.ypos_slider.grid(row=1, column=1, sticky=tk.W + tk.E, padx=5, pady=5)


    def createDummyPsf(self):
        psf_dummy = plt.figure(figsize=(6, 6), dpi=self.main_app.figure_dpi)
        psf_dummy.text(0.5, 0.5, "No PSF has been loaded.", fontname='Arial', fontsize=16, horizontalalignment='center')
        psf_dummy_figure = FigureCanvasTkAgg(psf_dummy, master=self)
        plt.close(psf_dummy)
        return psf_dummy_figure

    def createPsfXY(self, current_zpos):
        psf_xy = plt.figure(figsize=(6, 6), dpi=self.main_app.figure_dpi)
        xy_ax = psf_xy.add_axes([0, 0, 1, 1])
        xy_ax.matshow(self.main_app.psf_parameters.psf_data[int(current_zpos)], cmap="inferno")
        self.main_app.image_streams.reset_image_stream(self.main_app.image_streams.psf_image_stream_xy,
                                                       psf_xy)
        psf_xy_figure = FigureCanvasTkAgg(psf_xy, master=self)
        plt.close(psf_xy)
        return psf_xy_figure

    def createPsfXZ(self, current_line_pos):
        psf_xz = plt.figure(figsize=(6, 6), dpi=self.main_app.figure_dpi)
        xz_ax = psf_xz.add_axes([0, 0, 1, 1])
        xz_ax.xaxis.set_visible(False)
        psf_xz.patch.set_facecolor('black')
        aspect_z_xy = self.main_app.psf_parameters.z_res.value.get() / float(self.main_app.psf_parameters.xy_res.value.get())
        xz_ax.matshow(self.main_app.psf_parameters.psf_data[:,int(current_line_pos),:],
                      cmap="inferno", aspect=aspect_z_xy)
        self.main_app.image_streams.reset_image_stream(self.main_app.image_streams.psf_image_stream_xz,
                                                       psf_xz)
        psf_xz_figure = FigureCanvasTkAgg(psf_xz, master=self)
        plt.close(psf_xz)
        return psf_xz_figure

    def updatePsfXY(self, current_zpos):
        obsolete_canvas = self.psf_xy_figure
        self.psf_xy_figure = self.createPsfXY(current_zpos)
        self.psf_xy_figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        obsolete_canvas._tkcanvas.destroy()
        self.zstack_slider.configure(state=tk.NORMAL, to=self.main_app.psf_parameters.z_size - 1)

    def updatePsfXZ(self, current_ypos):
        obsolete_canvas = self.psf_xz_figure
        self.psf_xz_figure = self.createPsfXZ(current_ypos)
        self.psf_xz_figure._tkcanvas.grid(row=0, column=1, padx=5, pady=5)
        obsolete_canvas._tkcanvas.destroy()
        self.ypos_slider.configure(state=tk.NORMAL, to=self.main_app.psf_parameters.xy_size - 1)


class ResultFrame(tk.LabelFrame):
    def __init__(self, parent, main_app, label_text, placeholder_text, figure_width, figure_height):
        tk.LabelFrame.__init__(self, parent, text=label_text)
        self.main_app = main_app
        self.placeholder_text = placeholder_text
        self.figure_width = figure_width
        self.figure_height = figure_height
        self.initiate()

    def initiate(self):
        white_space = plt.figure(figsize=(self.figure_width, self.figure_height), dpi=self.main_app.figure_dpi)
        white_space.text(0.5, 0.5, self.placeholder_text, fontname='Arial', fontsize=16, horizontalalignment='center')
        self.figure = FigureCanvasTkAgg(white_space, master=self)
        self.figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        plt.close(white_space)

    def show_results(self, result_figure):
        obsolete_canvas = self.figure
        self.figure = FigureCanvasTkAgg(result_figure, master=self)
        self.figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        obsolete_canvas._tkcanvas.destroy()
        plt.close(result_figure)

    def reset(self):
        obsolete_canvas = self.figure
        self.initiate()
        obsolete_canvas._tkcanvas.destroy()


class ZernikeCoefficientFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, label_text):
        tk.LabelFrame.__init__(self, parent, text=label_text)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        rows = range(0, len(self.main_app.zernike_results.zernike_polynoms))
        for row, polynom in zip(rows, self.main_app.zernike_results.zernike_polynoms):

                if polynom.order in self.main_app.zernike_results.important_coeff_orders:
                    temp_label = tk.Label(self, text=polynom.name, font=("Arial", self.main_app.font_size, 'bold'),
                                          anchor=tk.E)
                else:
                    temp_label = tk.Label(self, text=polynom.name, font=("Arial", self.main_app.font_size),
                                          anchor=tk.E)
                temp_label.grid(row=row, column=0, sticky=tk.E, pady=2)

                value_string = '  {:.2f}'.format(polynom.value)
                if polynom.order in self.main_app.zernike_results.important_coeff_orders:
                    temp_label = tk.Label(self, text=value_string, font=("Arial", self.main_app.font_size, 'bold'),
                                          anchor=tk.E)
                else:
                    temp_label = tk.Label(self, text=value_string, font=("Arial", self.main_app.font_size),
                                          anchor=tk.E)
                temp_label.grid(row=row, column=1, sticky=tk.E)

                if polynom.in_tolerance is not None:
                    if polynom.in_tolerance:
                        temp_label = tk.Label(self, text='OK!', font=("Arial", self.main_app.font_size), fg='green')
                    else:
                        temp_label = tk.Label(self, text='Not OK!', font=("Arial", self.main_app.font_size), fg='red')
                    temp_label.grid(row=row, column=2)

    def update_entries(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.widgets()


class ResultButtonFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, label_text):
        tk.LabelFrame.__init__(self, parent, text=label_text)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):

        self.main_app.pr_state.pr_finished.trace('w', self.toggle_buttons)

        self.save_pr_result_button = tk.Button(self, text="Phase & Magnitude as .png", font=("Arial", self.main_app.font_size),
                                            command=self.save_pr_image, state=tk.DISABLED, width=23)
        self.save_pr_result_button.grid(row=0, column=0, padx=5, pady=5,)

        self.save_zernice_img_button = tk.Button(self, text="Zernike Coeff. as .png", font=("Arial", self.main_app.font_size),
                                            command=self.save_zd_image, state=tk.DISABLED, width=23)
        self.save_zernice_img_button.grid(row=1, column=0, padx=5, pady=5,)

        self.save_zernice_values_button = tk.Button(self, text="Zernike Coeff. as .csv", font=("Arial", self.main_app.font_size),
                                            command=self.save_zd_values, state=tk.DISABLED, width=23)
        self.save_zernice_values_button.grid(row=0, column=1, padx=5, pady=5,)

        self.save_pdf_report = tk.Button(self, text="Create pdf report", font=("Arial", self.main_app.font_size),
                                            command=self.generate_pdf_report, state=tk.DISABLED, width=23)
        self.save_pdf_report.grid(row=1, column=1, padx=5, pady=5,)


    def toggle_buttons(self, n, m, x):

        for child in self.winfo_children():
            if self.main_app.pr_state.pr_finished.get():
               child.configure(state=tk.NORMAL)
            else:
                child.configure(state=tk.DISABLED)

    def save_pr_image(self):
        save_file = os.path.join(self.main_app.result_directory.get(),
                                 os.path.splitext(self.main_app.psf_filename)[0] + '_pr_results.png')
        try:
            with open(save_file, "wb") as f:
                f.write(self.main_app.image_streams.pr_result_image_stream.getvalue())
        except FileNotFoundError as pop_up_alert:
            messagebox.showwarning("Invalid File Path", str(pop_up_alert))

    def save_zd_image(self):
        save_file = os.path.join(self.main_app.result_directory.get(),
                                 os.path.splitext(self.main_app.psf_filename)[0] + '_zd_results.png')
        try:
            with open(save_file, "wb") as f:
                f.write(self.main_app.image_streams.zd_decomposition_image_stream.getvalue())
        except FileNotFoundError as pop_up_alert:
            messagebox.showwarning("Invalid File Path", str(pop_up_alert))

    def save_zd_values(self):
        xlsx_path = os.path.join(self.main_app.result_directory.get(),
                                 os.path.splitext(self.main_app.psf_filename)[0] + '_zd_results.xlsx')
        try:
            ZdResultWorkbook(self.main_app, xlsx_path)
        except Exception as pop_up_alert:
            messagebox.showwarning("Saving results as .xlsx failed", str(pop_up_alert))

    def generate_pdf_report(self):
        pdf_path = os.path.join(self.main_app.result_directory.get(),
                                 os.path.splitext(self.main_app.psf_filename)[0] + '_report.pdf')
        pdf_report = PdfReport(self.main_app, pdf_path)
        try:
            pdf_report.create_pdf_report()
        except Exception as pop_up_alert:
            messagebox.showwarning("Creating a .pdf-report failed", str(pop_up_alert))

class MainWindow(tk.Tk):

    def __init__(self, parent, screen_height, scaling_factor):
        tk.Tk.__init__(self, parent)
        javabridge.start_vm(class_path=bioformats.JARS)
        self.parent = parent
        self.title("Phase retrieval from PSF")
        self.window_height = int(0.7 * screen_height)
        self.scaling_factor = scaling_factor

        self.window_width = int(1.43 * self.window_height)
        window_size = '{}x{}'.format(str(self.window_width), str(self.window_height))
        self.geometry(window_size)
        self.resizable(False, False)

        self.font_size = int((30 * 1080) / (screen_height * self.scaling_factor))
        self.figure_dpi = int((180 * 1080) / screen_height)
        self.psf_parameters = PsfParameters(self)
        self.psf_file = tk.StringVar()
        self.psf_file.set('Select a PSF file...')
        self.psf_directory = tk.StringVar()
        self.psf_directory.set('D:\\')
        self.psf_filename = None
        self.result_directory = tk.StringVar()
        self.result_directory.set('Select a result directory...')
        self.pr_state = PrState()
        self.phase_retrieval_results = phaseretrieval_gui.PhaseRetrievalResult()
        self.phase_retrieval_done = tk.BooleanVar()
        self.phase_retrieval_done.set(False)
        self.zernike_results = ZernikeDecomposition(self)
        self.zernike_fit_done = tk.BooleanVar()
        self.zernike_fit_done.set(False)
        self.image_streams = ResultImageStreams()
        self.main_widgets()

    def main_widgets(self):
        self.left_frame = ParameterFrame(self, self)
        self.left_frame.grid(row=0, column=0, sticky=tk.N)
        self.middle_frame = ImageFrame(self, self)
        self.middle_frame.grid(row=0, column=1, sticky=tk.N)
        self.right_frame = ZernikeFrame(self, self)
        self.right_frame.grid(row=0, column=2, sticky=tk.N)

    def check_pr_results(self):
        if(self.left_frame.action_button_frame.pr_thread.is_alive()):
            self.left_frame.status_frame.update()
            self.after(250, self.check_pr_results)
            if self.pr_state.current_iter.get() != 0 and self.pr_state.current_iter.get() % 5 == 0:
                self.left_frame.action_button_frame.display_pr_results()
        else:
            self.left_frame.action_button_frame.display_pr_results()
            self.left_frame.action_button_frame.display_zd_results()
            self.left_frame.status_frame.update_status(None, None, None)
            self.left_frame.action_button_frame.pr_button.configure(text="Start Phase Retrieval",
                                                                    command=self.left_frame.action_button_frame.
                                                                    initiate_pr)
            self.pr_state.pr_finished.set(True)


    def clean_up(self):
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            javabridge.kill_vm()
            self.destroy()


if __name__ == "__main__":
    user32 = windll.user32
    virtual_screen_height = user32.GetSystemMetrics(1)
    user32.SetProcessDPIAware(1)
    screen_height = user32.GetSystemMetrics(1)
    scaling = screen_height / virtual_screen_height
    app = MainWindow(None, screen_height, scaling)
    app.protocol("WM_DELETE_WINDOW", app.clean_up)
    app.mainloop()

