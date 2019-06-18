"""
This module implements all types of users and their properties
"""
from enum import Enum

import attr
from attr.validators import instance_of


ADMIN_USER_IDS = {}


class AccessType(Enum):
    PUBLIC = 'public'
    PRIVATE = 'private'

    def __str__(self):
        return self.value


@attr.s(kw_only=True)
class Access:

    access_type = attr.ib(converter=AccessType)
    owner_id = attr.ib(converter=int, default=-10)

    @staticmethod
    def load(item):
        """ Method from loading class from a payload
        """
        if isinstance(item, Access) or item is None:
            return item
        if isinstance(item, dict):
            return Access(**item)
        if isinstance(item, str):
            return Access(access_type=item)
        raise ValueError('Unsupported type of campaign access payload')

    def has_access(self, user_id):
        """ Decides if user has access to a campaign or data source
        """
        user_id = int(user_id)
        return self.access_type is AccessType.PUBLIC or user_id == self.owner_id or user_id in ADMIN_USER_IDS

    def can_delete(self, user_id):
        """ Decides if user is allowed to delete a campaign
        """
        user_id = int(user_id)
        return user_id == self.owner_id or user_id in ADMIN_USER_IDS


@attr.s
class User:

    name = attr.ib(validator=instance_of(str))
    id = attr.ib(validator=instance_of(int))
    campaign_ids = attr.ib(validator=instance_of(list))
    ranking = attr.ib(validator=instance_of(list))

    def to_json(self):
        return {
            'name': self.name,
            'id': self.id,
            'campaignId': self.campaign_ids,
            'ranking': self.ranking
        }
