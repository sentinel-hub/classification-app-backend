"""
Module containing utils for processing images
"""

import base64
import io
import numpy as np

from PIL import Image


MASK_THRESHOLD = 100


def merge_images(images, colors):
    merged_image = np.zeros(images[0].shape[:2] + (3,), dtype=np.uint8)

    for image, color in zip(images, colors):
        merged_image[image[..., 0] >= MASK_THRESHOLD, :] = hex_to_rgb(color)

    return merged_image


def hex_to_rgb(hex_color):
    hex_color = hex_color.strip('#')
    return np.array(list(int(hex_color[i: i + 2], 16) for i in (0, 2, 4)))


def encode_image(np_image):
    """ Transforms numpy image into bytes
    """
    if np_image.dtype != np.uint8:
        raise ValueError('Classification mask numpy array must have type numpy.uint8')

    if len(np_image.shape) == 2:
        np_image = np.stack((np_image,) * 3, -1)

    channels = np_image.shape[-1]
    if len(np_image.shape) != 3 or channels not in [3, 4]:
        raise ValueError('Image must have 3 or 4 channels, got {} channels'.format(channels))

    image = Image.fromarray(np_image, 'RGB' if channels == 3 else 'RGBA')
    bio = io.BytesIO()
    image.save(bio, format='png')
    return base64.b64encode(bio.getvalue()).decode('utf-8')
