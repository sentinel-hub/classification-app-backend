"""
Module for storing and managing all configuration parameters
"""

import os
import json
import logging
import datetime as dt
from abc import ABC, abstractmethod
import random

from sentinelhub import read_data, get_json, GeopediaSession, GeopediaFeatureIterator, BBox, CRS

from .campaigns import Campaign
from .users import User
from .utils import to_python
from .sources import Source, SourceType
from .users import Access, AccessType
from .geopedia import SaveToGeopedia, GeopediaTable, GeopediaConfig
from .tasks import Task
from .exceptions import MissingCampaignError


LOGGER = logging.getLogger(__name__)


class Store(ABC):
    """ Base class to handle campaigns and users.
    """

    @abstractmethod
    def get_campaign(self, campaign_id):
        raise NotImplementedError

    @abstractmethod
    def get_available_campaigns(self, user):
        raise NotImplementedError

    @abstractmethod
    def add_campaign(self, campaign, user_session_id):
        raise NotImplementedError

    @abstractmethod
    def delete_campaign(self, campaign_id):
        raise NotImplementedError

    @abstractmethod
    def add_task(self, campaign):
        raise NotImplementedError

    @abstractmethod
    def save_task(self, task_id, user_id, campaign, request):
        raise NotImplementedError

    @abstractmethod
    def add_access(self, campaign_uid, user_uid):
        raise NotImplementedError


class LocalStore(Store):
    """ Load back-end information form local file

    Class that implements the base class by reading configuration parameter from file stored locally
    """
    def __init__(self, filename):
        """ Class constructor

        Store information about sources, campaigns and users in `source_dict`, `campaign_collection` and
        `user_collection`
        """
        self._load_data(filename)

    def _load_data(self, filename):
        """ Load data from file  """
        data = read_data(os.path.join(os.path.dirname(os.path.realpath(__file__)), filename))

        self.source_dict = {}
        for source_info in data['sources']:
            source = SourceType(source_info['source_type'])
            source_info = to_python(source_info)

            if source is SourceType.S2_L1C_ARCHIVE:
                self.source_dict[source_info['id']] = Source(**source_info)
            elif source is SourceType.GEOPEDIA_WB:
                self.source_dict[source_info['id']] = Source(**source_info)
            else:
                raise NotImplementedError('Support for source {} is not implemented')

        self.campaign_collection = {}
        for campaign_info in data['campaigns']:
            campaign_info = to_python(campaign_info)

            # TODO: add parsing of Box for local back-end
            if 'bbox' not in campaign_info:
                campaign_info['bbox'] = BBox(bbox=((0, 0), (0, 0)), crs=CRS(4326))

            for param in ['input_source', 'output_source']:
                campaign_info[param] = self.source_dict[campaign_info[param]['id']]

            self.campaign_collection[campaign_info['id']] = Campaign(**campaign_info)

        self.user_collection = {user_info['id']: User(**to_python(user_info)) for user_info in data['users']}

    def get_campaign(self, campaign_id):
        """ Retrieves a campaign from the collection given the campaign ID """
        return self.campaign_collection.get(campaign_id)

    def get_available_campaigns(self, user):
        """ Returns a list of available campaigns to the specific user """
        campaign_list = [campaign.get_basic_info() for campaign in self.campaign_collection.values()]

        return {"campaigns": campaign_list}

    def add_campaign(self, campaign, user_session_id):
        """ Add new campaign to local store """
        # TODO: add campaign to local store
        raise RuntimeError("Method not currently implemented")

    def add_task(self, campaign):
        """ Add new task to local store """
        # TODO: add task to local store
        raise RuntimeError("Method not currently implemented")

    def delete_campaign(self, campaign_id):
        """ Delete campaign from available campaigns """
        # TODO: delete campaign from local store
        raise RuntimeError("Method not currently implemented")

    def save_task(self, task_id, user_id, campaign, request):
        """ Save task results to local back-end """
        # TODO: add support for saving task results locally
        raise RuntimeError("Method not currently implemented")

    def add_access(self, campaign_uid, user_uid):
        """ Add access to a private campaign to a user with a link to it """
        # TODO: add access to campaign from local store
        raise RuntimeError("Method not currently implemented")


class GeopediaStore(Store):
    """ Load back-end information from Geopedia

    Class that implements the base class by reading configuration parameter from Geopedia tables
    """
    CAMPAIGN_TABLE = 'campaign_layer'
    USER_TABLE = 'users_layer'
    USER_CAMPAIGN_TABLE = 'user_campaign_layer'
    INPUT_TABLE = 'input_layer'
    OUTPUT_TABLE = 'output_layer'
    SAMPLING_TABLE = 'sampling_layer'
    UI_TABLE = 'uis_layer'
    TASK_TABLE = 'task_layer'
    TASK_USER_TABLE = 'task_user_layer'  # not used

    def __init__(self):
        """ Reads local Geopedia configurations and collects info about tables from Geopedia. During the process an
        admin Geopedia session is created
        """
        self.geopedia_config, tables = GeopediaConfig.load_config()
        self._gpd_session = None

        self.tables = {table_name: GeopediaTable.load(table_id, self) for table_name, table_id in tables.items()}

    @property
    def gpd_session(self):
        """ Geopedia Session is a property which is kept alive in this class. Once session updating is fixed at
        Geopedia this will become redundant
        """
        # pylint: disable=protected-access
        if self._gpd_session is None or self._gpd_session._session_start + dt.timedelta(hours=1) < dt.datetime.now():
            try:
                self._gpd_session = GeopediaSession(username=self.geopedia_config['user'],
                                                    password_md5=self.geopedia_config['md5pass'], is_global=True)
                LOGGER.debug('Admin Geopedia session was created or updated')
            except Exception as ex:
                LOGGER.error('Could not create new Geopedia Session: \'%s\'!', str(ex))
                raise RuntimeError('No session to Geopedia, exiting!')
        return self._gpd_session

    @staticmethod
    def _get_document_json(file_name, window_shape, is_image=True):
        document = {'objectType': 'IMAGE' if is_image else 'DOCUMENT',
                    'mimeType': 'image/png' if is_image else 'text/plain',
                    'customLabel': None,
                    'niceName': file_name,
                    'fileUploadToken': '*' + file_name}
        if is_image:
            document['width'] = window_shape[0]
            document['height'] = window_shape[1]
        return document

    @staticmethod
    def _get_task(task_data):
        window = json.loads(task_data['window'])
        return Task(task_id=task_data['task_id'],
                    bbox=BBox(bbox=json.loads(task_data['bbox']),  # TODO: why is string?
                              crs=CRS(task_data['crs'])),
                    acq_time=dt.datetime.strptime(task_data['datetime'], '%Y-%m-%d'),
                    window_shape=[window['height'], window['width']],
                    data_list=json.loads(task_data['data']),
                    vector_data=task_data['vector_data'])

    def is_new_user(self, user_id):
        """ Check if user is at first access on classification app
        """
        return not self.get_user_data(user_id)

    def add_new_user(self, user_name, user_id):
        """ Add new user to store
        """
        save_to_gpd = SaveToGeopedia(self.tables, self.gpd_session.session_id)

        save_to_gpd.save_feature(self.USER_TABLE,
                                 dict(name=user_name, user_id=user_id))

    def get_campaign_access_object(self, campaign_id):
        """ Obtains access properties of the campaign
        """
        campaign_data = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign_id),
                                                                       return_all=False)
        return Access(access_type=campaign_data['access'],
                      owner_id=campaign_data['owner_id'])

    def get_public_campaigns(self):
        """ Retrieve IDs and links of active public campaigns
        """
        campaign_data = self.tables[self.CAMPAIGN_TABLE].query_columns(['access', 'is_active'],
                                                                       ['="public"', '=True'])

        return [camp.properties['campaign_id'] for camp in campaign_data], [camp.id for camp in campaign_data]

    def get_user_data(self, user_id):
        """ Method to retrieve user information
        """
        try:
            return self.tables[self.USER_TABLE].query_columns('user_id', '={}'.format(user_id), return_all=False)
        except RuntimeError:
            LOGGER.info("First time login to classification application")
            return []

    def get_campaign_data(self, campaign_ids):
        """ Queries all campaigns with given campaign ids and filters out the ones that are inactive
        """
        return [campaign for campaign in self.tables[self.CAMPAIGN_TABLE].query_rows(campaign_ids)
                if campaign['is_active']]

    def add_access(self, campaign_id, user_id):
        """ Add access to a private campaign to a user with a link to it
        """
        campaign_data = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign_id),
                                                                       return_all=False)

        user_data = self.tables[self.USER_TABLE].query_columns('user_id', '={}'.format(user_id), return_all=False)

        save_to_gpd = SaveToGeopedia(self.tables, self.gpd_session.session_id)

        save_to_gpd.save_feature(self.USER_CAMPAIGN_TABLE,
                                 dict(user_link=user_data.id,
                                      campaign_link=campaign_data.id,
                                      counter=0))

    def user_has_access(self, campaign_id, user_id):
        """ Check whether user has access to campaign
        """
        campaigns = self.get_available_campaigns(user_id)
        return any([campaign.id == campaign_id for campaign in campaigns])

    def get_available_campaigns(self, user_id):
        """ Method to retrieve available campaigns (with basic info) for a given user

        :param user_id: Geopedia user ID
        type user_id: str
        :return: A list of campaigns
        :rtype: list(Campaign)
        """
        user_data = self.get_user_data(user_id)

        user_camp_data = self.tables[self.USER_CAMPAIGN_TABLE].query_columns('user_link', '={}'.format(user_data.id))
        private_campaign_ids = [user_camp['campaign_link'] for user_camp in user_camp_data]

        _, public_campaign_ids = self.get_public_campaigns()
        campaign_data = self.get_campaign_data(set(private_campaign_ids + public_campaign_ids))

        return [Campaign(name=campaign['name'],
                         id=campaign['campaign_id'],
                         description=campaign['description'],
                         access=campaign['access']) for campaign in campaign_data]

    def get_campaign(self, campaign_id):
        """ Method to retrieve a campaign with full info from a given campaign ID

        :param campaign_id: Unique ID of campaign
        :param campaign_id: str
        :return: A campaign with all properties
        :rtype: Campaign
        """
        try:
            campaign_data = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign_id),
                                                                           return_all=False)
        except RuntimeError:
            raise MissingCampaignError(campaign_id)

        in_data = self.tables[self.INPUT_TABLE].query_rows(campaign_data['input_source_link'])
        if isinstance(in_data['layers'], str):
            in_data['layers'] = json.loads(in_data['layers'])

        out_data = self.tables[self.OUTPUT_TABLE].query_rows(campaign_data['output_source_link'])
        if isinstance(out_data['layers'], str):
            out_data['layers'] = json.loads(out_data['layers'])

        input_source = Source(**in_data.properties)
        output_source = Source(**out_data.properties)

        sampling_data = self.tables[self.SAMPLING_TABLE].query_rows(campaign_data['sampling_link'])

        ui_data = self.tables[self.UI_TABLE].query_rows(campaign_data['ui_link'])

        ui_data['ui'] = ui_data['ui'].replace('\n', '\\n')  # Otherwise json couldn't decode new lines

        return Campaign(name=campaign_data['name'],
                        id=campaign_id,
                        description=campaign_data['description'],
                        access=campaign_data['access'],
                        input_source=input_source,
                        output_source=output_source,
                        sampling=sampling_data.properties,
                        ui=json.loads(ui_data['ui']))

    def add_campaign(self, campaign, user_session_id):
        """ Add new campaign to Geopedia table

        :param campaign: A new campaign
        :param user_session_id: Session ID of user
        :return: Status of adding a campaign
        """
        gpd_saver = SaveToGeopedia(self.tables, self.gpd_session.session_id)

        # This data is collected first just in case user would not exist and an error would be raised here
        user_link = self.get_user_data(campaign.access.owner_id).id

        result_table_id = gpd_saver.create_table(user_session_id, campaign.name, campaign.access.access_type).id

        post_data = gpd_saver.save_feature(self.SAMPLING_TABLE, campaign.sampling)
        sampling_link = post_data.id

        post_data = gpd_saver.save_feature(self.UI_TABLE, {'ui': json.dumps(campaign.ui)})
        ui_link = post_data.id

        post_data = gpd_saver.save_feature(self.INPUT_TABLE, campaign.input_source.dump())
        input_source_link = post_data.id

        campaign.output_source.geopedia_layer = result_table_id
        post_data = gpd_saver.save_feature(self.OUTPUT_TABLE, campaign.output_source.dump())
        output_source_link = post_data.id

        post_data = gpd_saver.save_feature(self.CAMPAIGN_TABLE,
                                           dict(campaign_id=campaign.id,
                                                name=campaign.name,
                                                description=campaign.description,
                                                access=campaign.access.access_type,
                                                input_source_link=input_source_link,
                                                output_source_link=output_source_link,
                                                sampling_link=sampling_link,
                                                ui_link=ui_link,
                                                is_active=True,
                                                owner_id=campaign.access.owner_id,
                                                primaryGeometry=campaign.geometry.wkt))
        campaign_id = post_data.id

        gpd_saver.save_feature(self.USER_CAMPAIGN_TABLE,
                               dict(user_link=user_link,
                                    campaign_link=campaign_id,
                                    counter=0))

    def delete_campaign(self, campaign_id):
        """ Delete campaign from available campaigns

        This method doesn't actually a campaign from the table, rather sets it's status to inactive

        :param campaign_id: Unique ID of campaign to deactivate
        :return: Status of deleting a campaign
        """
        # get campaign and update is_active field
        campaign_data = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign_id),
                                                                       return_all=False)

        campaign_data['is_active'] = False
        # parse geometry - must be better way
        # TODO: there is some problem with geometry, it gets deleted!
        campaign_data['primary_geometry'] = campaign_data.geometry.wkt
        gpd_saver = SaveToGeopedia(self.tables, self.gpd_session.session_id)
        gpd_saver.update_feature(self.CAMPAIGN_TABLE,
                                 campaign_data.properties,
                                 campaign_data.id)

    def get_task(self, campaign):
        """ Retrieve an available task from Geopedia table  """
        # get available tasks
        campaign_id = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign.id),
                                                                     return_all=False).id
        task_data_list = self.tables[self.TASK_TABLE].query_columns(['campaign_link', 'is_done'],
                                                                    ['={}'.format(campaign_id), '=False'])
        if not task_data_list:
            return None, 0
        task_data = random.choice(task_data_list)  # TODO: random?
        return self._get_task(task_data), len(task_data_list)

    def add_task(self, campaign):
        """ Write a new task to Geopedia table

        :param campaign: Campaign instance
        """
        campaign_link = self.tables[self.CAMPAIGN_TABLE].query_columns('campaign_id', '="{}"'.format(campaign.id),
                                                                       return_all=False).id
        gpd_saver = SaveToGeopedia(self.tables, self.gpd_session.session_id)

        task = next(campaign.get_sampling_method())
        payload = task.get_app_json()
        gpd_saver.save_feature(self.TASK_TABLE,
                               dict(primaryGeometry=task.bbox.transform(CRS.POP_WEB).wkt,
                                    task_id=payload['id'],
                                    bbox=str(payload['bbox']),
                                    crs=str(payload['crs']),
                                    window=json.dumps(payload['window']),
                                    datetime=payload['datetime'],
                                    data=json.dumps(payload['data']),
                                    vector_data=json.dumps(payload['vectorData'])
                                    if 'vectorData' in payload else None,
                                    campaign_link=campaign_link,
                                    is_done=False))
        return task

    def save_task(self, task_id, user_id, campaign, response):
        """ Save result of task to geopedia

        :param task_id: Task ID
        :param user_id: Geopedia ID of user
        :param campaign: Campaign object
        :param response: POST response with files to write to Geopedia table
        """
        task_data = self.tables[self.TASK_TABLE].query_columns('task_id', '="{}"'.format(task_id), return_all=False)
        task = self._get_task(task_data)
        task_dict = task_data.properties
        task_dict['is_done'] = True
        task_dict['primary_geometry'] = task.bbox.transform(CRS.POP_WEB).wkt

        save_to_gpd = SaveToGeopedia(self.tables, self.gpd_session.session_id)
        # save files
        results_table = GeopediaTable.load(int(campaign.output_source.geopedia_layer), self)
        files = response.files.to_dict()
        masks = [self._get_document_json(filename, campaign.get_sampling_window(), True)
                 for filename in set(response.files.keys()) if filename.endswith('.png')]
        save_to_gpd.save_files(results_table,
                               dict(primaryGeometry=task_dict['primary_geometry'],
                                    task_id=task_id,
                                    task_payload=json.dumps(task.get_app_json()),
                                    masks=masks),
                               files=files)
        # update task table
        save_to_gpd.update_feature(self.TASK_TABLE,
                                   task_dict,
                                   task_data.id)
        # update user-task table
        save_to_gpd.save_feature(self.TASK_USER_TABLE,
                                 dict(task_link=task_data.id, user_id=user_id))

        # TODO: update user-campaign table
        # save_to_gpd.update_feature(self.USER_CAMPAIGN_TABLE,
        #                            dict(user_link=user_data.id,
        #                                 campaign_link=campaign_data.id,
        #                                 counter=0))

        return True
