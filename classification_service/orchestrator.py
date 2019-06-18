"""
This module implements tools for selecting next task for user of Classification App
"""

import logging

from .campaigns import Campaign
from .sources import load_input_sources
from .tasks import TaskThreading
from .constants import MIN_TASKS
from .exceptions import NotAllowedError

LOGGER = logging.getLogger(__name__)


class Orchestrator:
    """ Class orchestrating actions performed on campaign by back-end

    Actions include:
        * retrieving a campaign given its id
        * retrieving user info given its id
        * retrieving campaigns available for a given user
        * adding a new campaign to the store
        * deleting a campaign from the store
        * adding a task to the store to speed up retrieval of tasks
        * retrieving a task from the store
        * save result of a task to store
    """
    def __init__(self, store_class, **kwargs):
        """ Initialise orchestrator with back-end store which will perform actions.

        Only GeopediaStore currently supports all campaign actions, while LocalStore supports only read actions.

        :param store_class: A class for initializing the store
        :type store_class: Store
        :param kwargs: Any parameters for store_class initialization
        """
        self._store_class = store_class
        self._store_params = kwargs

        self._store = None

    @property
    def store(self):
        if self._store is None:
            self._store = self._store_class(**self._store_params)
        return self._store

    @staticmethod
    def get_input_sources(user_id):
        """ For now we only load sources which are saved locally and supported by the service
        """
        input_sources = load_input_sources()
        return {'sources': [source.get_info_json() for source in input_sources.values() if source.has_access(user_id)]}

    def is_new_user(self, user_id):
        """ Check if user is at first access on classification app """
        return self.store.is_new_user(user_id)

    def add_new_user(self, user_name, user_id):
        """ Add new user to store """
        return self.store.add_new_user(user_name, user_id)

    def add_access(self, campaign_id, user_id):
        """ Add access to a private campaign to a user that has link to it """
        return self.store.add_access(campaign_id, user_id)

    def get_campaign(self, campaign_id, user_id, allow_new_user=False, add_new_user=False):
        """ Get information about campaign from campaign ID

        :param campaign_id: Campaign ID
        :type campaign_id: str
        :param user_id: Geopedia user ID
        :type user_id: int
        :param allow_new_user: If a new user is allowed to make this call
        :type allow_new_user: bool
        :param add_new_user: If a new user will be added to the list of participation users
        :type add_new_user: bool
        """
        has_access = self.store.user_has_access(campaign_id, user_id)
        if not allow_new_user and not has_access:
            raise NotAllowedError

        campaign = self.store.get_campaign(campaign_id)

        if not has_access and add_new_user:
            self.store.add_access(campaign_id, user_id)

        campaign.set_instructions_flag(not has_access)

        return campaign

    def get_available_campaigns(self, user_id):
        """ Get list of available campaigns to the specific user
        """
        campaigns = self.store.get_available_campaigns(user_id)
        return {'campaigns': [campaign.get_basic_info() for campaign in campaigns]}

    def delete_campaign(self, campaign_id, user_id):
        """ Delete campaign given campaign id and user id
        """
        campaign_access = self.store.get_campaign_access_object(campaign_id)

        if campaign_access is None:
            return 400
        if not campaign_access.can_delete(user_id):
            return 403

        self.store.delete_campaign(campaign_id)
        return 200

    def add_campaign(self, campaign_payload, user_id, user_session_id):
        """ Create a new campaign from json and save in into the store
        """
        campaign_payload = Campaign.prepare_payload(campaign_payload, user_id)
        campaign = Campaign.load(campaign_payload)

        self.store.add_campaign(campaign, user_session_id)

        thread = TaskThreading(campaign, self.store, interval=.300)
        thread.start()

        return campaign

    def add_task(self, campaign):
        """ Compute a task for the given campaign and save to store """
        return self.store.add_task(campaign)

    def get_task(self, campaign):
        """ Retrieve a task from the store """
        current_task, n_tasks_left = self.store.get_task(campaign)

        # no tasks available on geopedia, compute one and push
        if current_task is None:
            current_task = self.store.add_task(campaign)
            n_tasks_left = 1

        campaign.add_active_task(current_task)

        if n_tasks_left <= MIN_TASKS:
            thread = TaskThreading(campaign, self.store, interval=.300)
            thread.start()

        return current_task

    def save_task(self, task_id, user_id, campaign, request):
        """ Save result of a task to store """
        return self.store.save_task(task_id, user_id, campaign, request)

