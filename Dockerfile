FROM tiangolo/uwsgi-nginx-flask:python3.6

COPY . /app
RUN pip install .