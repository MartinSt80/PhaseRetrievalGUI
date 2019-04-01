#!/usr/bin/env python
# -*- coding: utf-8 -*-
# bioformats_helper.py
"""
Extracts the necessary image parameters and the image data from ome-tiffs or bioformats supported image formats.

Copyright (c) 2019, Martin Stoeckl
"""

import javabridge
import bioformats
import numpy as np
import imghdr
import imageio
import xml.etree.ElementTree as ET


class PsfImageDataAndParameters:

    # map refractive indices to immersion keywords
    immersion_to_ri = {'oil': 1.518,
                       'glycerol': 1.472,
                       'water': 1.333,
                       'air': 1.,
                       }

    def __init__(self, image_path):
        self.pixel_size_xy = 0
        self.pixel_size_z = 0
        self.image_size_xy = 0
        self.image_size_z = 0
        self.numerical_aperture = 0.
        self.refractive_index = 0.
        self.image_data = None
        self.read_psf_params_and_data(image_path)


    def read_psf_params_and_data(self, image_path):
        """Extract the image parameters and data from a supported PSF image

                Parameters
                ----------
                image_path : string
                    Full path to the PSF image file

                Sets the class attributes
                -------
                self.pixel_size_xy : int
                    x/y-size of a voxel in nm
                self.pixel_size_z : int
                    z-size of a voxel in nm
                self.image_size_xy : int
                    x/y-size of the PSF image
                self.image_size_z : int
                    z-size of the PSF image
                self.numerical_aperture : float
                    Numerical aperture of the objective
                self.refractive_index : float
                    Refractive index of the immersion medium
                self.psf_data : np.ndarray (3 dim)
                    The measured intensities of a PSF
        """

        # Check file format, bioformats compatible microscopy images and ome-tiffs supported
        file_format = imghdr.what(image_path)

        if file_format == 'tiff':
            # .lsm images return "tiff" as file_format, read with bioformats anyway
            if image_path.endswith('.lsm'):
                javabridge.attach()
                try:
                    metadata = bioformats.get_omexml_metadata(image_path, )
                except:
                    raise AssertionError('File format not supported')
                finally:
                    javabridge.detach()

            # read tiff-metadata and extract "description" tag, in case of ome-tif it is OME compliant
            else:
                with imageio.get_reader(image_path) as tiff_reader:
                    metadata = tiff_reader.get_meta_data()
                metadata = metadata['description']
                assert metadata is not None, 'Only OME-tif file format is supported'

        # not a tiff image, but a ome-bioformats supported container
        else:
            javabridge.attach()
            try:
                metadata = bioformats.get_omexml_metadata(image_path,)
            except:
                raise AssertionError('File format not supported')
            finally:
                javabridge.detach()

        # parse metadata string
        ome_xml = bioformats.OMEXML(metadata)

        # Retrieve information about the image
        ome_pixel_information = ome_xml.image(0).Pixels

        # assert pixels and images are square, pixels are scaled and the unit is recognizable
        assert ome_pixel_information.PhysicalSizeX == ome_pixel_information.PhysicalSizeY, \
            'Identical pixel size required for X and Y'

        assert ome_pixel_information.PhysicalSizeXUnit in ('um', 'µm', 'micron', 'nm'), \
            'Unit of pixel size not recognized: Must be um, µm, micron or, nm)'

        assert ome_pixel_information.PhysicalSizeZUnit in ('um', 'µm', 'micron', 'nm'), \
            'Unit of z-step not recognized: Must be um, µm, micron or, nm)'

        assert ome_pixel_information.SizeC == 1 and ome_pixel_information.SizeT == 1, \
            'Only single channel images  and no time series are supported'

        assert ome_pixel_information.SizeX == ome_pixel_information.SizeY, \
            'Images with equal pixel numbers for X and Y are required'

        # Get pixel size, convert to nm
        px_size_xy = float(ome_pixel_information.PhysicalSizeX)
        if ome_pixel_information.PhysicalSizeXUnit in ('um', 'µm', 'micron'):
            px_size_xy *= 1000
        self.pixel_size_xy = int(px_size_xy)

        # Get z step, convert to nm
        px_size_z = float(ome_pixel_information.PhysicalSizeZ)
        if ome_pixel_information.PhysicalSizeZUnit in ('um', 'µm', 'micron'):
            px_size_z *= 1000
        self.pixel_size_z = int(px_size_z)

        # Get image / stack size
        self.image_size_xy = int(ome_pixel_information.SizeX)
        self.image_size_z = int(ome_pixel_information.SizeZ)

        # Retrieve information about the objective
        ome_instrument_information = ome_xml.instrument()

        # Get the numerical aperture of the objective
        na = float(ome_instrument_information.Objective.LensNA)
        if na >= 1:
            self.numerical_aperture = round(na, 3)
        else:
            self.numerical_aperture = round(na, 2)

        # Refractive index / Immersion is not part of the ome_xml.instrument() model, parse xml with ET
        ome_root = ET.fromstring(metadata)

        # search parsed xml, for refractive index or immersion (convert to refractive index)
        for element in ome_root:
            if 'Image' in element.tag:
                for sub_element in element:
                    if 'ObjectiveSettings' in sub_element.tag:
                        refr_index = sub_element.get('RefractiveIndex')
                        if refr_index is not None:
                            self.refractive_index = float(refr_index)
                        else:
                            for element in ome_root:
                                if 'Instrument' in element.tag:
                                    for sub_element in element:
                                        if 'Objective' in sub_element.tag:
                                            immersion = sub_element.get('Immersion')
                                            if immersion is not None:
                                                try:
                                                    self.refractive_index = self.immersion_to_ri[immersion.lower()]
                                                except KeyError:
                                                    pass
        # store image data in a numpy array
        temp_data = []
        with bioformats.ImageReader(image_path) as reader:
            for z_pos in range(self.image_size_z):
                temp_data.append(reader.read(c=0, z=z_pos, rescale=False))
        self.image_data = np.asarray(temp_data)



