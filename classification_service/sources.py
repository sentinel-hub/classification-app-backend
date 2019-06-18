"""
Modules implementing sources of data
"""

import os
from enum import Enum

import attr
from marshmallow import ValidationError

from sentinelhub import read_data

from .schemas import SourceSchema, InputSourceInfoSchema
from .users import Access
from .utils import to_python, get_uuid


class SourceType(Enum):
    """ Type of source where data is obtained from or saved to
    """
    S2_L1C_ARCHIVE = 'S2 L1C Archive'
    GEOPEDIA_V0 = 'Geopedia V0'
    GEOPEDIA_WB = 'Geopedia WB'
    GEOPEDIA_RESULTS = 'Geopedia Results'
    LOCAL = 'local'

    def is_geopedia_source(self):
        return self in {SourceType.GEOPEDIA_V0, SourceType.GEOPEDIA_WB, SourceType.GEOPEDIA_RESULTS}

    def __str__(self):
        return self.value


@attr.s
class Source:
    """ Class implementing data sources
    """
    name = attr.ib()
    source_type = attr.ib(converter=SourceType)
    id = attr.ib(factory=get_uuid)
    description = attr.ib(default='')
    access = attr.ib(converter=Access.load, default=None)
    geopedia_layer = attr.ib(default=-1)
    layers = attr.ib(factory=list)
    sampling_params = attr.ib(factory=list)
    default_ui = attr.ib(factory=dict)

    SOURCE_SCHEMA = SourceSchema()
    SOURCE_INFO_SCHEMA = InputSourceInfoSchema()

    @staticmethod
    def load(payload):
        if isinstance(payload, Source) or payload is None:
            return payload

        payload, errors = Source.SOURCE_SCHEMA.load(payload)
        if errors:
            raise ValidationError(errors)

        return Source(**payload)

    def dump(self):
        return Source.SOURCE_SCHEMA.dump(self).data

    def get_info_json(self):
        return Source.SOURCE_INFO_SCHEMA.dump(self).data

    def has_access(self, user_id):
        return self.access.has_access(user_id)


def load_input_sources():
    """ Loads input sources and returns a dictionary with source IDs and source classes
    """
    sources_filename = os.path.join(os.path.dirname(__file__), 'data', 'input_sources.json')
    sources_list = [Source.load(payload) for payload in to_python(read_data(sources_filename))['sources']]

    return {source.id: source for source in sources_list}
