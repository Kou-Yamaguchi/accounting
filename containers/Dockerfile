FROM python:3.9.11

ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fontconfig \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

RUN fc-cache -fv

RUN mkdir -p /root/workspace
COPY requirements.txt /root/workspace/
WORKDIR /root/workspace

RUN pip install --upgrade pip\
    && pip install --upgrade setuptools\
    && pip install -r requirements.txt
