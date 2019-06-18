"""
This module contains utility functions for sampling
"""

import random
import shapely.affinity
import shapely.ops

from shapely.geometry import Polygon, MultiPolygon

from sentinelhub import BBox

from eolearn.geometry import PointSampler


def random_sample(geo_shape, window_shape):
    """ Samples any geometrical shape with a rectangular window. The sampled window will have integer coordinates
    """
    subgeo_shape = minkowski_difference(geo_shape, window_shape)

    if not subgeo_shape:
        raise ValueError('You cannot sample the area with so large window size')

    x, y = random_sample_point(subgeo_shape, use_int_coords=True)

    return Polygon([(x, y), (x + window_shape[0], y),
                    (x + window_shape[0], y - window_shape[1]), (x, y - window_shape[1])])


def random_sample_point(geo_shape, triangles=None, use_int_coords=False):
    """
    :param geo_shape: Shapely geometry object
    :param triangles: Pre-calculated list of triangles to avoid recalculating them every time
    :param use_int_coords: Flag if return coordinates should be integer
    :return: x and y coordinates of a point sampled uniformly at random
    """
    if triangles is None:
        triangles = triangulate(geo_shape)

    # TODO: switch with random.choices(triangles, weights=[triangle.area for triangle in triangles], k=1)[0]
    # doesn't work in Python 3.5
    cumulative_areas = [0]
    for idx, triangle in enumerate(triangles):
        cumulative_areas.append(triangle.area + cumulative_areas[idx])

    sample_tries = 10  # We are sampling integer points but there might not be any
    while sample_tries:
        triangle_index = _binary_search(cumulative_areas, random.random() * cumulative_areas[-1])

        point = PointSampler.random_point_triangle(triangles[triangle_index], use_int_coords=use_int_coords)

        if geo_shape.intersects(point):
            return point.coords.xy[0][0], point.coords.xy[1][0]

        sample_tries -= 1

    raise ValueError('Failed to sample the area{}'.format(' with a window that has integer coordinates'
                                                          if use_int_coords else ''))


def minkowski_difference(geo_shape, window_shape):
    """ Calculates Minkowski difference of any geometrical shape and a rectangular window
    """
    if not geo_shape:
        return geo_shape

    area_hull = geo_shape.convex_hull
    area_diff = area_hull.difference(geo_shape)
    return convex_minkowski_difference(area_hull, window_shape).difference(minkowski_sum(area_diff, (-window_shape[0],
                                                                                                     -window_shape[1])))


def convex_minkowski_difference(geo_shape, window_shape):
    """ Calculates Minkowski difference of a convex geometrical shape and a rectangular window
    """
    translated_shapes = [shapely.affinity.translate(geo_shape, xoff=xoff, yoff=yoff)
                         for xoff, yoff in [(-window_shape[0], 0), (0, window_shape[1]),
                                            (-window_shape[0], window_shape[1])]]

    for translated_shape in translated_shapes:
        geo_shape = geo_shape.intersection(translated_shape)

    return geo_shape


def minkowski_sum(geo_shape, window_shape):
    """ Calculates Minkowski sum of any geometrical shape and a rectangular window
    """
    if not geo_shape:
        return geo_shape

    triangles = triangulate(geo_shape)
    shape_union = None
    for triangle in triangles:
        triangle_sum = convex_minkowski_sum(triangle, window_shape)
        if shape_union is None:
            shape_union = triangle_sum
        else:
            shape_union = shape_union.union(triangle_sum)
    return shape_union


def convex_minkowski_sum(geo_shape, window_shape):
    """ Calculates Minkowski sum of a convex geometrical shape and a rectangular window
    """
    return MultiPolygon([shapely.affinity.translate(geo_shape, xoff=xoff, yoff=yoff)
                         for xoff, yoff in [(0, 0), (window_shape[0], 0), (0, -window_shape[1]),
                                            (window_shape[0], -window_shape[1])]]).convex_hull


def triangulate(geo_shape):
    """ Triangulation of geometry

    Note that shapely.ops.triangulate actually triangulates convex hull of a polygon, that is why we need this
    function. And this function uses the fact that shapely.ops.triangulate performs Delaunay triangulation

    :param geo_shape: A polygon or multi-polygon
    :type geo_shape: shapely.geometry.Polygon or shapely.geometry.MultiPolygon
    :returns: A list of triangles
    :rtype: list(shapely.geometry.Polygon)
    """
    convex_poly_list = []
    for triangle in shapely.ops.triangulate(geo_shape):
        reduced_shape = triangle.intersection(geo_shape)

        if isinstance(reduced_shape, MultiPolygon):
            convex_poly_list.extend(list(reduced_shape))
        else:
            convex_poly_list.append(reduced_shape)

    convex_poly_list = [poly for poly in convex_poly_list if poly.area > 0]

    return [triangle for poly in convex_poly_list for triangle in shapely.ops.triangulate(poly)]


def _binary_search(increasing_list, value):
    """ Helper function for binary search in a list of increasing values
    """
    left = 0
    right = len(increasing_list) - 2

    while left < right:
        pivot = (left + right) // 2
        if increasing_list[pivot + 1] >= value:
            right = pivot
        else:
            left = pivot + 1

    return left


def random_sample_image(image, bbox, window_shape):
    """ Randomly sample geo-referenced image with a rectangular window shape
    """
    height, width = image.shape[:2]
    if window_shape[0] > width or window_shape[1] > height:
        raise ValueError('Cannot sample so small image')

    geo_shape = Polygon([(0, 0), (width, 0), (width, height), (0, height)])
    sampled_coords = list(map(int, random_sample(geo_shape, window_shape).bounds))

    return sample_image_with_window(image, bbox, sampled_coords)


def sample_image_with_bbox(image, bbox, reduced_coords, buffer=0):
    """ Randomly sample geo-referenced image with a bounding box
    """
    bbox_coords = list(bbox)
    reduced_coords = list(reduced_coords)

    height, width = image.shape[:2]
    resx, resy = get_resolution(image, bbox_coords)

    reduced_coords = [
        max(round((reduced_coords[0] - bbox_coords[0]) / resx - buffer), 0),
        max(round((reduced_coords[1] - bbox_coords[1]) / resy - buffer), 0),
        min(round((reduced_coords[2] - bbox_coords[0]) / resx + buffer), width),
        min(round((reduced_coords[3] - bbox_coords[1]) / resy + buffer), height)
    ]

    return sample_image_with_window(image, bbox, reduced_coords)


def sample_image_with_window(image, bbox, window_coords):
    """ Randomly sample geo-referenced image with a rectangular window
    """
    height = image.shape[0]
    bbox_coords = list(bbox)
    resx, resy = get_resolution(image, bbox_coords)

    return image[height - window_coords[3]: height - window_coords[1], window_coords[0]: window_coords[2], ...], \
        BBox([bbox_coords[0] + resx * window_coords[0], bbox_coords[1] + resy * window_coords[1],
              bbox_coords[0] + resx * window_coords[2], bbox_coords[1] + resy * window_coords[3]],
             crs=bbox.get_crs())


def get_resolution(image, bbox_coords):
    """ Get image resolution
    """
    height, width = image.shape[:2]
    return (bbox_coords[2] - bbox_coords[0]) / width, (bbox_coords[3] - bbox_coords[1]) / height


def count_points(geo_shape):
    """ Counts number of exterior points in geometrical shape
    """
    point_cnt = 0
    if isinstance(geo_shape, Polygon):
        geo_shape = [geo_shape]

    for poly_shape in geo_shape:
        point_cnt += len(poly_shape.exterior.coords)

    return point_cnt


def get_bbox_polygon(geo_shape):
    """ Returns a polygon which is a bounding box of given geometrical shape
    """
    bbox_coords = list(geo_shape.bounds)

    return Polygon([(bbox_coords[0], bbox_coords[1]), (bbox_coords[2], bbox_coords[1]),
                    (bbox_coords[2], bbox_coords[3]), (bbox_coords[0], bbox_coords[3])])
