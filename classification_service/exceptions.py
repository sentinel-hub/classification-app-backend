"""
Module where custom exceptions are defined
"""


class CustomServiceException(Exception):
    """ Base class of all custom exceptions defined here
    """
    def __init__(self, message, http_code):
        """
        :param message: Exception message
        :type message: str
        :param http_code: HTTP code of response which will be returned by service
        :type http_code: int
        """
        self.message = message
        self.http_code = http_code
        super().__init__(message)


class MissingCampaignError(CustomServiceException):
    """ This is raised when a campaign with requested ID does not exist
    """
    def __init__(self, campaign_id):
        """
        :param campaign_id: ID of the missing campaign
        :type campaign_id: str
        """
        super().__init__('Campaign with ID {} does not exist'.format(campaign_id), 404)


class NotAllowedError(CustomServiceException):
    """ This is raised whenever user is not allowed to access something
    """
    def __init__(self):
        super().__init__('Not allowed to do that', 403)
