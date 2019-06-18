"""
This module implements tasks
"""

import time
import datetime
import logging
import threading

from sentinelhub import CRS

from .constants import MAX_TASKS
from .schemas import TaskSchema
from .utils import get_uuid

LOWER_BOUND = 0
UPPER_BOUND = 2 ** 50

LOGGER = logging.getLogger(__name__)


class Task:
    """ Container with task parameters
    """
    # TODO: figure what to do with **props in attrs package
    # id = attr.ib(validator=instance_of(int))
    # bbox = attr.ib(validator=instance_of(BBox))
    # time = attr.ib(validator=instance_of(datetime.datetime))
    # window_size = attr.ib(validator=instance_of(list))
    # data_list = attr.ib(validator=instance_of(list))

    def __init__(self, bbox, acq_time, window_shape, task_id=None, data_list=None, **props):

        self.task_id = get_uuid() if task_id is None else task_id
        self.bbox = bbox
        self.acq_time = acq_time
        self.window_shape = window_shape
        self.data_list = [] if data_list is None else data_list

        self.props = props

    def get_app_json(self):
        bbox_coords = list(self.bbox)
        crs = self.bbox.get_crs()

        # TODO: use TaskSchema(strict=True).dump instead of this
        payload = {
            'id': self.task_id,
            'bbox': [bbox_coords[1], bbox_coords[0],
                     bbox_coords[3], bbox_coords[2]] if crs is CRS.WGS84 else bbox_coords,
            'crs': int(crs.value),
            'window_width': self.window_shape[0],
            'window_height': self.window_shape[1],
            'datetime': self.acq_time,
            'data': self.data_list
        }
        if 'vector_data' in self.props and self.props['vector_data'] is not None:
            payload['vectorData'] = self.props['vector_data']

        payload = TaskSchema(strict=True).dump(payload)[0]

        payload['window'] = {  # TODO: remove this once they change it on frontend
            'width': self.window_shape[0],
            'height': self.window_shape[1]
        }
        return payload


class TaskThreading(threading.Thread):
    """ Class to handle creating tasks in the back-ground and adding them to Geopedia """
    def __init__(self, campaign, store, *args, interval=1, **kwargs):
        threading.Thread.__init__(self, target=self.run, *args, **kwargs)
        # sleep time interval between geopedia requests
        self.campaign = campaign
        self.store = store
        self.interval = interval

    def run(self):
        for _ in range(MAX_TASKS):
            try:
                current_task = self.store.add_task(self.campaign)
                LOGGER.info("Task %s added to geopedia", current_task.task_id)
                time.sleep(self.interval)
            except (RuntimeError, ValueError) as exception:
                LOGGER.debug("Error creating tasks in the background: %s", str(exception))
