"""
This module holds constants used throughout the package
"""

from enum import Enum


class GeopediaType(Enum):
    IDENTIFIER = 'long'
    NUMERIC = 'double'
    PLAINTEXT = 'text'
    WIKITEXT = 'html'
    BINARYREFERENCE = 'binaryReferenceArray'
    DATETIME = 'date'
    STYLE = 'text'
    BOOLEAN = 'boolean'
    GEOMETRY = 'geometry'

    @property
    def python_type(self):
        return {
            GeopediaType.IDENTIFIER: int,
            GeopediaType.NUMERIC: float,
            GeopediaType.PLAINTEXT: str,
            GeopediaType.WIKITEXT: str,
            GeopediaType.STYLE: str,
            GeopediaType.BOOLEAN: bool,
            GeopediaType.GEOMETRY: str,
            GeopediaType.BINARYREFERENCE: list,
            GeopediaType.DATETIME: str,
        }[self]


class PermissionType(Enum):
    PRIVATE = 0
    PUBLIC = 113


GPD_FEATURE = {'id': '4*',
               '@id': 'feature/4*',
               'properties': [{'type': 'long', 'value': None},      # row id
                              {'type': 'long', 'value': None},      # user foreign key
                              {'type': 'boolean', 'value': 'false'},  # is_deleted
                              {'type': 'text', 'value': None},      # fulltext
                              {'type': 'long', 'value': None}],     # journal revision number
               'lastUserId': None,
               'tableId': None,
               'table': None,
               'storeAction': 'INSERT',
               'name': None,
               'revision': 0,
               'dataScope': 'ALL'}

GPD_TABLE = {
    'id': '2*',
    '@id': None,
    'dataRevision': 0,
    'publicPermissions': {
        'permissionSet': 0
    },
    'tagIdentifiers': [],
    'settings': {},
    'fields': [
        {
            'id': '3*',
            '@id': None,
            'description': None,
            'type': 'IDENTIFIER',
            'uiPosition': 0,
            'settings': {},
            'isSystemField': 'true',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 0,
            'name': 'id',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '4*',
            '@id': None,
            'description': None,
            'type': 'IDENTIFIER',
            'uiPosition': 0,
            'settings': {},
            'isSystemField': 'true',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 1,
            'name': 'u',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '5*',
            '@id': None,
            'description': None,
            'type': 'BOOLEAN',
            'uiPosition': 0,
            'settings': {},
            'isSystemField': 'true',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 2,
            'name': 'd',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '6*',
            '@id': None,
            'description': None,
            'type': 'PLAINTEXT',
            'uiPosition': 0,
            'settings': {},
            'isSystemField': 'true',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 3,
            'name': 'ft',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '7*',
            '@id': None,
            'description': None,
            'type': 'IDENTIFIER',
            'uiPosition': 0,
            'settings': {},
            'isSystemField': 'true',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 4,
            'name': 'jn_rev_num',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '8*',
            '@id': 'tablefield/8*',
            'description': None,
            'type': 'GEOMETRY',
            'uiPosition': 0,
            'settings': {
                'geometryType': 'POLYGON',
                'geometryCrsId': {
                    'code': 'EPSG:3857'
                }
            },
            'isSystemField': 'false',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 5,
            'name': 'primaryGeometry',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '9*',
            '@id': None,
            'description': '',
            'type': 'PLAINTEXT',
            'uiPosition': 1,
            'settings': {
                'valueFormat': ''
            },
            'isSystemField': 'false',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 6,
            'name': 'task_id',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '10*',
            '@id': None,
            'description': '',
            'type': 'PLAINTEXT',
            'uiPosition': 3,
            'settings': {
                'valueFormat': ''
            },
            'isSystemField': 'false',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 8,
            'name': 'task_payload',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        },
        {
            'id': '11*',
            '@id': None,
            'description': '',
            'type': 'BINARYREFERENCE',
            'uiPosition': 4,
            'settings': {
                'binarySettings': {
                    'objectStorageURI': 'sgswift://*DEFAULT*',
                    'publicURLProvider': None,
                    'supportedTypes': {
                        'IMAGE': {
                            'thumbnails': {
                                '_th': {
                                    'width': 180,
                                    'height': 120,
                                    'mimeType': 'image/png'
                                }
                            },
                            'maxWidth': 1920,
                            'maxHeight': 1080,
                            'allowedMimeTypes': [
                                'image/png'
                            ],
                            'maxSize': None,
                            'maxCount': 20
                        }
                    }
                },
                'valueFormat': ''
            },
            'isSystemField': 'false',
            'tableId': '2*',
            'referencedTableId': None,
            'referencedTable': None,
            'index': 9,
            'name': 'masks',
            'revision': 0,
            'isDeleted': 'false',
            'dataScope': 'ALL',
            'storeAction': 'INSERT'
        }
    ],
    'repTextJS': 'f8N',
    'styleJS': 'return sf.Symbology([ sf.PaintingPass([ sf.LineSymbolizer({ opacity: 1, displacementX: 0, '
               'displacementY: 0, lineType: "SOLID", lineJoin: "BEVEL", lineCap: "SQUARE", stroke: 0xffe8670c, '
               'strokeBackground: 0x0, strokeWidth: 1 }) ]) ]);',
    'iconURI': 'images/icons/table/polyIcon.png',
    'extent': None,
    'descRawHtml': '',
    'descDisplayableHtml': None,
    'name': '',
    'revision': 0,
    'isDeleted': 'false',
    'dataScope': 'ALL',
    'storeAction': 'INSERT'
}

MAX_TASKS = 5
MIN_TASKS = 2
