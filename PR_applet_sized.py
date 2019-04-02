# coding: utf-8
"""
Graphical user interface
Back focal plane (pupil) phase retrieval algorithm base on:
[(1) Hanser, B. M.; Gustafsson, M. G. L.; Agard, D. A.; Sedat, J. W.
Phase Retrieval for High-Numerical-Aperture Optical Systems.
Optics Letters 2003, 28 (10), 801.](dx.doi.org/10.1364/OL.28.000801)

Copyright (c) 2016, David Hoffman

The original phaseretrieval.py has been changed to a threading.Thread class, to allow it to run in parallel with the
tkinter mainloop. This is needed to make the tkinter gui responsive during calculation and allows for intermediate
results to be displayed.

Copyright (c) 2019, Martin Stoeckl
"""


import os
from ctypes import *
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import javabridge
import bioformats

from pyOTF import phaseretrieval_gui
from pyOTF import utils

import TrackingClasses



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

        generate_parameter_entry(self.main_app.psf_fit_parameters.em_wavelength, 0)
        generate_parameter_entry(self.main_app.psf_fit_parameters.num_aperture, 1)
        generate_parameter_entry(self.main_app.psf_fit_parameters.refractive_index, 2)
        generate_parameter_entry(self.main_app.psf_fit_parameters.xy_res, 3)
        generate_parameter_entry(self.main_app.psf_fit_parameters.z_res, 4)


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

        generate_parameter_entry(self.main_app.psf_fit_parameters.max_iterations, 0)
        generate_parameter_entry(self.main_app.psf_fit_parameters.pupil_tolerance, 1)
        generate_parameter_entry(self.main_app.psf_fit_parameters.mse_tolerance, 2)
        generate_parameter_entry(self.main_app.psf_fit_parameters.phase_tolerance, 3)


class PsfButtonFrame(tk.Frame):

    def __init__(self, parent, main_app):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.main_app = main_app
        self.widgets()

    def widgets(self):
        self.load_psf_button = tk.Button(self, text="Load PSF", font=("Arial", self.main_app.font_size),
                                         command=self.main_app.load_PSF_file, width=18)
        self.load_psf_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.E+tk.W)

        self.pr_button = tk.Button(self, text="Start Phase Retrieval", font=("Arial", self.main_app.font_size),
                                         command=self.main_app.initiate_pr, width=18)
        self.pr_button.grid(row=0, column=1, padx=5, pady=5, sticky=tk.E+tk.W)


class PrStatusFrame(tk.LabelFrame):

    def __init__(self, parent, main_app, frame_text):
        tk.LabelFrame.__init__(self, parent, text=frame_text)
        self.parent = parent
        self.main_app = main_app
        self.iteration_text = tk.StringVar()
        self.iteration_text.set(" {} / {}".format(self.main_app.pr_state.current_iter.get(),
                                                  self.main_app.psf_fit_parameters.max_iterations.value.get()))
        self.pupil_diff_text = tk.StringVar()
        self.pupil_diff_text.set(" {}".format(self.main_app.pr_state.current_pupil_diff.get()))
        self.mse_diff_text = tk.StringVar()
        self.mse_diff_text.set(" {}".format(self.main_app.pr_state.current_mse_diff.get()))
        self.widgets()

    def widgets(self):

        self.progress_bar = ttk.Progressbar(self, mode='determinate',
                                       max=self.main_app.psf_fit_parameters.max_iterations.value.get(),
                                       variable=self.main_app.pr_state.current_iter,
                                       length=self.parent.current_frame_width)
        self.progress_bar.grid(row=0, column=0, columnspan=2, sticky=tk.E+tk.W, padx=5, pady=5)

        self.status_label = tk.Label(self, textvariable=self.main_app.pr_state.current_state,
                                     font=("Arial", self.main_app.font_size), anchor=tk.W, justify=tk.LEFT)
        self.status_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        self.main_app.psf_fit_parameters.max_iterations.value.trace('w', self.update_status)
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
                self.progress_bar.configure(max=self.main_app.psf_fit_parameters.max_iterations.value.get())

            self.iteration_text.set("{} / {}".format(self.main_app.pr_state.current_iter.get(),
                                                     self.main_app.psf_fit_parameters.max_iterations.value.get()))

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
        xy_ax.matshow(self.main_app.psf_fit_parameters.psf_data[int(current_zpos)], cmap="inferno")
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
        aspect_z_xy = self.main_app.psf_fit_parameters.z_res.value.get() / float(self.main_app.psf_fit_parameters.xy_res.value.get())
        xz_ax.matshow(self.main_app.psf_fit_parameters.psf_data[:,int(current_line_pos),:],
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
        self.zstack_slider.configure(state=tk.NORMAL, to=self.main_app.psf_fit_parameters.z_size - 1)

    def updatePsfXZ(self, current_ypos):
        obsolete_canvas = self.psf_xz_figure
        self.psf_xz_figure = self.createPsfXZ(current_ypos)
        self.psf_xz_figure._tkcanvas.grid(row=0, column=1, padx=5, pady=5)
        obsolete_canvas._tkcanvas.destroy()
        self.ypos_slider.configure(state=tk.NORMAL, to=self.main_app.psf_fit_parameters.xy_size - 1)


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
            TrackingClasses.ZdResultWorkbook(xlsx_path, self.main_app.psf_file.get(), self.main_app.psf_fit_parameters,
                                             self.main_app.zernike_results, self.main_app.pr_state)
        except Exception as pop_up_alert:
            messagebox.showwarning("Saving results as .xlsx failed", str(pop_up_alert))

    def generate_pdf_report(self):
        pdf_path = os.path.join(self.main_app.result_directory.get(),
                                os.path.splitext(self.main_app.psf_filename)[0] + '_report.pdf')
        pdf_report = TrackingClasses.PdfReport(pdf_path, self.main_app.psf_file.get(), self.main_app.psf_fit_parameters,
                                               self.main_app.zernike_results, self.main_app.image_streams,
                                               self.main_app.pr_state)
        try:
            pdf_report.create_pdf_report()
        except Exception as pop_up_alert:
            messagebox.showwarning("Creating a .pdf-report failed", str(pop_up_alert))

class MainWindow(tk.Tk):

    def __init__(self, screen_height, scaling_factor):
        tk.Tk.__init__(self)

        # start a JVM, needed to run the bioformats class used in bioformats_helper.PsfImageDataAndParameters
        javabridge.start_vm(class_path=bioformats.JARS)

        # Set up the main window and font size and figure resolution according to the screen resolution
        #TODO: test this for different environments
        self.title("Phase retrieval from PSF")
        self.window_height = int(0.7 * screen_height)
        self.scaling_factor = scaling_factor
        self.window_width = int(1.43 * self.window_height)
        window_size = '{}x{}'.format(str(self.window_width), str(self.window_height))
        self.geometry(window_size)
        self.resizable(False, False)

        self.font_size = int((30 * 1080) / (screen_height * self.scaling_factor))
        self.figure_dpi = int((180 * 1080) / screen_height)

        # Instantiate the class tracking PSF and fit parameters
        self.psf_fit_parameters = TrackingClasses.PsfandFitParameters()

        # Initialize the variables tracking PSF file and results directory
        self.psf_file = tk.StringVar()
        self.psf_file.set('Select a PSF file...')
        self.psf_directory = tk.StringVar()
        self.psf_directory.set('D:\\')
        self.psf_filename = None
        self.result_directory = tk.StringVar()
        self.result_directory.set('Select a result directory...')

        # Instantiate the class tracking the state of the Phase Retrieval Algorithm
        self.pr_state = TrackingClasses.PrState()

        # Instantiate the class tracking the Phase Retrieval Algorithm results
        self.phase_retrieval_results = phaseretrieval_gui.PhaseRetrievalResult()

        # Instantiate the class tracking the Zernike Decomposition results
        self.zernike_results = TrackingClasses.ZernikeDecomposition()

        # Instantiate the class storing the GUI images as Bytestreams
        self.image_streams = TrackingClasses.ResultImageStreams()

        # Create the first level frames
        self.left_frame = ParameterFrame(self, self)
        self.left_frame.grid(row=0, column=0, sticky=tk.N)
        self.middle_frame = ImageFrame(self, self)
        self.middle_frame.grid(row=0, column=1, sticky=tk.N)
        self.right_frame = ZernikeFrame(self, self)
        self.right_frame.grid(row=0, column=2, sticky=tk.N)

    def load_PSF_file(self):
        self.main_app.psf_fit_parameters.read_data_and_parameters(self.main_app.psf_file.get())
        if self.main_app.psf_fit_parameters.is_initiated:
            starting_zpos = self.main_app.psf_fit_parameters.z_size // 2
            self.main_app.middle_frame.psf_frame.zpos.set(starting_zpos)
            self.main_app.middle_frame.psf_frame.updatePsfXY(starting_zpos)
            starting_xypos = self.main_app.psf_fit_parameters.xy_size // 2
            self.main_app.middle_frame.psf_frame.ypos.set(starting_xypos)
            self.main_app.middle_frame.psf_frame.updatePsfXZ(starting_xypos)

            self.main_app.phase_retrieval_results.reset_pr_result()
            self.main_app.middle_frame.pr_result_frame.reset()
            self.main_app.middle_frame.pr_mse_frame.reset()
            self.main_app.right_frame.zernike_frame.reset()
            self.main_app.zernike_results.initialize_polynom_list()
            self.main_app.right_frame.coefficient_frame.update_entries()

    def initiate_pr(self):
        if self.psf_fit_parameters.verify():
            self.pr_state.reset_state()
            self.middle_frame.pr_result_frame.reset()
            self.middle_frame.pr_mse_frame.reset()
            self.right_frame.zernike_frame.reset()
            self.zernike_results.initialize_polynom_list()
            self.right_frame.coefficient_frame.update_entries()

            self.pr_thread = phaseretrieval_gui.PhaseRetrievalThreaded(self.psf_fit_parameters.psf_data_prepped,
                                                                       self.psf_fit_parameters.psf_parameter_dict(),
                                                                       self.pr_state,
                                                                       self.phase_retrieval_results,
                                                                       **self.psf_fit_parameters.fit_parameter_dict(),
                                                                       )
            self.pr_thread.daemon = True
            self.pr_thread.start()
            self.pr_button.configure(text="Stop Phase Retrieval", command=self.stop_pr)
            self.pr_state.current_state.set("Phase retrieval running...")
            self.after(250, self.check_pr_results)

    def check_pr_results(self):
        """Checks every 250 ms, whether phaseretrieval_gui.PhaseRetrievalThreaded is still running. If the thread
            is not alive(finished or has been aborted), update the GUI display, reset the PR_button to start the next
            Phase Retrieval Algorithm. Calls itself, if the thread is still running and updates the GUI display every
            five iterations.
        """
        if self.pr_thread.is_alive():
            self.left_frame.status_frame.update()
            self.after(250, self.check_pr_results)
            if self.pr_state.current_iter.get() != 0 and self.pr_state.current_iter.get() % 5 == 0:
                self.display_pr_results()
        else:
            self.display_pr_results()
            self.display_zd_results()
            self.left_frame.status_frame.update_status(None, None, None)
            self.left_frame.action_button_frame.pr_button.configure(text="Start Phase Retrieval",
                                                                    command=self.initiate_pr)
            self.pr_state.pr_finished.set(True)

    def display_pr_results(self):
        result_figure, _ = self.phase_retrieval_results.plot(self.figure_dpi)
        self.image_streams.reset_image_stream(self.image_streams.pr_result_image_stream, result_figure)
        self.middle_frame.pr_result_frame.show_results(result_figure)

        mse_figure, _ = self.phase_retrieval_results.plot_convergence_gui(self.figure_dpi,
                                                                          self.psf_fit_parameters.
                                                                          max_iterations.value.get())
        self.image_streams.reset_image_stream(self.image_streams.pr_fiterror_image_stream, mse_figure)
        self.middle_frame.pr_mse_frame.show_results(mse_figure)

    def display_zd_results(self):
        self.phase_retrieval_results.fit_to_zernikes(120)

        zernike_figure, _ = self.phase_retrieval_results.zd_result.plot_named_coefs(self.figure_dpi)
        self.image_streams.reset_image_stream(self.image_streams.zd_decomposition_image_stream, zernike_figure)
        self.right_frame.zernike_frame.show_results(zernike_figure)

        self.zernike_results.decomposition_from_phase_retrieval(self.phase_retrieval_results, self.psf_fit_parameters.
                                                                phase_tolerance.value.get())
        self.right_frame.coefficient_frame.update_entries()

    def stop_pr(self):
        """Sets the stop_pr flag, breaks out of the iteration loop in phaseretrieval_gui.PhaseRetrievalThreaded"""
        self.pr_thread.stop_pr.set()

    def clean_up(self):
        """Ensures that the JVM is killed, before the tk.root is destroyed"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            javabridge.kill_vm()
            self.destroy()


if __name__ == "__main__":
    user32 = windll.user32
    virtual_screen_height = user32.GetSystemMetrics(1)
    user32.SetProcessDPIAware(1)
    screen_height = user32.GetSystemMetrics(1)
    scaling = screen_height / virtual_screen_height
    app = MainWindow(screen_height, scaling)
    app.protocol("WM_DELETE_WINDOW", app.clean_up)
    app.mainloop()

