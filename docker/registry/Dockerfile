FROM python:3.11-slim

# SSH client + libssh (required by ansible-pylibssh)
# ansible is installed via pip (not apt) so it shares the same Python as the
# rest of the app — apt ansible uses the system Python which can't see pip packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        libssh-dev \
    && rm -rf /var/lib/apt/lists/*

# Ensure /root/.ansible exists so the vault_pass.txt bind-mount lands as a file,
# not a directory (Docker creates directories when the parent path is missing).
RUN mkdir -p /root/.ansible

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py lookup.py state_io.py servicenow_push.py ./
COPY static/ static/

ENV PORT=5000
EXPOSE 5000

CMD ["python", "server.py"]
