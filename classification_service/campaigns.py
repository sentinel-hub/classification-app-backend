"""
This module implements campaigns and their properties
"""

import logging

import attr
from attr.validators import instance_of
from marshmallow import ValidationError

from sentinelhub import BBox, CRS

from .utils import to_python
from .sampling import Sampling, ShIndexSampling, GeopediaWaterBodySampling, GeopediaOldAppResults
from .sources import Source, SourceType, load_input_sources
from .schemas import CampaignSchema, BasicCampaignSchema, CampaignInfoSchema
from .users import Access
from .utils import get_uuid


LOGGER = logging.getLogger(__name__)


@attr.s(kw_only=True)
class Campaign:

    name = attr.ib()
    description = attr.ib(default='')
    access = attr.ib(converter=Access.load)
    id = attr.ib(factory=get_uuid)
    sampling = attr.ib(default=None)
    input_source = attr.ib(converter=Source.load, default=None)
    output_source = attr.ib(converter=Source.load, default=None)
    ui = attr.ib(validator=instance_of(dict), factory=dict)
    active_users = attr.ib(init=False, factory=set)
    active_tasks = attr.ib(init=False, factory=dict)
    sampling_method = attr.ib(init=False)

    CAMPAIGN_SCHEMA = CampaignSchema(strict=True)
    CAMPAIGN_INFO_SCHEMA = CampaignInfoSchema(strict=True)
    BASIC_CAMPAIGN_SCHEMA = BasicCampaignSchema(strict=True)

    def __attrs_post_init__(self):

        if self.description is None:
            self.description = ''

        if self.sampling is None:  # TODO: fixme
            return

        # TODO: accept non-default geometry
        max_coord = 2 * 10 ** 7
        self.geometry = BBox((-max_coord, -max_coord, max_coord, max_coord), CRS.POP_WEB)

        if self.input_source.source_type is SourceType.S2_L1C_ARCHIVE:
            window_shape = self.sampling['window_width'], self.sampling['window_height']
            # TODO: replace ShIndexSampling with ShOgcIndexSampling
            self.sampling_method = ShIndexSampling(window_shape, self.sampling['resolution'], self.sampling['buffer'])

        elif self.input_source.source_type.is_geopedia_source():
            if self.input_source.geopedia_layer == 1749:
                self.sampling_method = GeopediaOldAppResults(self.input_source)

            elif self.input_source.geopedia_layer == 2048:
                window_shape = self.sampling['window_width'], self.sampling['window_height']
                self.sampling_method = GeopediaWaterBodySampling(self.input_source, window_shape,
                                                                 self.sampling['resolution'])
            else:
                raise NotImplementedError
        else:
            raise NotImplementedError

    @property
    def layers(self):
        """ A property that provides layers of output source
        """
        return self.output_source.layers

    @staticmethod
    def load(payload):
        """ Loads a campaign from a complete payload
        """
        payload, errors = Campaign.CAMPAIGN_SCHEMA.load(to_python(payload))
        if errors:
            raise ValidationError(errors)

        return Campaign(**payload)

    @staticmethod
    def prepare_payload(payload, user_id=None):
        """ Prepares some parts of the payload
        """
        if user_id is not None:
            payload['access']['owner_id'] = user_id

        if 'input_source_id' in payload:
            input_source = load_input_sources()[payload['input_source_id']]
            payload['input_source'] = input_source.dump()

            if 'ui' not in payload:
                payload['ui'] = payload['input_source']['default_ui']

        if 'output_source' not in payload:  # TODO: this should be handled differently when creation of new tables is added
            payload['output_source'] = {
                "name": "Classification App results",
                'access': payload['access'],
                "description": 'something',
                "source_type": "Geopedia Results",
                "geopedia_layer": 2047,
                "layers": payload['layers']
            }

        return payload

    def get_basic_info(self):
        """ Provides basic info about a campaign
        """
        return Campaign.BASIC_CAMPAIGN_SCHEMA.dump(self).data

    def get_info(self):
        """ Provides all info that will be passed to front-end
        """
        return Campaign.CAMPAIGN_INFO_SCHEMA.dump(self).data

    def get_sampling_method(self):
        return self.sampling_method

    def add_active_task(self, task):
        self.active_tasks[task.task_id] = task

    def get_sampling_window(self):
        return [self.sampling['window_width'], self.sampling['window_height']]

    def set_instructions_flag(self, show_instructions):
        """
        :param show_instructions: If instructions should be shown right away
        :type show_instructions: bool
        """
        self.ui['show_instructions'] = show_instructions
