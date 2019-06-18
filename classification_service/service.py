"""
This module implements the service for communicating with Classification App
"""

import os
import sys
import logging
import datetime
import traceback

from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from flask_restplus import Resource, Api
from flask_restplus.reqparse import RequestParser
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from marshmallow import ValidationError

from sentinelhub import GeopediaSession, DownloadFailedException

from .geopedia import GeopediaConfig
from .orchestrator import Orchestrator
from .store import GeopediaStore
from .utils import to_json, to_python
from .schemas import get_flask_schema, AvailableInputSourcesSchema, CreateCampaignSchema, AvailableCampaignsSchema, \
    CampaignInfoSchema, TaskSchema
from .exceptions import CustomServiceException
from ._version import __version__

# pylint: disable=no-self-use
# pylint: disable=protected-access

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

AUTHORIZATION_STR = 'Authorization'
MESSAGE = 'message'

GeopediaConfig.set_sh_config()
# orchestrator = Orchestrator(LocalStore, filename='./../data/local_data.json')
orchestrator = Orchestrator(GeopediaStore)

app = Flask(__name__)
app.config["PROPAGATE_EXCEPTIONS"] = True
app.config['RESTPLUS_MASK_SWAGGER'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', '<JWT_SECRET_KEY>')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(hours=1)
app.config['JWT_HEADER_TYPE'] = ''
app.config['JWT_ERROR_MESSAGE_KEY'] = MESSAGE

api = Api(app, version=__version__, title='Classification App Backend', contact='eoresearch@sinergise.com',
          description='Service for handling classification campaigns, providing tasks for users and processing results',
          default=os.environ.get('SERVICE_NAMESPACE', 'classification'), default_label='version {}'.format(__version__),
          doc='/docs')
GENERAL_RESPONSES = {
    200: 'Success',
    400: 'Incorrect request parameters',
    404: 'Parameters in URL path are invalid'
}
AUTHORIZATION_RESPONSES = {
    401: 'Missing or expired authorization token',
    422: 'Invalid authorization token'
}
CAMPAIGN_ID = 'campaign_id'
TASK_ID = 'task_id'
PARAMETER_DESCRIPTIONS = {
    CAMPAIGN_ID: 'A campaign ID string',
    TASK_ID: 'A task ID string'
}

jwt = JWTManager(app)
# The following is a hack that enable JWTManager to pass its own error handlers to Api
jwt._set_error_handler_callbacks(api)

CORS(app, resources={r"/*": {"origins": "*"}})


@api.route('/login')
class Login(Resource):
    """ Endpoint for login into Classification App. It starts a new session.

    Login has to be done with a post request where username and password are in payload. Password has to be MD5 encoded.
    Optionally you can specify response format, which is by default json.

    curl -d "username=test_normaluser&password=<pswd_md5>" \
    -X POST "http://127.0.0.1:5000/login" -o token.json

    curl -d "username=test_normaluser&password=<pswd_md5>&format=application/text" \
    -X POST "http://127.0.0.1:5000/login" -o token.txt
    """
    USERNAME = 'username'
    PASSWORD = 'password'
    FORMAT = 'format'

    JSON_FORMAT = 'application/json'
    TEXT_FORMAT = 'application/text'

    parser = RequestParser()
    parser.add_argument(USERNAME, required=True, type=str, help='Geopedia username')
    parser.add_argument(PASSWORD, required=True, type=str, help='Geopedia password')
    parser.add_argument(FORMAT, default=JSON_FORMAT, type=str, choices=[JSON_FORMAT, TEXT_FORMAT],
                        help='Format of output response')

    @api.expect(parser)
    @api.doc(responses={
        200: GENERAL_RESPONSES[200],
        400: GENERAL_RESPONSES[400],
        401: 'Login to Geopedia failed'
    })
    @api.representation(TEXT_FORMAT)
    def post(self):
        """ Authentication to the service
        """
        args = self.parser.parse_args()

        try:
            gpd_session = GeopediaSession(username=args[self.USERNAME], password_md5=args[self.PASSWORD])
            LOGGER.info("Created a new session for user '%s'", gpd_session.username)
        except DownloadFailedException:
            return {MESSAGE: 'Invalid username or password'}, 401

        access_token = create_access_token((gpd_session.session_id, gpd_session.user_id))

        # TODO: add user to users_table if not there already
        if orchestrator.is_new_user(gpd_session.user_id):
            orchestrator.add_new_user(gpd_session.username, gpd_session.user_id)

        if args[self.FORMAT] == self.JSON_FORMAT:
            return {AUTHORIZATION_STR: access_token}
        return Response(access_token, content_type=self.TEXT_FORMAT)


@api.route('/sources')
@api.doc(responses=AUTHORIZATION_RESPONSES)
class SourceProvider(Resource):
    """ Manage data about data source for campaigns

    To query list of sources
    curl "http://127.0.0.1:5000/sources" -H "Authorization: $(cat token.txt)"
    """
    @api.response(200, GENERAL_RESPONSES[200], api.schema_model(*get_flask_schema(AvailableInputSourcesSchema)))
    @jwt_required
    def get(self):
        """ Get a list of available input sources for campaign creation
        """
        user_id = get_jwt_identity()[1]

        response = orchestrator.get_input_sources(user_id)

        AvailableInputSourcesSchema(strict=True).validate(response)
        return to_json(response)


@api.route('/campaigns')
class CampaignManager(Resource):
    """ Manage querying, creation and deletion of campaigns

    To query campaign visible to a user
    curl "http://127.0.0.1:5000/campaigns" -H "Authorization: $(cat token.txt)"

    To add a new campaign
    curl -H "Content-Type: application/json" \
        -d '{"name":"New campaign","description":"Something descriptive","access":{"accessType":"private"},
        "sampling":{"method":"random","resolution":10,"windowWidth":128,"windowHeight":128,"buffer":0,"aoi":
        {"type":"Polygon","crs":4326,"coordinates":[[[60,45],[60,46],[61,46],[61,45],[60,45]]]}},"inputSourceId":
        "c8924362434211e9b4869dc96327a82d","layers":[{"title":"Surface","paintAll":false,"classes":
        [{"color":"#FF0000","title":"Wrong classification"}]}]}'\
        -X POST "http://127.0.0.1:5000/campaigns" -H "Authorization: $(cat token.txt)"
    """
    @api.doc(responses={
        400: GENERAL_RESPONSES[400],
        **AUTHORIZATION_RESPONSES
    })
    @api.response(200, GENERAL_RESPONSES[200], api.schema_model(*get_flask_schema(AvailableCampaignsSchema)))
    @jwt_required
    def get(self):
        """ Provide a list of campaigns which user can access
        """
        user_id = get_jwt_identity()[1]

        response = orchestrator.get_available_campaigns(user_id)

        AvailableCampaignsSchema(strict=True).validate(response)
        return to_json(response), 200

    @api.doc(responses={
        201: 'New campaign created',
        400: GENERAL_RESPONSES[400],
        **AUTHORIZATION_RESPONSES
    })
    @api.expect(api.schema_model(*get_flask_schema(CreateCampaignSchema)), validate=False)
    @jwt_required
    def post(self):
        """ Add a new campaign
        """
        try:
            campaign_json = request.get_json()
        except RuntimeError:
            return {MESSAGE: 'Error in reading campaign POST request'}, 400

        LOGGER.debug('New campaign dictionary received')

        user_session_id = get_jwt_identity()[0]
        user_id = get_jwt_identity()[1]
        campaign_json = to_python(campaign_json)

        campaign_json, errors = CreateCampaignSchema().load(campaign_json)
        if errors:
            return {MESSAGE: 'Wrong payload parameters'}, 400

        new_campaign = orchestrator.add_campaign(campaign_json, user_id, user_session_id)

        if new_campaign:
            return {MESSAGE: 'Campaign successfully added'}, 201
        return {MESSAGE: 'Error in adding campaign'}, 400


@api.route('/campaigns/<string:{}>'.format(CAMPAIGN_ID))
@api.doc(
    params={CAMPAIGN_ID: PARAMETER_DESCRIPTIONS[CAMPAIGN_ID]},
    responses={**GENERAL_RESPONSES, **AUTHORIZATION_RESPONSES}
)
class CampaignSelector(Resource):
    """ Manage data of a single campaign

    To query campaign data for a single campaign
    curl "http://127.0.0.1:5000/campaigns/b410c84644d411e9b81c2202fd41f301" -H "Authorization: $(cat token.txt)"

    To delete a campaign
    curl -X DELETE "http://127.0.0.1:5000/campaigns/<campaign_id>" -H "Authorization: $(cat token.txt)"
    """
    @api.response(200, GENERAL_RESPONSES[200], api.schema_model(*get_flask_schema(CampaignInfoSchema)))
    @jwt_required
    def get(self, campaign_id):
        """ Get properties of the specified campaign
        """
        user_id = get_jwt_identity()[1]

        campaign = orchestrator.get_campaign(campaign_id, user_id, allow_new_user=True)

        return to_json(campaign.get_info()), 200

    @api.doc(responses={
        403: 'Not allowed to delete a campaign'
    })
    @jwt_required
    def delete(self, campaign_id):
        """ Delete the specified campaign
        """
        LOGGER.info('Campaign id %s', campaign_id)

        user_id = get_jwt_identity()[1]
        status_code = orchestrator.delete_campaign(campaign_id, user_id)  # TODO: this should be handled with exceptions!

        if status_code == 200:
            return {MESSAGE: "Campaign successfully deleted"}, status_code
        if status_code == 403:
            return {MESSAGE: "Only campaign owner can delete this campaign"}, status_code
        return {MESSAGE: 'Campaign with ID {} does not exist'.format(campaign_id)}, status_code


@api.route('/campaigns/<string:{}>/tasks'.format(CAMPAIGN_ID))
@api.doc(
    params={CAMPAIGN_ID: PARAMETER_DESCRIPTIONS[CAMPAIGN_ID]},
    responses={**GENERAL_RESPONSES, **AUTHORIZATION_RESPONSES}
)
class TaskProvider(Resource):
    """
    To get a task for current campaign
    curl -X POST "http://127.0.0.1:5000/campaigns/b410c84644d411e9b81c2202fd41f301/tasks" \
    -H "Authorization: $(cat token.txt)"
    """
    @api.response(200, GENERAL_RESPONSES[200], api.schema_model(*get_flask_schema(TaskSchema)))
    @api.doc(responses={
        403: 'Not allowed to access a campaign'
    })
    @jwt_required
    def post(self, campaign_id):
        """ Provide a new task for requested campaign
        """
        user_id = get_jwt_identity()[1]
        # Only when user get his first task we add him to a list of users
        # TODO: Maybe user should be added only when he solves the first task?
        campaign = orchestrator.get_campaign(campaign_id, user_id, allow_new_user=True, add_new_user=True)

        task = orchestrator.get_task(campaign)

        return to_json(task.get_app_json()), 200


@api.route('/campaigns/<string:{}>/tasks/<string:{}>/save'.format(CAMPAIGN_ID, TASK_ID))
@api.doc(
    params=PARAMETER_DESCRIPTIONS,
    responses={**GENERAL_RESPONSES, **AUTHORIZATION_RESPONSES}
)
class Save(Resource):
    """
    To save results of a task for current campaign
    curl -d "data=hello" -X POST "http://127.0.0.1:5000/campaigns/b634cc9e44d411e98195b7e98f19201f/tasks/99/save" -H "Authorization: $(cat token.txt)"
    """
    @jwt_required
    def post(self, campaign_id, task_id):
        """ Save results of a given task
        """
        user_id = get_jwt_identity()[1]
        campaign = orchestrator.get_campaign(campaign_id, user_id)

        is_valid_data = orchestrator.save_task(task_id, user_id, campaign, request)

        if is_valid_data:
            return {MESSAGE: 'Saved successfully'}, 200
        return {MESSAGE: 'Wrong data'}, 400


@app.errorhandler(404)
def not_found(_):
    """ Handles invalid endpoint requests
    """
    return jsonify({MESSAGE: 'Invalid request'}), 404


@api.errorhandler(ValidationError)
def validation_error(error):
    """ Handles errors of Marshmallow schema validation
    """
    # The following line solves a nasty bug in Flask-RESTPlus: https://github.com/noirbizarre/flask-restplus/issues/183
    del error.data
    return {MESSAGE: "Internal validation error"}, 500


@api.errorhandler(CustomServiceException)
def custom_service_exception(error):
    """ Handles errors of missing campaign
    """
    LOGGER.info(traceback.format_exc())
    return {MESSAGE: error.message}, error.http_code
