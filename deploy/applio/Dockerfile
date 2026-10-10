FROM python:3.10.16-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libportaudio2 libsndfile1 build-essential git ca-certificates && rm -rf /var/lib/apt/lists/*
ADD https://codeload.github.com/IAHispano/Applio/tar.gz/b8791412993ebc934c148bd84798782af2f0439e /tmp/applio.tar.gz
RUN echo '56d30b0d39d45d6c4c3aa331b8dbd8fd1417924d29defea200643cab7c7f864f  /tmp/applio.tar.gz' | sha256sum -c - && mkdir /app && tar -xzf /tmp/applio.tar.gz --strip-components=1 -C /app && rm /tmp/applio.tar.gz
WORKDIR /app
# The base image's old pip rejects normalized wheel names (typing_extensions).
RUN python -m pip install --no-cache-dir --upgrade pip==25.1.1
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu128
COPY launch_applio.py /station/launch_applio.py
ENV GRADIO_ANALYTICS_ENABLED=False HF_HOME=/cache/huggingface TORCH_HOME=/cache/torch
EXPOSE 6969
CMD ["python3", "/station/launch_applio.py"]
