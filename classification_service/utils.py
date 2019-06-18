"""
This utility module handles transforming data from json to python and back
"""

import json
import uuid

from inflection import camelize, underscore


def to_python(data):
    """ Transforms key values into underscore case
    """
    return json.loads(json.dumps(data), object_hook=lambda subdict: {underscore(key):
                                                                     value for key, value in subdict.items()})


def to_json(data):
    """ Transforms key values in camel case
    """
    return json.loads(json.dumps(data), object_hook=lambda subdict: {camelize(key, uppercase_first_letter=False):
                                                                     value for key, value in subdict.items()})


def get_uuid():
    """ Returns an unique id which is generated from current time. Because uuid1 by default also uses host's address
    we remove that part of uuid. Because consecutive IDs are very similar we add a random part from uuid4

    Disadvantage of these IDs is that you can find out when they were generated.
    """
    return uuid.uuid1(node=0).hex[:-12] + uuid.uuid4().hex[:12]
