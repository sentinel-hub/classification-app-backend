"""
Module containing data schemas
"""
from marshmallow import Schema, fields
from marshmallow_jsonschema import JSONSchema
from inflection import camelize

from .utils import to_json

REFERENCE_KEY = '$ref'
REQUIRED_KEY = 'required'
TITLE_KEY = 'title'


class AttributionSchema(Schema):
    """ Schema of attribution properties of map layers in UI campaign config
    """
    name = fields.Str(required=True)
    href = fields.URL()


class MapLayerSchema(Schema):
    """ Schema of map layers in UI campaign config
    """
    name = fields.Str(required=True)
    url = fields.URL(required=True)
    attribution = fields.Nested(AttributionSchema)
    presets = fields.List(fields.Str())


class UiSchema(Schema):
    """ Schema of UI part of campaign config
    """
    instructions = fields.Str(default='')
    show_instructions = fields.Bool()
    show_ranking = fields.Bool()
    map_layers = fields.List(fields.Nested(MapLayerSchema))


class AccessSchema(Schema):
    """ Schema of user access configuration
    """
    access_type = fields.Str(required=True)
    owner_id = fields.Int()


class BasicAccessSchema(Schema):
    """ Schema for basic info about access configuration
    """
    access_type = fields.Str(required=True)


class AoiSchema(Schema):
    """ Schema of area of interest configuration
    """
    type = fields.Str(required=True)
    crs = fields.Raw(description='CRS in GeoJSON format',
                     example={"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}})
    coordinates = fields.Raw(description='Coordinates in GeoJSON format',
                             example=[[[60.0, 45.0], [60.0, 46.0], [61.0, 46.0], [61.0, 45.0], [60.0, 45.0]]])


class SamplingSchema(Schema):
    """ Schema of configuration of sampling
    """
    method = fields.Str(required=True)
    resolution = fields.Int()
    window_width = fields.Int()
    window_height = fields.Int()
    buffer = fields.Int()
    aoi = fields.Nested(AoiSchema, required=True)


class ClassSchema(Schema):
    """ Schema of classes for classification
    """
    title = fields.Str(required=True)
    color = fields.Str(required=True)


class LayerSchema(Schema):
    """ Schema of layers for classification
    """
    title = fields.Str(required=True)
    paint_all = fields.Bool()
    classes = fields.List(fields.Nested(ClassSchema), required=True)


class SourceSchema(Schema):
    """ Schema of source parameters
    """
    id = fields.Str()
    name = fields.Str(required=True)
    description = fields.Str(required=True)
    access = fields.Nested(AccessSchema, required=True)
    source_type = fields.Str(required=True)
    geopedia_layer = fields.Int()
    layers = fields.List(fields.Nested(LayerSchema))
    sampling_params = fields.List(fields.Str())
    default_ui = fields.Nested(UiSchema)


class InputSourceInfoSchema(Schema):
    """ Schema of a single input source properties which is sent to user
    """
    id = fields.Str(required=True)
    name = fields.Str(required=True)
    description = fields.Str(required=True)
    sampling_params = fields.List(fields.Str(required=True), required=True)


class AvailableInputSourcesSchema(Schema):
    """ Schema of input sources with properties which is sent to user
    """
    sources = fields.List(fields.Nested(InputSourceInfoSchema), required=True)


class CampaignSchema(Schema):
    """ Schema of entire campaign configuration
    """
    name = fields.Str(required=True)
    id = fields.Str()
    description = fields.Str(required=True)
    access = fields.Nested(AccessSchema, required=True)
    sampling = fields.Nested(SamplingSchema, required=True)
    input_source = fields.Nested(SourceSchema, required=True)
    output_source = fields.Nested(SourceSchema, required=True)
    ui = fields.Nested(UiSchema)


class CreateCampaignSchema(Schema):
    """ Schema for creating a new campaign
    """
    name = fields.Str(required=True)
    description = fields.Str(required=True)
    access = fields.Nested(AccessSchema, required=True)
    sampling = fields.Nested(SamplingSchema, required=True)
    input_source_id = fields.Str(required=True)
    layers = fields.List(fields.Nested(LayerSchema), required=True)
    ui = fields.Nested(UiSchema)


class BasicCampaignSchema(Schema):
    """ Basic info about a campaign
    """
    name = fields.Str(required=True)
    id = fields.Str(required=True)
    description = fields.Str(required=True)
    access = fields.Nested(BasicAccessSchema, required=True)


class AvailableCampaignsSchema(Schema):
    """ Schema of list of available campaigns
    """
    campaigns = fields.List(fields.Nested(BasicCampaignSchema), required=True)


class CampaignInfoSchema(Schema):
    """ Schema of campaign info which are passed from service to the app
    """
    id = fields.Str(required=True)
    name = fields.Str(required=True)
    description = fields.Str(required=True)
    layers = fields.List(fields.Nested(LayerSchema), required=True)
    ui = fields.Nested(UiSchema, required=True)


class TaskDataSchema(Schema):
    """ Schema of raster data which will be passed to the app
    """
    layer = fields.Str()
    image = fields.Str()


class TaskSchema(Schema):
    """ Schema of task info which is passed from service to the app
    """
    id = fields.Str(required=True)
    bbox = fields.List(fields.Float(), required=True)
    crs = fields.Int(required=True)
    window_width = fields.Int(required=True)
    window_height = fields.Int(required=True)
    datetime = fields.DateTime(format='%Y-%m-%d', required=True)
    data = fields.List(fields.Nested(TaskDataSchema))
    vector_data = fields.List(fields.Dict())


def get_schema_json(schema_class):
    """ Returns json description of schema
    """
    return JSONSchema().dump(schema_class()).data


def _get_reference_name(reference):
    return reference.rsplit('/')[-1]


def _recursive_schema_build(schema, schema_collection):
    if REQUIRED_KEY in schema:
        schema[REQUIRED_KEY] = [camelize(name, uppercase_first_letter=False) for name in schema[REQUIRED_KEY]]
    if isinstance(schema.get(TITLE_KEY), str):
        schema[TITLE_KEY] = camelize(schema[TITLE_KEY], uppercase_first_letter=False)

    if REFERENCE_KEY in schema:
        return _recursive_schema_build(schema_collection[_get_reference_name(schema[REFERENCE_KEY])], schema_collection)

    return {key: _recursive_schema_build(value, schema_collection) if isinstance(value, dict) else value
            for key, value in schema.items()}


def get_flask_schema(schema_class):

    schema = get_schema_json(schema_class)
    class_name = _get_reference_name(schema[REFERENCE_KEY])

    schema = schema['definitions']
    return class_name, to_json(_recursive_schema_build(schema[class_name], schema))
