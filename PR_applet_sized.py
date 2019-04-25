# coding: utf-8
"""
Graphical user interface for the Phase Retrieval Algorithm based on:
Hanser, B. M.; Gustafsson, M. G. L.; Agard, D. A.; Sedat, J. W.
Phase Retrieval for High-Numerical-Aperture Optical Systems.
Optics Letters 2003, 28 (10), 801.](dx.doi.org/10.1364/OL.28.000801)

The user interface allows to select the PSF files (supported by bioformats oder ome-tiff), adjust PSF and
fit parameters. The PSF can be previewed, the current status of the PR Algorithm can be tracked. Images of the results,
the final data and a comprehensive pdf report can be created.

The GUI uses the algorithms written by David Hoffman (Copyright (c) 2016):
https://github.com/david-hoffman/pyOTF
https://github.com/david-hoffman/dphutils

The original phaseretrieval.py has been changed to a threading.Thread class, to allow it to run in parallel with the
tkinter mainloop. This is needed to make the tkinter gui responsive during calculation and allows for intermediate
results to be displayed. In addition some plotting fuctions have been adapted towork with th GUI.
These changes have been made in a forked pyOTF repository:
https://github.com/MartinSt80/pyOTF

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

import TrackingClasses


class ParameterFrame(tk.Frame):
    """
    The left frame in the GUI. Select PSF file and result directory, enter PSF and Fit Parameters, load PSF file,
    start/stop the Phase Retrieval Algorithm, show the current state of the PR Algorithm in its subframes.

        Arguments
        ----------
        parent: _tkinter.tkapp
            The parent (tk.Root)

        Parameters
        -----------
        self.current_frame_width: int
            Width of the frame in pixels
    """
    class FileDialogFrame(tk.LabelFrame):
        """
        Contains the Filedialogs and buttons to select PSF file and result directory.

           Arguments
           ----------
           parent: tk.Frame
               The parent frame (tk.Frame)
            frame_text: string
                The tk.LabelFrame description
       """

        def __init__(self, parent, frame_text):
            tk.LabelFrame.__init__(self, parent, text=frame_text)
            self.widgets()

        def widgets(self):
            # tk.Entry for the PSF file
            self.psf_file_entry = tk.Entry(self,
                                           textvariable=self.winfo_toplevel().psf_file,
                                           font=("Arial", self.winfo_toplevel().font_size)
                                           )
            self.psf_file_entry.grid(row=0, column=0)

            # tk.Button, opens a filedialog to select the PSF file
            self.psf_button = tk.Button(self,
                                        text="Select PSF file",
                                        font=("Arial", self.winfo_toplevel().font_size),
                                        command=self.winfo_toplevel().select_psf_file
                                        )
            self.psf_button.grid(row=0, column=1, sticky=tk.E + tk.W, padx=5, pady=5)

            # tk.Entry for the result directory
            self.result_dir_entry = tk.Entry(self,
                                             textvariable=self.winfo_toplevel().result_directory,
                                             font=("Arial", self.winfo_toplevel().font_size)
                                             )
            self.result_dir_entry.grid(row=1, column=0)

            # tk.Button, opens a filedialog to select the result directory
            self.result_button = tk.Button(self,
                                           text="Select result directory",
                                           font=("Arial", self.winfo_toplevel().font_size),
                                           command=self.winfo_toplevel().select_result_dir
                                           )
            self.result_button.grid(row=1, column=1, sticky=tk.E + tk.W, padx=5, pady=5)

    class PsfParamFrame(tk.LabelFrame):
        """
        Contains the Entries for the PSF parameters loaded from the PSF file or entered by the user.

           Arguments
           ----------
           parent: tk.Frame
               The parent frame (tk.Frame)
            frame_text: string
                The tk.LabelFrame description
       """

        def __init__(self, parent, frame_text):
            tk.LabelFrame.__init__(self, parent, text=frame_text)
            self.widgets()

        def widgets(self):
            # Generate the widgets for the PSF parameters
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.em_wavelength, 0)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.num_aperture, 1)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.refractive_index, 2)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.xy_res, 3)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.z_res, 4)

    class PrParamFrame(tk.LabelFrame):
        """
            Contains the Entries for the Phase Retrieval Algorithm parameters used from default (kwarg)
            or entered by the user.

               Arguments
               ----------
               parent: tk.Frame
                   The parent frame (tk.Frame)
                frame_text: string
                    The tk.LabelFrame description
           """

        def __init__(self, parent, frame_text):
            tk.LabelFrame.__init__(self, parent, text=frame_text)
            self.widgets()

        def widgets(self):
            # Generate the widgets for the PR Algorithm parameters
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.max_iterations, 0)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.pupil_tolerance, 1)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.mse_tolerance, 2)
            self.master.generate_parameter_entry(self, self.winfo_toplevel().psf_fit_parameters.phase_tolerance, 3)

    class PsfButtonFrame(tk.Frame):
        """
        Buttons, to load the PSF parameters and date from the selected file and start/stop the PR Algorithm

           Arguments
           ----------
           parent: tk.Frame
               The parent frame (tk.Frame)
        """

        def __init__(self, parent):
            tk.Frame.__init__(self, parent)
            self.widgets()

        def widgets(self):
            # Button to load the PSF parameters and date from the selected file
            self.load_psf_button = tk.Button(self,
                                             text="Load PSF",
                                             font=("Arial", self.winfo_toplevel().font_size),
                                             command=self.winfo_toplevel().load_psf_file,
                                             width=18
                                             )
            self.load_psf_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.E + tk.W)

            # Button to start/stop the PR Algorithm
            self.pr_button = tk.Button(self,
                                       text="Start Phase Retrieval",
                                       font=("Arial", self.winfo_toplevel().font_size),
                                       command=self.winfo_toplevel().initiate_pr,
                                       width=18
                                       )
            self.pr_button.grid(row=0, column=1, padx=5, pady=5, sticky=tk.E + tk.W)

    class PrStatusFrame(tk.LabelFrame):
        """
            Displays the current state of the PR Algorithm by progressbar, status message and display of the
            current fit convergence.

                Arguments
                ----------
                parent: tk.Frame
                   The parent frame (tk.Frame)
                frame_text: string
                    The tk.LabelFrame description

                Attributes
                -----------
                iteration_text: tk.StringVar
                    The current iterations snippet for the status string
                pupil_diff_text: tk.StringVar
                    The current iterations snippet for the pupil function difference string
                mse_diff_text: tk.StringVar
                    The current iterations snippet for the mse difference string
           """

        def __init__(self, parent, frame_text):
            tk.LabelFrame.__init__(self, parent, text=frame_text)
            # initiate tk.StringVars
            self.iteration_text = tk.StringVar()
            self.iteration_text.set(" {} / {}".format(self.winfo_toplevel().pr_state.current_iter.get(),
                                                      self.winfo_toplevel().psf_fit_parameters.
                                                      max_iterations.value.get()
                                                      )
                                    )
            self.pupil_diff_text = tk.StringVar()
            self.pupil_diff_text.set(" {}".format(self.winfo_toplevel().pr_state.current_pupil_diff.get()))
            self.mse_diff_text = tk.StringVar()
            self.mse_diff_text.set(" {}".format(self.winfo_toplevel().pr_state.current_mse_diff.get()))

            self.widgets()

        def widgets(self):
            # Create a progress bar to follow the PR Algorithm iterations, fit length to self.master.frame_width
            self.progress_bar = ttk.Progressbar(self,
                                                mode='determinate',
                                                max=self.winfo_toplevel().psf_fit_parameters.max_iterations.value.get(),
                                                variable=self.winfo_toplevel().pr_state.current_iter,
                                                length=self.master.current_frame_width
                                                )
            self.progress_bar.grid(row=0, column=0, columnspan=2, sticky=tk.E + tk.W, padx=5, pady=5)

            # Creates a label which displays the PR Algorithm status
            self.status_label = tk.Label(self,
                                         textvariable=self.winfo_toplevel().pr_state.current_state,
                                         font=("Arial", self.winfo_toplevel().font_size),
                                         anchor=tk.W,
                                         justify=tk.LEFT
                                         )
            self.status_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

            # Trace if the user changed the max iterations and the current iteration of the PR algorithm
            # Throws exception if field was empty, because user deleted the entry
            self.winfo_toplevel().psf_fit_parameters.max_iterations.value.trace('w', self.update_status)
            self.winfo_toplevel().pr_state.current_iter.trace('w', self.update_status)

            # Generate the status entries
            self.generate_status_entry("Current iteration", self.iteration_text, 2)
            self.generate_status_entry("Relative difference in the pupil function", self.pupil_diff_text, 3)
            self.generate_status_entry("Relative difference in the MSE", self.mse_diff_text, 4)

        def generate_status_entry(self, description, value_variable, row_grid):
            """
                Generate a status display with fixed description, and a tk.StringVar which can be updated as needed

                    Arguments
                    ----------
                    description: string
                       The fixed descriptional part of the displayed text
                    value_variable: tk.StringVar
                        A text snippet which can be updated dynamically
                    row_grid: int
                        The row for the grid geometry manager to place the widgets on
               """
            name_label = tk.Label(self, text=description, font=("Arial", self.winfo_toplevel().font_size), anchor=tk.E)
            name_label.grid(row=row_grid, column=0, sticky=tk.E, padx=2, pady=2)

            value_label = tk.Label(self,
                                   textvariable=value_variable,
                                   font=("Arial", self.winfo_toplevel().font_size),
                                   justify=tk.RIGHT,
                                   anchor=tk.E
                                   )
            value_label.grid(row=row_grid, column=1, sticky=tk.E, padx=2, pady=2)

        def update_status(self, name, m, x):
            """
                Updates the status elements, called by trace if the max iterations or the current iteration changed.

                Arguments
                ----------
                name: string or list
                   The internal name of the variable which was changed, or as list of variabels
                m: int or ""
                    Index for name list or empty string
                x: string
                    What operation triggered the trace: 'w': write, 'r': read or 'u': delete
           """

            # Check if the maximum iterations were adjusted by the user
            try:
                if name == 'MAX_ITER':
                    # Set current iterations to zero and adjust the max of the progress bar
                    self.winfo_toplevel().pr_state.current_iter.set(0)
                    self.progress_bar.configure(max=self.winfo_toplevel().psf_fit_parameters.max_iterations.value.get())

                # Update the dynamical text snippets in the status display
                self.iteration_text.set("{} / {}".format(self.winfo_toplevel().pr_state.current_iter.get(),
                                                         self.winfo_toplevel().psf_fit_parameters.max_iterations.
                                                         value.get()
                                                         )
                                        )
                self.pupil_diff_text.set(" {:.2E}".format(self.winfo_toplevel().pr_state.current_pupil_diff.get()))

                self.mse_diff_text.set(" {:.2E}".format(self.winfo_toplevel().pr_state.current_mse_diff.get()))
            except tk._tkinter.TclError:
                pass

    def __init__(self, parent):
        tk.Frame.__init__(self, parent)
        self.current_frame_width = None
        self.widgets()

    def widgets(self):
        # Subframe, select PSF and result directory (the widest in ParameterFrame)
        self.filedialog_frame = self.FileDialogFrame(self, "Select PSF file & Result directory")
        self.filedialog_frame.grid(row=0, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        # Draw the frame
        self.filedialog_frame.update()

        # get its width and store it (needed to size the progressbar in self.status_frame)
        self.current_frame_width = self.filedialog_frame.winfo_width()

        # Subframe, contains the entries for the PSF parameters
        self.psf_parameter_frame = self.PsfParamFrame(self, "PSF Acquisition Parameters")
        self.psf_parameter_frame.grid(row=1, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        # Subframe, contains the entries for the PR fit parameters
        self.pr_parameter_frame = self.PrParamFrame(self, "Phase Recovery Parameters")
        self.pr_parameter_frame.grid(row=2, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        # Subframe, contains the buttons to load the PSF and start/stop the PR Algorithm
        self.action_button_frame = self.PsfButtonFrame(self)
        self.action_button_frame.grid(row=3, column=0, sticky=tk.W+tk.E, padx=5, pady=5)

        # Subframe, displays the current state of the PR Algorithm
        self.status_frame = self.PrStatusFrame(self, "Phase Retrieval Status")
        self.status_frame.grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)

    def generate_parameter_entry(self, parent, parameter, row_grid):
        """
          Generates a line of widgets for the given parameter

             Arguments
             ----------
             parent: tk.Frame
                Frame in which the widgets should be created
             parameter: TrackingClasses.PsfandFitParameters.PsfFitParameter
                 The parameter object, containing name, value and unit
             row_grid: int
                 The row for the grid geometry manager to place the widgets on
         """
        # Generate a name label in column 0
        name_label = tk.Label(parent,
                              text=parameter.name,
                              font=("Arial", self.winfo_toplevel().font_size),
                              anchor=tk.E
                              )
        name_label.grid(row=row_grid, column=0, sticky=tk.E, padx=2, pady=2)

        # Generate a value entry in column 1
        value_entry = tk.Entry(parent, textvariable=parameter.value,
                               font=("Arial", self.winfo_toplevel().font_size),
                               width=5,
                               justify=tk.RIGHT
                               )
        value_entry.grid(row=row_grid, column=1, padx=2, pady=2)

        # Generate a unit label in column 2
        unit_label = tk.Label(parent, text=parameter.unit,
                              font=("Arial", self.winfo_toplevel().font_size),
                              anchor=tk.E
                              )
        unit_label.grid(row=row_grid, column=2, sticky=tk.E, padx=2, pady=2)


class ImageFrame(tk.Frame):
    """
    The middle frame in the GUI. Shows xy and xz sections of the PSF with attached sliders. Displays the PR Algorithm
    results and convergence.

        Arguments
        ----------
        parent: _tkinter.tkapp
            The parent (tk.Root)
    """
    class PsfFrame(tk.LabelFrame):
        """
            Displays xy and xz sections of the loaded PSF.
            The sliders can be used to preview different planes of the PSF

                Arguments
                ----------
                parent: tk.Frame
                   The parent frame (tk.Frame)
                label_text: string
                    The tk.LabelFrame description

                Attributes
                -----------
                self.zpos: tk.IntVar
                    The z current position within the stack
                self.ypos: tk.IntVar
                    The y current position within the stack
        """
        def __init__(self, parent, label_text):
            tk.LabelFrame.__init__(self, parent, text=label_text)

            # Track the position of the slider
            self.zpos = tk.IntVar()
            self.zpos.set(0)
            self.ypos = tk.IntVar()
            self.ypos.set(0)
            self.widgets()

        def widgets(self):
            # Initially create placeholder images, as long as no PSF has been loaded, create the sliders
            self.psf_xy_figure = self.create_placeholder_psf()
            self.psf_xy_figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
            self.zstack_slider = tk.Scale(self,
                                          label="Z Position",
                                          orient=tk.HORIZONTAL,
                                          font=("Arial", self.winfo_toplevel().font_size),
                                          variable=self.zpos,
                                          state=tk.DISABLED,
                                          name='z-slider'
                                          )
            self.zstack_slider.bind("<ButtonRelease-1>", self.update_psf)
            self.zstack_slider.grid(row=1, column=0, sticky=tk.W + tk.E, padx=5, pady=5)

            self.psf_xz_figure = self.create_placeholder_psf()
            self.psf_xz_figure._tkcanvas.grid(row=0, column=1, padx=5, pady=5)
            self.ypos_slider = tk.Scale(self,
                                        label="Y Position",
                                        orient=tk.HORIZONTAL,
                                        font=("Arial", self.winfo_toplevel().font_size),

                                        variable=self.ypos,
                                        state=tk.DISABLED,
                                        name='y-slider'
                                        )
            self.ypos_slider.bind("<ButtonRelease-1>", self.update_psf)
            self.ypos_slider.grid(row=1, column=1, sticky=tk.W + tk.E, padx=5, pady=5)

        def create_placeholder_psf(self):
            """
            Creates a placeholder PSF figure.

                Returns
                --------
                psf_dummy_figure: FigureCanvasTkAgg
            """
            psf_dummy = plt.figure(figsize=(6, 6), dpi=self.winfo_toplevel().figure_dpi)
            psf_dummy.text(0.5, 0.5, "No PSF has been loaded.", fontname='Arial', fontsize=16,
                           horizontalalignment='center')
            psf_dummy_figure = FigureCanvasTkAgg(psf_dummy, master=self)
            plt.close(psf_dummy)
            return psf_dummy_figure

        def update_psf(self, event, z_position=None, y_position=None):
            """
            Update the current displayed image of the PSF at the current section and updates the image streams.

                Arguments
                ----------
                event: tk.Event
                    If triggered by <ButtonRelease-1> on a stack slider, None if triggered initially
                    after PSF has been loaded
                z_position: int
                    Position in the stack, from which the psf image is created
                y_position: int
                    Position in the stack, from which the psf image is created

                Returns
                ---------
                psf_figure: FigureCanvasTkAgg
            """

            def __update_it(psf_view, zpos=None, ypos=None, aspect=1):

                if psf_view == 'xy':
                    # track old psf figure, create a new one and then destroy old one
                    # (needed to remove geometry manager jumping around)
                    obsolete_canvas = self.psf_xy_figure
                    self.psf_xy_figure = __create_psf(psf_view, zpos)
                    self.psf_xy_figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
                if psf_view == 'xz':
                    obsolete_canvas = self.psf_xz_figure
                    self.psf_xz_figure = __create_psf(psf_view, ypos, aspect)
                    self.psf_xz_figure._tkcanvas.grid(row=0, column=1, padx=5, pady=5)

                obsolete_canvas._tkcanvas.destroy()

            def __create_psf(psf_view, current_stack_pos, voxel_aspect=1):
                """
                Creates an image (FigureCanvasTkAgg)  of the PSF at the current section and updates the image stream.

                    Arguments
                    ----------
                    current_stack_pos: int
                        Position in the stack, from which the image is created

                    Returns
                    ---------
                    psf_figure: FigureCanvasTkAgg
                """
                # Create the matplotlib.Figure and configure it
                psf = plt.figure(figsize=(6, 6), dpi=self.winfo_toplevel().figure_dpi)
                psf_ax = psf.add_axes([0, 0, 1, 1])
                psf_ax.xaxis.set_visible(False)
                psf.patch.set_facecolor('black')

                # Create the requested image and store it in its image stream
                if psf_view == 'xy':
                    psf_ax.matshow(self.winfo_toplevel().psf_fit_parameters.psf_data[int(current_stack_pos)],
                                   cmap="inferno"
                                   )
                    self.winfo_toplevel().image_streams.reset_image_stream(self.winfo_toplevel().image_streams.
                                                                           psf_image_stream_xy,
                                                                           psf,
                                                                           )
                if psf_view == 'xz':
                    psf_ax.matshow(self.winfo_toplevel().psf_fit_parameters.psf_data[:, int(current_stack_pos), :],
                                   cmap="inferno",
                                   aspect=voxel_aspect
                                   )
                    self.winfo_toplevel().image_streams.reset_image_stream(self.winfo_toplevel().image_streams.
                                                                           psf_image_stream_xz,
                                                                           psf,
                                                                           )
                    # Create the image for display and return it
                psf_figure = FigureCanvasTkAgg(psf, master=self)
                plt.close(psf)
                return psf_figure

            # initial update after PSF file has been loaded, update both PSF images
            if event is None:
                __update_it('xy', zpos=z_position)
                self.zstack_slider.configure(state=tk.NORMAL, to=self.winfo_toplevel().psf_fit_parameters.z_size - 1)

                __update_it('xz', ypos=y_position, aspect=self.winfo_toplevel().psf_fit_parameters.voxel_aspect)
                self.ypos_slider.configure(state=tk.NORMAL, to=self.winfo_toplevel().psf_fit_parameters.xy_size - 1)

            # One of the sliders have been moved, update the corresponding PSF image
            else:
                # get current position of the slider
                stack_position = event.widget.get()

                # update the corresponding PSF image
                if event.widget == self.zstack_slider:
                    __update_it('xy', zpos=stack_position)
                if event.widget == self.ypos_slider:
                    __update_it('xz', ypos=stack_position)

    def __init__(self, parent, ):
        tk.Frame.__init__(self, parent)
        self.widgets()

    def widgets(self):
        # This frame displays xy and xz sections of the loaded PSF file, and sliders to change the section
        self.psf_frame = self.PsfFrame(self, "PSF preview")
        self.psf_frame.grid(row=0, column=0, padx=5, pady=5)

        # This frame displays the results of the PR Algorithm
        self.pr_result_frame = ResultFrame(self,
                                           'Phase Retrieval Results',
                                           'No phase retrieval results yet.',
                                           figure_width=12,
                                           figure_height=5,
                                           )
        self.pr_result_frame.grid(row=1, column=0, padx=5, pady=5, sticky=tk.E+tk.W)

        # This frame displays the PR Algorithm convergence
        self.pr_mse_frame = ResultFrame(self,
                                        'Phase Retrieval Error',
                                        'No phase retrieval results yet.',
                                        figure_width=12,
                                        figure_height=3,
                                        )
        self.pr_mse_frame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.E+tk.W)


class ZernikeFrame(tk.Frame):
    """
    The right frame in the GUI. Displays the results of the Zernike Decomposition graphically and as discrete values.
    Allows to save the results images, the Zernike Decomposition results as .csv,
    and generate a comprehensive pdf report.

        Arguments
        ----------
        parent: _tkinter.tkapp
            The parent (tk.Root)
    """
    class ZernikeCoefficientFrame(tk.LabelFrame):
        """
        Displays the results of the Zernike Decomposition as discrete values. Generates a list of
        Zernike Polynomials, with name, phase coefficient value

            Arguments
            ----------
            parent: _tkinter.tkapp
                The parent (tk.Root)
        """

        def __init__(self, parent, label_text):
            tk.LabelFrame.__init__(self, parent, text=label_text)
            self.widgets()

        def widgets(self):
            # Generate an entry for each Zernike Polynomial
            rows = range(0, len(self.winfo_toplevel().zernike_results.zernike_polynomials))
            for row, polynomial in zip(rows, self.winfo_toplevel().zernike_results.zernike_polynomials):
                # Set the font to bold for the "important" polynomials
                if polynomial.order in self.winfo_toplevel().zernike_results.important_coeff_orders:
                    temp_label = tk.Label(self,
                                          text=polynomial.name,
                                          font=("Arial", self.winfo_toplevel().font_size, 'bold'),
                                          anchor=tk.E
                                          )
                else:
                    temp_label = tk.Label(self,
                                          text=polynomial.name,
                                          font=("Arial", self.winfo_toplevel().font_size),
                                          anchor=tk.E
                                          )
                temp_label.grid(row=row, column=0, sticky=tk.E, pady=2)

                # Format the phase coefficient value, make it bold if "important"
                value_string = '  {:.2f}'.format(polynomial.value)
                if polynomial.order in self.winfo_toplevel().zernike_results.important_coeff_orders:
                    temp_label = tk.Label(self,
                                          text=value_string,
                                          font=("Arial", self.winfo_toplevel().font_size, 'bold'),
                                          anchor=tk.E
                                          )
                else:
                    temp_label = tk.Label(self,
                                          text=value_string,
                                          font=("Arial", self.winfo_toplevel().font_size),
                                          anchor=tk.E
                                          )
                temp_label.grid(row=row, column=1, sticky=tk.E)

                # If no results yet, in_tolerance is None --> don't display it
                if polynomial.in_tolerance is not None:
                    if polynomial.in_tolerance:
                        temp_label = tk.Label(self,
                                              text='OK!',
                                              font=("Arial", self.winfo_toplevel().font_size),
                                              fg='green'
                                              )
                    else:
                        temp_label = tk.Label(self,
                                              text='Not OK!',
                                              font=("Arial", self.winfo_toplevel().font_size),
                                              fg='red'
                                              )
                    temp_label.grid(row=row, column=2)

        def update_entries(self):
            # To update, destroy all label entries and recreate
            for widget in self.winfo_children():
                widget.destroy()
            self.widgets()

    class ResultButtonFrame(tk.LabelFrame):
        """
        Buttons to save the results of the PR Algorithm, and the Zernike Decomposition.

           Arguments
           ----------
           parent: tk.Frame
               The parent frame (tk.Frame)
        """

        def __init__(self, parent, label_text):
            tk.LabelFrame.__init__(self, parent, text=label_text)
            self.widgets()

        def widgets(self):
            # Check if the PR Algorithm has finished or been restarted, activate or deactivate report buttons
            self.winfo_toplevel().pr_state.pr_finished.trace('w', self.toggle_buttons)

            # Buttons to trigger the saving functions
            self.save_pr_result_button = tk.Button(self,
                                                   text="Phase & Magnitude as .png",
                                                   command=self.save_pr_image,
                                                   )
            self.save_pr_result_button.grid(row=0, column=0, padx=5, pady=5, )

            self.save_zernike_img_button = tk.Button(self,
                                                     text="Zernike Coeff. as .png",
                                                     command=self.save_zd_image,
                                                     )
            self.save_zernike_img_button.grid(row=1, column=0, padx=5, pady=5, )

            self.save_zernike_values_button = tk.Button(self,
                                                        text="Save fit results as .xlsx",
                                                        command=self.save_zd_values,
                                                        )
            self.save_zernike_values_button.grid(row=0, column=1, padx=5, pady=5, )

            self.save_pdf_report = tk.Button(self,
                                             text="Create pdf report",
                                             command=self.generate_pdf_report,
                                             )
            self.save_pdf_report.grid(row=1, column=1, padx=5, pady=5, )

            for child_button in self.winfo_children():
                child_button.configure(font=("Arial", self.winfo_toplevel().font_size),
                                       state=tk.DISABLED,
                                       width=23
                                       )

        def toggle_buttons(self, n, m, x):
            """
            Switches the button to active when the PR Algorithm has finished, to inactive when a new PSF has been loaded.

            Arguments
            ----------
            n: string or list
               The internal name of the variable which was changed, or as list of variabels
            m: int or ""
                Index for name list or empty string
            x: string
                What operation triggered the trace: 'w': write, 'r': read or 'u': delete
            """
            for child in self.winfo_children():
                if self.winfo_toplevel().pr_state.pr_finished.get():
                    child.configure(state=tk.NORMAL)
                else:
                    child.configure(state=tk.DISABLED)

        def save_pr_image(self):
            """ Save the phase and magnitude images from the image stream to the disk. """
            save_file = os.path.join(self.winfo_toplevel().result_directory.get(),
                                     os.path.splitext(self.winfo_toplevel().psf_filename)[0] + '_pr_results.png')
            try:
                with open(save_file, "wb") as f:
                    f.write(self.winfo_toplevel().image_streams.pr_result_image_stream.getvalue())
            except FileNotFoundError as pop_up_alert:
                messagebox.showwarning("Invalid File Path", str(pop_up_alert))

        def save_zd_image(self):
            """ Save the graphical results of the Zernike Decomposition from the image stream to the disk. """
            save_file = os.path.join(self.winfo_toplevel().result_directory.get(),
                                     os.path.splitext(self.winfo_toplevel().psf_filename)[0] + '_zd_results.png')
            try:
                with open(save_file, "wb") as f:
                    f.write(self.winfo_toplevel().image_streams.zd_decomposition_image_stream.getvalue())
            except FileNotFoundError as pop_up_alert:
                messagebox.showwarning("Invalid File Path", str(pop_up_alert))

        def save_zd_values(self):
            """ Save the Results of the Zernike Decomposition and the parameters
                for the PSF and the PR Fit to a .xlsx file.
            """
            xlsx_path = os.path.join(self.winfo_toplevel().result_directory.get(),
                                     os.path.splitext(self.winfo_toplevel().psf_filename)[0] + '_zd_results.xlsx')
            try:
                TrackingClasses.ZdResultWorkbook(xlsx_path,
                                                 self.winfo_toplevel().psf_file.get(),
                                                 self.winfo_toplevel().zernike_results,
                                                 self.winfo_toplevel().pr_state,
                                                 psf_fit_parameters=self.winfo_toplevel().psf_fit_parameters,
                                                 )
            except Exception as pop_up_alert:
                messagebox.showwarning("Saving results as .xlsx failed", str(pop_up_alert))

        def generate_pdf_report(self):
            """ Generate a pdf report with all results and save it."""
            pdf_path = os.path.join(self.winfo_toplevel().result_directory.get(),
                                    os.path.splitext(self.winfo_toplevel().psf_filename)[0] + '_report.pdf')

            pdf_report = TrackingClasses.PdfReport(pdf_path,
                                                   self.winfo_toplevel().psf_file.get(),
                                                   self.winfo_toplevel().psf_fit_parameters,
                                                   self.winfo_toplevel().zernike_results,
                                                   self.winfo_toplevel().image_streams,
                                                   self.winfo_toplevel().pr_state
                                                   )
            try:
                pdf_report.create_pdf_report()
            except Exception as pop_up_alert:
                messagebox.showwarning("Creating a .pdf-report failed", str(pop_up_alert))

    def __init__(self, parent):
        tk.Frame.__init__(self, parent)
        self.widgets()

    def widgets(self):
        # Generate a result frame which displays the results of the Zernike Decomposition
        self.zernike_frame = ResultFrame(self,
                                         'Zernike Decomposition Results',
                                         'No zernike decomposition results yet.',
                                         figure_width=6,
                                         figure_height=6
                                         )
        self.zernike_frame.grid(row=0, column=0, padx=5, pady=5)

        # Lists the named Zernike polynomials and their phase coefficients
        self.coefficient_frame = self.ZernikeCoefficientFrame(self, "Decomposed Zernike Coefficients")
        self.coefficient_frame.grid(row=1, column=0, padx=5, pady=5, sticky=tk.E+tk.W)

        # Buttons to save the results
        self.result_button_frame = self.ResultButtonFrame(self, "Save Results")
        self.result_button_frame.grid(row=2, column=0, padx=5, pady=5, sticky=tk.E+tk.W)


class ResultFrame(tk.LabelFrame):
    """
    LabelFrame which displays a matplotlib.pyplot.Figure on the GUI. It is initialized with a placeholder figure.

        Arguments
        ----------
        parent: tk.Frame
           The parent frame (tk.Frame)
        label_text: string
            The tk.LabelFrame description
        placeholder_text: string
            The placeholder text displayed after initialization.
        figure_width: int
            plt.Figure width in inches
        figure_height: int
            plt.Figure height in inches

        Attributes
        -----------
        self.figure: FigureCanvasTkAgg
            The current displayed figure
    """
    def __init__(self, parent, label_text, placeholder_text, figure_width=None, figure_height=None):
        tk.LabelFrame.__init__(self, parent, text=label_text)
        self.placeholder_text = placeholder_text
        self.figure_width = figure_width
        self.figure_height = figure_height
        self.initiate()

    def initiate(self):
        """ Generate a placeholder figure of the appropriate size and resolution. """
        white_space = plt.figure(figsize=(self.figure_width, self.figure_height), dpi=self.winfo_toplevel().figure_dpi)
        white_space.text(0.5, 0.5, self.placeholder_text, fontname='Arial', fontsize=16, horizontalalignment='center')
        self.figure = FigureCanvasTkAgg(white_space, master=self)
        self.figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        plt.close(white_space)

    def show_results(self, result_figure):
        """ Replace the current figure.

            Arguments
            ---------
            result_figure: plt.Figure
        """
        obsolete_canvas = self.figure
        self.figure = FigureCanvasTkAgg(result_figure, master=self)
        self.figure._tkcanvas.grid(row=0, column=0, padx=5, pady=5)
        obsolete_canvas._tkcanvas.destroy()
        plt.close(result_figure)

    def reset(self):
        """ Replace the current figure wit a placeholder figure. """
        obsolete_canvas = self.figure
        self.initiate()
        obsolete_canvas._tkcanvas.destroy()


class MainWindow(tk.Tk):
    """ The tk.root for the GUI.

        Arguments
        ----------
        screen_height: int
            Actual screen height after windows scaling
        scaling_factor: int
            Scaling factor set for the screen by Windows
    """
    def __init__(self, screen_height, scaling_factor):
        tk.Tk.__init__(self)

        # start a JVM, needed to run the bioformats class used in bioformats_helper.PsfImageDataAndParameters
        javabridge.start_vm(class_path=bioformats.JARS)

        # Set up the main window and font size and figure resolution according to the screen resolution
        # TODO: test this for different environments
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
        self.psf_filename = ""
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
        self.left_frame = ParameterFrame(self)
        self.left_frame.grid(row=0, column=0, sticky=tk.N)
        self.middle_frame = ImageFrame(self)
        self.middle_frame.grid(row=0, column=1, sticky=tk.N)
        self.right_frame = ZernikeFrame(self)
        self.right_frame.grid(row=0, column=2, sticky=tk.N)

    def select_psf_file(self):
        """ Open a filedialog to select a PSF file, store it"""
        psf_path = filedialog.askopenfilename(initialdir=self.psf_directory,
                                              title="Select PSF file..."
                                              )
        self.psf_file.set(psf_path)
        psf_dir, self.psf_filename = os.path.split(psf_path)
        self.psf_directory.set(psf_dir)

    def select_result_dir(self):
        """ Open a filedialog to select a result directory, store it"""
        self.result_directory.set(filedialog.askdirectory(initialdir=self.psf_directory,
                                                          title="Select result directory...",
                                                          )
                                  )

    def load_psf_file(self):
        """
        Linked to the self.left_frame.action_button_frame.load_psf_button . Loads the PSF parameters and PSF data
            from the selected file and displays the data (self.middle_frame.psf_frame)
        """
        # Load the PSF file store parameters and data
        self.psf_fit_parameters.read_data_and_parameters(self.psf_file.get())

        # If loading the PSF was successful...
        if self.psf_fit_parameters.is_initiated:
            # ...display PSF on the GUI and initialize the sliders
            starting_zpos = self.psf_fit_parameters.z_size // 2
            self.middle_frame.psf_frame.zpos.set(starting_zpos)
            starting_xypos = self.psf_fit_parameters.xy_size // 2
            self.middle_frame.psf_frame.ypos.set(starting_xypos)

            # Also triggered by changes of the sliders --> tk.Event
            self.middle_frame.psf_frame.update_psf(None, z_position=starting_zpos, y_position=starting_xypos)

            # ...reset the stored results in case there was a previous Phase Retrieval Algorithm run
            self.phase_retrieval_results.reset_pr_result()
            self.zernike_results.initialize_polynomial_list()

            # ... reset the GUI display
            self.middle_frame.pr_result_frame.reset()
            self.middle_frame.pr_mse_frame.reset()
            self.right_frame.zernike_frame.reset()
            self.right_frame.coefficient_frame.update_entries()

    def initiate_pr(self):
        """
        Linked to the self.left_frame.action_button_frame.pr_button . Checks, whether all parameters for the
            Phase Retrieval Algorithm are set, resets the current state of the GUI and the internals, starts the
            algorithm in its own thread, reconfigures the button to allow stopping the the thread and starts monitoring
            the current state of the thread
        """
        # Check if all parameters are set
        if self.psf_fit_parameters.verify():
            # Reset internals and GUI display
            self.pr_state.reset_state()
            self.middle_frame.pr_result_frame.reset()
            self.middle_frame.pr_mse_frame.reset()
            self.right_frame.zernike_frame.reset()
            self.zernike_results.initialize_polynomial_list()
            self.right_frame.coefficient_frame.update_entries()

            # Initialize the Phase Retrieval Thread and start it
            self.pr_thread = phaseretrieval_gui.PhaseRetrievalThreaded(self.psf_fit_parameters.psf_data_prepped,
                                                                       self.psf_fit_parameters.psf_parameter_dict,
                                                                       self.pr_state,
                                                                       self.phase_retrieval_results,
                                                                       **self.psf_fit_parameters.fit_parameter_dict,
                                                                       )
            self.pr_thread.daemon = True
            self.pr_thread.start()

            # Reconfigure the Phase Retrieval Button to allow to stop the thread
            self.left_frame.action_button_frame.pr_button.configure(text="Stop Phase Retrieval", command=self.stop_pr)
            self.pr_state.current_state.set("Phase retrieval running...")

            # After 250 ms call the monitoring function
            self.after(250, self.check_pr_results)

    def check_pr_results(self):
        """
        Checks every 250 ms, whether phaseretrieval_gui.PhaseRetrievalThreaded is still running. If the thread
            is not alive(finished or has been aborted), update the GUI display, reset the PR_button to allow the start
            of the next Phase Retrieval Algorithm.
            Calls itself, if the thread is still running and updates the GUI display every five iterations.
        """
        # Check if the algorithm is still running
        if self.pr_thread.is_alive():
            self.left_frame.status_frame.update()
            self.after(250, self.check_pr_results)

            # Update the GUI every five iterations
            if self.pr_state.current_iter.get() > 0 and self.pr_state.current_iter.get() % 5 == 0:
                self.display_pr_results()

        # If the thread has stopped, update the GUI display and reset the Phase Retrieval Button
        else:
            self.display_pr_results()
            self.display_zd_results()

            # Also triggered by traced variable changes, which call it with three arguments
            self.left_frame.status_frame.update_status(None, None, None)
            self.left_frame.action_button_frame.pr_button.configure(text="Start Phase Retrieval",
                                                                    command=self.initiate_pr)
            self.pr_state.pr_finished.set(True)

    def display_pr_results(self):
        """ Generates figures from the Phase Retrieval Algorithm Results and the differences in pupil function and mse.
            Stores the figures in the image streams and updates the GUI display
        """
        # Create the Phase Retrieval result figure, store it as a byte stream and update GUI display
        result_figure, _ = self.phase_retrieval_results.plot_gui(self.figure_dpi)
        self.image_streams.reset_image_stream(self.image_streams.pr_result_image_stream, result_figure)
        self.middle_frame.pr_result_frame.show_results(result_figure)

        # Plot the errors in a figure, store it as a byte stream and update GUI display
        mse_figure, _ = self.phase_retrieval_results.plot_convergence_gui(self.figure_dpi,
                                                                          self.psf_fit_parameters.
                                                                          max_iterations.value.get())
        self.image_streams.reset_image_stream(self.image_streams.pr_fiterror_image_stream, mse_figure)
        self.middle_frame.pr_mse_frame.show_results(mse_figure)

    def display_zd_results(self):
        """ Generate a figure from the Zernike Decomposition REsult, store the figure in the image streams and
            update the GUI display
        """
        # Do the Zerniken Decomposition
        self.phase_retrieval_results.fit_to_zernikes(120)

        # Create the Zernike Decomposition result figure, store it as a byte stream and update GUI display
        zernike_figure, _ = self.phase_retrieval_results.zd_result.plot_named_coefs_gui(self.figure_dpi)
        self.image_streams.reset_image_stream(self.image_streams.zd_decomposition_image_stream, zernike_figure)
        self.right_frame.zernike_frame.show_results(zernike_figure)

        self.zernike_results.decomposition_from_phase_retrieval(self.phase_retrieval_results, self.psf_fit_parameters.
                                                                phase_tolerance.value.get())
        self.right_frame.coefficient_frame.update_entries()

    def stop_pr(self):
        """Sets the stop_pr flag, breaks out of the iteration loop in phaseretrieval_gui.PhaseRetrievalThreaded"""
        self.pr_thread.stop_pr.set()

    def clean_up(self):
        """Ensures that the JVM is killed, before tk.root is destroyed"""
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
