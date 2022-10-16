FROM python:3.9

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./billing /code/billing

CMD ["uvicorn", "billing.app:app", "--host", "0.0.0.0", "--port", "80"]
