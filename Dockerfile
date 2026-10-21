FROM debian:13-slim

ENV DEBIAN_FRONTEND=noninteractive

# Remove the default deb822 source configuration file
RUN rm -f /etc/apt/sources.list.d/debian.sources

RUN echo "deb http://mirror.truenetwork.ru/debian/ trixie main contrib non-free non-free-firmware" > /etc/apt/sources.list
RUN echo "deb-src http://mirror.truenetwork.ru/debian/ trixie main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN echo "deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN echo "deb-src http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN echo "deb http://mirror.truenetwork.ru/debian/ trixie-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list
RUN echo "deb-src http://mirror.truenetwork.ru/debian/ trixie-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    hashcat \
    nvidia-opencl-icd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

CMD ["python3", "bot/main.py"]
