"""
Script which runs the service

To run in production set env variable in terminal
> export PRODUCTION=true
"""

import os
import matplotlib
matplotlib.use('agg')

from classification_service.service import app


if __name__ == '__main__':
    app.run(
        host=os.environ.get('IP', '127.0.0.1'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('PRODUCTION', 'false').lower() == 'false'
    )
