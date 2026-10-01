FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# "CDC Places/" directory name contains a space — use JSON array form for COPY
COPY ["CDC Places/cdc_places_fetch.py",           "/app/cdc_places_fetch.py"]
COPY ["CDC Places/cdc_places_feature_builder.py", "/app/cdc_places_feature_builder.py"]

WORKDIR /app

# CyVerse DE standard mount points
RUN mkdir -p /input /output

# All CLI args after this point come from the CyVerse form or docker run command.
# --outdir is baked in; everything else is passed at runtime.
ENTRYPOINT ["python3", "/app/cdc_places_feature_builder.py", \
            "--outdir", "/output"]
