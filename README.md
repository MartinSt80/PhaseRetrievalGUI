# PhaseRetrievalGUI
Graphical user interface (PR_applet_sized.py) for the phase retrieval algorithm, described by Hanser et al. 2004. The algorithm was implemented by David Hoffmanm (https://github.com/david-hoffman/). 
The graphical user interface allows to easily load PSF images from bioformats compatible files, preview the loaded PSF, track the phase retrieval progress and generate reports in .xlsx or pdf format.
In addition the command line tool (retrieve_phase_from_image.py) has been modified to accept bioformat compatible files and PSF or Fit parameters as arguments, creates .xlsx reports and tracks the progress.

# Needed dependencies
The modified [dphutils](https://github.com/MartinSt80/dphutils) and [pyOTF](https://github.com/MartinSt80/pyOTF) repositories (forked from https://github.com/david-hoffman/) are needed to run the GUI and the command line tool.

