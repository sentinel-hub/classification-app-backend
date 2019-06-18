"""
This module contains different data sampling methods
"""

import logging
import random
import datetime
import math
from abc import ABC, abstractmethod
from io import BytesIO

import shapely.affinity
import shapely.geometry
import shapely.ops
import dateutil.parser
import numpy as np

from PIL import Image
from PIL.TiffTags import TAGS

from sentinelhub import get_json, BBox, CRS, download_data, DownloadRequest, MimeType, WebFeatureService, \
    DataSource, Geometry

from .tasks import Task
from .sampling_utils import random_sample, random_sample_image, sample_image_with_bbox, \
    get_resolution, count_points, triangulate, random_sample_point
from .geopedia import get_layer_item_list
from .image_utils import merge_images, encode_image, hex_to_rgb


BASE_INDEX_URL = 'https://services.sentinel-hub.com/index/s2/v3/tiles/'

LOGGER = logging.getLogger(__name__)


class Sampling(ABC):

    def __init__(self):
        self.index = 0

    def __iter__(self):
        """Iteration method

        :return: Iterator over samples
        :rtype: Iterator[dict]
        """
        self.index = 0
        return self

    @abstractmethod
    def __next__(self):
        """Next method
        """
        raise NotImplementedError

    @staticmethod
    def _expand_geo_shape(geo_shape, factor):
        if isinstance(factor, (float, int)):
            factor = (factor, factor)
        return shapely.affinity.scale(geo_shape, factor[0], factor[1], origin=shapely.geometry.Point((0, 0)))


class SentinelHubSampling(Sampling):

    def __init__(self, window_shape, resolution, buffer=10, data_source=DataSource.SENTINEL2_L1C):
        """
        :param window_shape: Shape of the sampling window in pixels
        :type window_shape: (int, int)
        :param resolution: Sampling resolution in meters
        :type resolution: int or float
        :param buffer: Buffer around sampled window which has to be inside the sampling area in pixels
        :type buffer: int
        :param data_source: Source of satellite data
        :type data_source: sentinelhub.DataSource
        """
        super().__init__()

        self.window_shape = window_shape
        self.resolution = resolution
        self.buffer = buffer
        self.data_source = data_source

    def __next__(self):
        attempts = 16
        while attempts > 0:
            try:
                tile_info = self.get_random_tile()

                sampling_geometry = self.get_sampling_geometry(tile_info)

                bbox = self.get_random_bbox(sampling_geometry)

                return Task(bbox=bbox, acq_time=self.get_sensing_time(tile_info),
                            window_shape=self.window_shape, data_list=[], tile_id=self.get_tile_id(tile_info))
            except ValueError:
                attempts -= 1

        raise ValueError('Failed to sample a new task')

    def get_random_bbox(self, area_geometry):
        """
        :param area_geometry: Geometry object which has to be in UTM CRS
        :type area_geometry: sentinelhub.Geometry
        """
        if not CRS.is_utm(area_geometry.crs):
            raise ValueError('Geometry object has to be in UTM CRS for sampling')

        reduced_geo = self._expand_geo_shape(area_geometry.geometry, 1 / self.resolution)
        sampled_rectangle = random_sample(reduced_geo, (self.window_shape[0] + 2 * self.buffer,
                                                        self.window_shape[1] + 2 * self.buffer))
        expanded_rectangle = self._expand_geo_shape(sampled_rectangle, self.resolution)

        return BBox(expanded_rectangle.bounds, crs=area_geometry.crs)

    @abstractmethod
    def get_random_tile(self):
        raise NotImplementedError

    @abstractmethod
    def get_sampling_geometry(self):
        raise NotImplementedError

    @abstractmethod
    def get_sensing_time(self):
        raise NotImplementedError

    @abstractmethod
    def get_tile_id(self):
        raise NotImplementedError


class ShIndexSampling(SentinelHubSampling):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.data_source is not DataSource.SENTINEL2_L1C:
            raise NotImplementedError

        self._archive_size = None
        self._archive_check_time = None  # In stateless service won't be needed anymore

    def get_random_tile(self):
        random_tile_id = random.randint(1, self.get_archive_size())
        tile_info = self.get_tile_info(random_tile_id)

        cover_percentage = float(tile_info['coverArea']) / 12055600804.0

        if cover_percentage >= 0.1 and random.random() <= cover_percentage:
            return tile_info

        raise ValueError('Could not get a random tile with enough coverage from the archive')

    def get_archive_size(self):
        """ This will collect archive size at most once per day
        """
        current_time = datetime.datetime.now()
        if self._archive_size is None or self._archive_check_time < current_time - datetime.timedelta(days=1):
            self._archive_check_time = current_time
            self._archive_size = self.get_tile_id(self.get_tile_info('lastTile'), esa_id=False)
        return self._archive_size

    @staticmethod
    def get_tile_info(tile_id):
        LOGGER.info('Collecting data from S-2 index for tile %s', str(tile_id))
        return get_json('{}{}'.format(BASE_INDEX_URL, tile_id))

    @staticmethod
    def get_tile_id(tile_info, esa_id=True):
        """ Can return either ESA tile ID or SH index tile ID
        """
        if esa_id:
            return tile_info['pdiId']
        return int(tile_info['id'])

    @staticmethod
    def get_crs(tile_info):
        return CRS(tile_info['tileOrigin']['crs']['properties']['name'].rsplit(':', 1)[1])

    @staticmethod
    def get_sensing_time(tile_info):
        datetime_obj = datetime.datetime.strptime('{}'.format(tile_info['sensingTime']), '%Y-%m-%dT%H:%M:%S.%f')
        return datetime_obj.date()

    @staticmethod
    def get_sampling_geometry(tile_info):
        return Geometry(shapely.geometry.shape(tile_info['coverGeometry']), crs=ShIndexSampling.get_crs(tile_info))


class ShOgcSampling(SentinelHubSampling):

    def __init__(self, area_of_interest, time_interval, maxcc, *args, **kwargs):
        """
        :param area_of_interest: Area of interest to sample from
        :type area_of_interest: sentinelhub.Geometry
        :param time_interval: Time interval when to sample
        :type time_interval:[datetime.datetime, datetime.datetime]
        :param maxcc: Maximal cloud coverage to allow to be sampled
        :type maxcc: float
        """
        super().__init__(*args, **kwargs)

        self.area_of_interest = area_of_interest
        self.time_interval = time_interval
        self.maxcc = maxcc

        self.time_interval_list = self._time_split(self.time_interval, resolution=datetime.timedelta(weeks=4))
        self.aoi_triangulation = triangulate(self.area_of_interest.geometry)

    def get_random_tile(self):
        """Get a random tile over AOI and time interval"""
        random_point = random_sample_point(self.area_of_interest.geometry, triangles=self.aoi_triangulation,
                                           use_int_coords=False)
        small_bbox = self._get_small_bbox(random_point)

        for time_interval in self._get_shuffled_time_intervals():
            tiles = list(WebFeatureService(bbox=small_bbox, time_interval=time_interval,
                                           data_source=self.data_source, maxcc=self.maxcc))
            if tiles:
                return random.choice(tiles)

        raise ValueError('Could not sample a random point from given areas of interest, maybe no data is available')

    def _get_small_bbox(self, point):
        """ Create a small random bbox from a point for WFS search
        TODO: sentinelhub-py should support WFS searches with a point object
        """
        x, y = point
        eps = 0.0001 if self.area_of_interest.crs is CRS.WGS84 else 0.01
        return BBox([x - eps, y - eps, x + eps, y + eps], crs=self.area_of_interest.crs)

    @staticmethod
    def _time_split(time_interval, resolution=datetime.timedelta(weeks=4)):
        """ Split time interval into several, at most resolution long
        """
        if len(time_interval) > 2:
            raise ValueError('Splitting only works on [ datetime, datetime ] array.')

        delta_t = time_interval[1] - time_interval[0]
        n_t = math.ceil(delta_t / resolution)
        delta_t = delta_t / n_t
        return [[time_interval[0] + i * delta_t, time_interval[0] + (i + 1) * delta_t] for i in range(n_t)]

    def _get_shuffled_time_intervals(self):
        """ Shuffles time intervals to allow a random selection
        """
        shuffled_time_intervals = self.time_interval_list[:]
        random.shuffle(shuffled_time_intervals)
        return shuffled_time_intervals

    def get_sampling_geometry(self, tile_info):
        tile_geometry = Geometry(tile_info['geometry'], crs=self.area_of_interest.crs)

        utm_crs = ShOgcSampling.get_crs(tile_info)
        tile_geometry = tile_geometry.transform(utm_crs)
        utm_aoi_geometry = self.area_of_interest.transform(utm_crs)

        # Warning: This intersection can be too small for sampling, that is why __next__ method is retrying the process
        return Geometry(tile_geometry.geometry.intersection(utm_aoi_geometry.geometry), utm_crs)

    @staticmethod
    def get_crs(tile_info):
        return CRS(tile_info['properties']['crs'].rsplit(':', 1)[1])

    @staticmethod
    def get_tile_id(tile_info):
        """ Returns ESA tile ID
        """
        return tile_info['properties']['id']

    @staticmethod
    def get_sensing_time(tile_info):
        return datetime.datetime.strptime('{}'.format(tile_info['properties']['date']), '%Y-%m-%d')


class GeopediaLayerSampling(Sampling):

    def __init__(self, source, feature_interval=None):
        super().__init__()

        self.source = source

        self.item_list = None
        self.feature_interval = feature_interval

    def __next__(self):

        if self.item_list is None:
            self.set_item_list()

        self.index += 1
        if self.index >= len(self.item_list):
            self.index = 0

        task = self.make_task(self.item_list[self.index])
        return task

    def set_item_list(self):
        LOGGER.info('Collecting data from Geopedia layer %d', int(self.source.geopedia_layer))
        self.item_list = get_layer_item_list(int(self.source.geopedia_layer), interval=self.feature_interval)

        random.shuffle(self.item_list)
        LOGGER.info('Collected data about %d features', len(self.item_list))

    @staticmethod
    def get_bbox_coords(tile_coords, offset, window_shape, resolution=(10, 10)):
        x, y = tile_coords[0] + resolution[0] * offset[0], tile_coords[1] - resolution[1] * offset[1]
        return [x, y, x + resolution[0] * window_shape[0], y - resolution[1] * window_shape[1]]


class GeopediaWaterBodySampling(GeopediaLayerSampling):

    def __init__(self, source, window_shape, resolution):
        super().__init__(source)

        self.window_shape = window_shape
        self.resolution = resolution

    def make_task(self, item):
        props = item['properties']

        feature_id = int(item['@id'].rsplit('/', 1)[1])

        image, bbox = self._collect_data(props['Mask'][0]['objectPath'])
        wb_geometry = shapely.geometry.shape(item['geometry'])

        # sampled_image, sampled_bbox = self.random_sample_bbox(image, bbox, wb_geometry)
        (sampled_image, sampled_bbox), wb_geometry = self.random_sample_geometry(image, bbox, wb_geometry)

        colored_sampled_image = np.zeros(sampled_image.shape[:2] + (3,), dtype=np.uint8)
        colored_sampled_image[sampled_image == 1] = hex_to_rgb(self.source.layers[0]['classes'][0]['color'])

        data_list = [{
            "layer": self.source.layers[0]['title'],
            "image": encode_image(colored_sampled_image)
        }]

        vector_data = [
            # bbox.get_geojson(),
            shapely.geometry.mapping(wb_geometry)
            # item['geometry']  # This is already shown in Geopedia WMS layer
        ]

        return Task(bbox=sampled_bbox, acq_time=self.parse_time(props), window_shape=self.window_shape,
                    data_list=data_list, feature_id=feature_id, vector_data=vector_data)

    @staticmethod
    def parse_time(gpd_props):
        return dateutil.parser.parse(gpd_props['SAT_IMAGE_DATE'].split('T')[0]).date()

    def _collect_data(self, url):
        download_list = [DownloadRequest(url=url, save_response=False, data_type=MimeType.RAW)]
        raw_image = download_data(download_list)[0].result(timeout=60)

        bbox = self.get_bbox(BytesIO(raw_image))

        image = np.array(Image.open(BytesIO(raw_image)))

        return image, bbox

    @staticmethod
    def get_bbox(image_bytes):
        with Image.open(image_bytes) as img:
            meta_dict = {TAGS[key]: value for key, value in img.tag.items()}

            if meta_dict['GeoAsciiParamsTag'] != ('WGS 84|',):
                raise ValueError('Expected image in WGS84')

        window_shape = meta_dict['ImageWidth'][0], meta_dict['ImageLength'][0]

        transform = (meta_dict['ModelTiepointTag'][3], meta_dict['ModelPixelScaleTag'][0], 0.0,
                     meta_dict['ModelTiepointTag'][4], 0.0, -meta_dict['ModelPixelScaleTag'][1])

        bbox = BBox(GeopediaLayerSampling.get_bbox_coords((transform[0], transform[3]), (0, 0), window_shape,
                                                          (transform[1], -transform[5])), crs=CRS.WGS84)
        return bbox

    def random_sample_geometry(self, image, bbox, wb_geometry_initial):
        resolution = get_resolution(image, list(bbox))
        bbox_polygon = bbox.get_geometry()
        bbox_polygon = self._expand_geo_shape(bbox_polygon, (1 / resolution[0], 1 / resolution[1]))

        wb_geometry = self._expand_geo_shape(wb_geometry_initial, (1 / resolution[0], 1 / resolution[1]))

        wb_geometry = wb_geometry.buffer(max(self.window_shape))
        wb_geometry = wb_geometry.simplify(2, preserve_topology=False)  # This simplifies geometry
        wb_geometry = wb_geometry.intersection(bbox_polygon)

        LOGGER.debug('Reduced number of points in sampling vector shape from %d to %d',
                     count_points(wb_geometry_initial), count_points(wb_geometry))

        sampled_rectangle = random_sample(wb_geometry, self.window_shape)
        sampled_bbox = list(map(float, self._expand_geo_shape(sampled_rectangle, resolution).bounds))

        wb_geometry = self._expand_geo_shape(wb_geometry, resolution)

        return sample_image_with_bbox(image, bbox, sampled_bbox), wb_geometry

    def random_sample_bbox(self, image, bbox, wb_geometry):
        image, bbox = sample_image_with_bbox(image, bbox, list(wb_geometry.bounds), buffer=10)

        return random_sample_image(image, bbox, self.window_shape)


class GeopediaOldAppResults(GeopediaLayerSampling):
    """ Special case of Geopedia sampling when we work with results of old version of classification results
    """

    def make_task(self, item):
        props = item['properties']

        tile_id = int(props["TileId"])
        window_shape = tuple(map(lambda prop_name: int(props[prop_name]), ["Size X", "Size Y"]))
        offset = tuple(map(lambda prop_name: int(props[prop_name]), ["Offset X", "Offset Y"]))

        tile_info = ShIndexSampling.get_tile_info(tile_id)
        tile_coords = self.get_tile_coords(tile_info)

        bbox = BBox(self.get_bbox_coords(tile_coords, offset, window_shape),
                    crs=ShIndexSampling.get_crs(tile_info))

        return Task(bbox=bbox, acq_time=ShIndexSampling.get_sensing_time(tile_info),
                    window_shape=window_shape, tile_id=tile_id, tile_coords=tile_coords, offset=offset,
                    data_list=self._collect_data(props['Masks']))

    @staticmethod
    def get_tile_coords(tile_info):
        return tile_info['tileOrigin']['coordinates']

    @staticmethod
    def get_bbox_coords(tile_coords, offset, window_shape, resolution=(10, 10)):
        x, y = tile_coords[0] + resolution[0] * offset[0], tile_coords[1] - resolution[1] * offset[1]
        return [x, y, x + resolution[0] * window_shape[0], y - resolution[1] * window_shape[1]]

    def _collect_data(self, mask_list):
        download_list = [DownloadRequest(url=mask_props['objectPath'], save_response=False, data_type=MimeType.PNG)
                         for mask_props in mask_list]
        images = [future.result(timeout=60) for future in download_data(download_list)]
        image_names = [mask_props['niceName'] for mask_props in mask_list]

        # TODO: Change this hardcoded part
        data_dict = {}
        for image, image_name in zip(images, image_names):
            class_name = image_name.rsplit('_', 1)[1].split('.')[0]
            layer_name = {
                'Opaque clouds': 'Clouds',
                'Thick clouds': 'Clouds',
                'Thin clouds': 'Clouds',
                'Shadows': 'Shadows',
                'Land': 'Surface',
                'Water': 'Surface',
                'Snow': 'Surface'
            }[class_name]
            data_dict[layer_name] = data_dict.get(layer_name, {})
            data_dict[layer_name][class_name] = image

        return self._join_data_dict(data_dict)

    def _join_data_dict(self, data_dict):
        data_list = []

        for layer_prop in self.source.layers:
            layer_name = layer_prop['title']
            if layer_name in data_dict:
                images = []
                colors = []
                for class_prop in layer_prop['classes']:
                    class_name = class_prop['title']
                    if class_name in data_dict[layer_name]:
                        images.append(data_dict[layer_name][class_name])
                        colors.append(class_prop['color'])

                if images:
                    merged_image = merge_images(images, colors)

                    data_list.append({
                        "layer": layer_name,
                        "image": encode_image(merged_image)
                    })

        return data_list
