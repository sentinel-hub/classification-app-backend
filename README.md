# ClassificationApp back-end service

A server site support for [ClassificationApp](https://apps.sentinel-hub.com/classificationApp/#lat=16.969046833518632&lng=36.77102565765381&zoom=14).

**In order to run the back-end service, a Geopedia or equivalent database with 
tables as defined in `schemas.py` needs to be created. Get in touch if you are interested in 
reproducing the results using Geopedia.**

A valid Sentinel Hub instance ID is required to retrieve Sentinel imagery. The instance ID
need be added to the `data/input_sources.json` file.  


## How to run the service

There are multiple ways how to run the service:

### Running development server locally (using pip)
(Required: Python >= 3.5)

- Clone git repository, move to the main project folder and install the project as a normal Python package. The following will install it in editable mode:

```bash
pip install -e . --upgrade
```
(On Windows some dependency packages might raise an error during installation. Install them from [wheels repo](https://www.lfd.uci.edu/~gohlke/pythonlibs/).)

- Start running the service with:
```bash
python main.py
```

### Running development server locally (using pipenv)
(Required: Python >= 3.5)

- Clone git repository, move to the main project folder and install packages:
```bash
pipenv install
```

- Enter virtual environment:
```bash
pipenv shell
```

- Start the service:
```bash
python main.py
```

### Running production server locally
(Required: docker)

- Clone git repository, move to the main project folder and create a docker image:

```bash
docker build . --tag=class-service
```

- Run the image in a container:

```bash
docker run -p 5000:80 class-service
```
(The service will be available at port 5000)

## Development

### Service end points

The running service will produce a swagger documentation at `/docs` (e.g locally that is 'http://127.0.0.1:5000/docs').

For more details check `./classification-service/service.py`. There you will also see example calls with `curl`.
