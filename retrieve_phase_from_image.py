import os
import time

import bioformats_helper

from pyOTF import phaseretrieval
from pyOTF import utils

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk


# phase retrieve a pupil

# read in data from fixtures
# data = tif.imread(os.path.split(__file__)[0] + "/fixtures/psf_wl520nm_z200nm_x52nm_na1.4_n1.518.tif")

# read in data from microscopy image
file_path = 'D:\\Python_projects\\phase_retrieval\\test\\'
file_name = 'LSM880_12092017_25xOil_green_x0_Y0_1.czi'

data = bioformats_helper.PsfImageDataAndParameters(os.path.join(file_path, file_name))

image_data = data.image_data

# prep data
data_prepped = utils.prep_data_for_PR(image_data, data.image_size_xy * 2)
# set up model params
params = dict(
    wl=530,
    na=0.8,
    ni=1.518,
)
params['res'] = data.pixel_size_xy
params['zres'] = data.pixel_size_z

# retrieve the phase
pr_start = time.time()
print("Starting phase retrieval")
pr_result = phaseretrieval.retrieve_phase(data_prepped, params)
print("It took {} seconds to retrieve the pupil function".format(
    time.time() - pr_start))
# plot
results, _ = pr_result.plot()
result_name = file_name[:-4] + '_result.png'
results.savefig(os.path.join(file_path, result_name))

convergence, _ = pr_result.plot_convergence()
convergence_name = file_name[:-4] + '_convergence.png'
convergence.savefig(os.path.join(file_path, convergence_name))

mse, _ = pr_result.plot_mse()
mse_name = file_name[:-4] + '_mse.png'
mse.savefig(os.path.join(file_path, mse_name))

# fit to zernikes
zd_start = time.time()
print("Starting zernike decomposition")
pr_result.fit_to_zernikes(120)
print("It took {} seconds to fit 120 Zernikes".format(
    time.time() - zd_start))

# simulated_psf = pr_result.generate_psf()
# simulated_psf = simulated_psf.astype(np.uint16)
# psf_name = file_name[:-4] + '_psf.tif'
# #tif.imsave(os.path.join(file_path, psf_name), simulated_psf)
# with tif.TiffWriter(os.path.join(file_path, psf_name), byteorder='>', imagej=True) as tif:
#     for i in range(simulated_psf.shape[0]):
#         tif.save(simulated_psf[i])


zernike, _ = pr_result.zd_result.plot_named_coefs()
zernike_name = file_name[:-4] + '_zernike.png'
zernike.savefig(os.path.join(file_path, zernike_name))

# pr_result.zd_result.plot_coefs()



root = tk.Tk()
root.title("Sinus vs. Cosinus")

canvas = FigureCanvasTkAgg(results, master=root)
canvas._tkcanvas.pack(side=tk.TOP, fill=tk.BOTH, expand=1)

root.mainloop()