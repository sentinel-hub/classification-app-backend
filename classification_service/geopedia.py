"""
This module implements communications with Geopedia
"""

import os
import io
import copy
import json
import logging
import pkg_resources
from configparser import RawConfigParser
from itertools import islice
from sys import version_info
from collections import OrderedDict

import requests
import shapely.geometry
import attr
from attr.validators import instance_of
from werkzeug.datastructures import FileStorage

from sentinelhub import SHConfig, GeopediaFeatureIterator, get_json, Geometry

from .constants import GeopediaType, GPD_FEATURE, GPD_TABLE, PermissionType

LOGGER = logging.getLogger(__name__)


class GeopediaConfig:

    @staticmethod
    def set_sh_config():
        config = SHConfig()

        expected_base_url = 'https://www.geopedia.world/rest/' if GeopediaConfig.is_production() else \
            'https://test.geopedia.world/rest/'

        if config.geopedia_rest_url != expected_base_url:
            config.geopedia_rest_url = expected_base_url
            config.save()

    @staticmethod
    def is_production():
        return os.environ.get('PRODUCTION', 'false').lower() == 'true'

    @staticmethod
    def get_config_path():
        filename = '.geopedia.config' if GeopediaConfig.is_production() else '.geopedia-test.config'

        config_path = os.path.join(os.path.dirname(__file__), 'data', filename)

        if not os.path.isfile(config_path):
            raise IOError('Geopedia configuration file does not exist: %s' % os.path.abspath(config_path))

        return config_path

    @staticmethod
    def load_config():
        """ Load Geopedia configuration file storing authentication and table IDs
        """
        config_parser = RawConfigParser()
        config_parser.read(GeopediaConfig.get_config_path())

        return dict(config_parser.items('geopedia')), dict(config_parser.items('tables'))


@attr.s()
class GeopediaPayloadBase:
    """ Base class for responses obtained from Geopedia
    """
    payload = attr.ib(validator=instance_of(dict))

    @property
    def properties(self):
        """ A dictionary of table properties
        """
        return self.payload['properties']

    @property
    def id(self):
        """ A dictionary of table properties
        """
        return int(self.payload['id'])


@attr.s()
class GeopediaTable(GeopediaPayloadBase):
    """ Container for basic properties of a Geopedia table
    """
    gpd_store = attr.ib()

    def __attrs_post_init__(self):
        """ This method happens right after init
        """
        self.field_name_map = {}
        for field_props in self.properties:
            field_name = field_props['name']
            if field_name in ['id', 'properties', 'geometry']:
                raise ValueError("Table with ID {} has a forbidden column name '{}'".format(self.id, field_name))

            self.field_name_map[field_name] = field_props

        if len(self.field_name_map) < len(self.properties):
            raise ValueError('Some fields in the table {} have same names'.format(self.id))

    def __contains__(self, item):
        """ Checks if column name exists in the table
        """
        return item in self.field_name_map

    @property
    def name(self):
        """ Name of the table
        """
        return self.payload['name']

    @property
    def gpd_session(self):
        """ Provides GeopediaSession object from the store
        """
        return self.gpd_store.gpd_session

    @staticmethod
    def load(table_id, gpd_store):
        """ Load an instance of GeopediaTable
        """
        # For now we need entire gpd_store because it is keeping the session alive
        # This should be changed when session updating is fixed at Geopedia
        gpd_session = gpd_store.gpd_session
        url = '{}data/v2/tables/{}'.format(gpd_session.base_url, table_id)
        payload = get_json(url, headers=gpd_session.session_headers)
        return GeopediaTable(payload=payload, gpd_store=gpd_store)

    def get_field_id(self, field_name):
        """ Get a field id from a field name
        """
        if field_name not in self.field_name_map:
            raise ValueError("Field with name '{}' is not in a table with ID {}".format(field_name, self.id))
        return self.field_name_map[field_name]['fieldId']

    def get_mandatory_fields(self):
        """ Get names of mandatory fields
        """
        return [field_name for field_name, field_props in self.field_name_map.items()
                if field_props['settings']['mandatory']]

    def query_columns(self, column_names, conditions, return_all=True):
        """ The method makes a query to Geopedia table with filter conditions on values. It returns filtered table
        content.

        Example:
        query_columns(['input_source_id','is_done'], ['=1', '=False'])

        :param column_names: Names of table columns to apply query
        :type column_names: str or list of str
        :param conditions: Logical conditions to be applied to corresponding columns
        :type conditions: str or list of str
        :param return_all: Whether to return all elements satisfying query or only the first one. Default is all.
        :type return_all: bool
        :return: Items from Geopedia table with properties
        :rtype: GeopediaRowData or list(GeopediaRowData)
        """
        column_names = [column_names] if isinstance(column_names, str) else column_names
        conditions = [conditions] if isinstance(conditions, str) else conditions
        if len(column_names) != len(conditions):
            raise ValueError("Name of columns and conditions must be of same length")

        field_ids = [self.get_field_id(name) for name in column_names]
        query = ' && '.join([col + expr for col, expr in zip(field_ids, conditions)])
        gpd_iterator = GeopediaFeatureIterator(self.id, query_filter=query, gpd_session=self.gpd_session)

        return self._return_query_results(gpd_iterator, query, return_all)

    def query_rows(self, row_ids):
        """ The method makes a query to Geopedia table for specified rows. It returns table content for those rows.

        Note: If input is a single ID it will return a single result, but if input is a list of IDs it will return a
        list of results.

        :param row_ids: IDs of queried rows
        :type row_ids: int or list(int)
        :return: Data about one or multiple Geopedia rows
        :rtype: GeopediaRowData or list(GeopediaRowData)
        """
        return_all = not isinstance(row_ids, (int, str))
        row_ids = row_ids if return_all else [row_ids]

        query = ' || '.join(['id{} = {}'.format(self.id, row_id) for row_id in row_ids])
        gpd_iterator = GeopediaFeatureIterator(self.id, query_filter=query, gpd_session=self.gpd_session)

        return self._return_query_results(gpd_iterator, query, return_all)

    def _return_query_results(self, gpd_iterator, query, return_all):
        """ Helper method for returning 1 or all results of a query to Geopedia table
        """
        if return_all:
            return [GeopediaRowData(result) for result in gpd_iterator]
        try:
            return GeopediaRowData(next(gpd_iterator))
        except StopIteration:
            raise RuntimeError("There are no items for query '{}' in table '{}'".format(query, self.name))


@attr.s()
class GeopediaRowData(GeopediaPayloadBase):
    """ Container for results obtained from querying Geopedia tables
    """

    @property
    def geometry(self):
        """ Helper function to return a WKT polygon from a Geopedia geometry

        Given a geometry field from a Geopedia table, return a WKT polygon in POP_WEB CRS

        :param geometry: Dictionary describing a Geopedia geometry feature
        :return: WKT polygon in popular web-mercator
        """
        geometry_payload = self.payload['geometry']
        return Geometry(shapely.geometry.shape(geometry_payload),
                        crs=geometry_payload['crs']['properties']['name'].split(':')[-1])

    def __getitem__(self, item):
        """ Obtaining property values without using .properties all the time
        """
        try:
            return self.properties[item]
        except KeyError:
            raise KeyError("Result from a table with ID {} does not contain a property "
                           "'{}'".format(self.payload['@id'].rsplit('/')[-1], item))

    def __setitem__(self, item, value):
        """ Setting a new property
        """
        self.properties[item] = value


class SaveToGeopedia:

    def __init__(self, gpd_tables, session_id):
        self.gpd_tables = gpd_tables
        self.session_id = session_id

        self.base_url = '{}'.format(SHConfig().geopedia_rest_url)

    def _get_headers(self, is_json=True, session_id=None):
        headers = {
            'X-Gpd-ClassificationApp': 'true',
            'X-GPD-Session': self.session_id if session_id is None else session_id
        }
        if is_json:
            headers['Content-type'] = 'application/json; charset=utf-8'
        return headers

    def _send_json(self, request_url, data=None, is_json=True, files=None, session_id=None):
        """ POST request to Geopedia.

         Data as json or files are written to Geopedia tables

        :param request_url: url where POST request is attempted
        :param data: JSON data to be posted
        :param is_json: Flag indicating whether data or files are posted
        :param files: Files to be posted to Geopedia
        :return: Geopedia row data instance
        """
        if needs_ordered_dicts() and data is not None:
            data = self._apply_ordered_dicts(data)

        response = requests.post(url=request_url,
                                 data=data if data is None else json.dumps(data),
                                 headers=self._get_headers(is_json=is_json, session_id=session_id),
                                 files=files)

        LOGGER.info('Sampling table - POST: Response: %s, Status: %d', response.reason, response.status_code)
        try:
            response.raise_for_status()
        except requests.RequestException as exception:
            LOGGER.info('Payload of the failed request:\n%s', json.dumps(data))
            LOGGER.info('Server response:\n%s', str(response.text))
            raise exception

        payload = response.json()
        if isinstance(payload, list):
            payload = payload[0]

        return GeopediaRowData(payload)

    @staticmethod
    def _apply_ordered_dicts(data):
        if 'properties' in data:
            data['properties'] = [OrderedDict([('type', prop['type']), ('value', prop['value'])])
                                  for prop in data['properties']]
        return data

    @staticmethod
    def _set_feature(table, values_dict):
        """ Set up feature to be written to geopedia based on the table's structure

        :param table: GeopediaTable object
        :param values_dict: Dictionary with the values to be inputted to the table. The keys of this dict correspond to
                            the `name` entry of the `props` dictionary
        :return: Dictionary feature to be written to Geopedia
        """
        values_dict = {key: value for key, value in values_dict.items() if key in table}
        if not set(table.get_mandatory_fields()).issubset(values_dict):
            raise ValueError("Some mandatory fields are missing in the payload:\n"
                             "Values: {}\n"
                             "Mandatory fields: {}".format(values_dict, table.get_mandatory_fields()))
        # create feature starting from the template
        feature = copy.deepcopy(GPD_FEATURE)
        feature['tableId'] = table.id
        feature['properties'].extend([{'type': GeopediaType[prop['type']].value,
                                       'value': SaveToGeopedia._prepare_value(values_dict, prop)}
                                      for prop in table.properties])

        # if there is a geometry feature, replace with correct format
        if 'primaryGeometry' in values_dict:
            for feat_prop in feature['properties']:
                if feat_prop['type'] == 'geometry':
                    wkt_geometry = feat_prop['value']
                    feat_prop['value'] = {'wkt': wkt_geometry, 'crsId': 'EPSG:3857'}
                    feat_prop['geomAuxData'] = {'mbr': None, 'pointInside': None}
                    break
        return feature

    @staticmethod
    def _prepare_value(values_dict, prop):
        """ Prepares a values which will be stored in a Geopedia table and makes sure it is of correct type
        """
        name = prop['name']
        if name not in values_dict:
            return None
        value = values_dict[name]

        expected_type = GeopediaType[prop['type']]

        if isinstance(value, (dict, list)) and expected_type is not GeopediaType.BINARYREFERENCE:
            value = json.dumps(value)

        if not isinstance(value, expected_type.python_type):
            value = expected_type.python_type(value)
        return value

    def _update_feature(self, table, values_dict, row_id):
        """ Set up feature to be updated on geopedia based on the table's structure

        :param table: GeopediaTable object
        :param values_dict: Dictionary with the values to be inputted to the table. The keys of this dict correspond to
                            the `name` entry of the `props` dictionary
        :param row_id: Value of ID row to be updated
        :return: Dictionary feature to be updated on Geopedia
        """
        feature = self._set_feature(table, values_dict)
        # set action to update
        feature['properties'][0]['value'] = row_id
        feature['id'] = row_id
        feature['@id'] = 'feature/{}'.format(row_id)
        feature['storeAction'] = 'UPDATE'
        return feature

    def save_feature(self, table_name, values_dict):
        return self._send_json('{}data/v1/features/save'.format(self.base_url),
                               data=self._set_feature(self.gpd_tables[table_name], values_dict))

    def update_feature(self, table_name, values_dict, row_id):
        return self._send_json('{}data/v1/features/save'.format(self.base_url),
                               data=self._update_feature(self.gpd_tables[table_name], values_dict, row_id))

    def save_files(self, table, values_dict, files):
        files['feature'] = FileStorage(io.StringIO(json.dumps(self._set_feature(table,
                                                                                values_dict))),
                                       name='blob', content_type='application/json')
        return self._send_json('{}data/v1/features/saveWithFiles'.format(self.base_url),
                               is_json=False,
                               files=files)

    def create_table(self, user_session_id, table_name, access_type):
        """ Create new table for the results of the campaign using the user session ID

        :param user_session_id: Geopedia session_id
        :param table_name: The name of the table with the results
        :param access_type: Type of table access ('private' or 'public')
        :return: response from the Geopedia
        """
        gpd_table = copy.deepcopy(GPD_TABLE)
        gpd_table['name'] = table_name
        gpd_table['publicPermissions']['permissionSet'] = PermissionType[access_type.value.upper()].value

        return self._send_json('{}data/v1/meta/table'.format(self.base_url),
                               session_id=user_session_id, data=gpd_table)


def get_layer_item_list(layer, interval=None):
    if interval:
        list(islice(GeopediaFeatureIterator(layer), *interval))
    return list(GeopediaFeatureIterator(layer))


def needs_ordered_dicts():
    return version_info.minor <= 5
