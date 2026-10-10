FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-dev build-essential ffmpeg libsndfile1 libsamplerate0-dev git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /venv
ENV PATH="/venv/bin:${PATH}"
RUN pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128
COPY constraints.txt /station/constraints.txt
RUN pip install -c /station/constraints.txt "audio-separator[gpu]==0.47.0" "onnxruntime-gpu==1.22.0" "audioread==3.0.1"
# Import the inference entry point during build, without loading models or a GPU.
RUN python3 -c 'from audio_separator.separator import Separator; import audioread, torch; assert torch.__version__ == "2.7.1+cu128", torch.__version__'
COPY launch_separator.py /station/launch_separator.py
RUN printf '#!/venv/bin/python3\nimport runpy\nrunpy.run_path("/station/launch_separator.py", run_name="__main__")\n' > /venv/bin/station-separate && chmod 755 /venv/bin/station-separate
WORKDIR /work
CMD ["python3", "-c", "import time; time.sleep(10**9)"]
