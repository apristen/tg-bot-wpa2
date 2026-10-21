# Telegram Bot for WiFi Security Testing

## Overview

A **Telegram bot** designed for quick security testing of WiFi networks by **brute-forcing WPA2 EAPOL/HANDSHAKE hashes**. 

> [!WARNING]
> This tool is intended for authorized security auditing and educational purposes only. Always obtain explicit permission before testing networks you do not own.

---

## Run How-To

Follow these steps to get the bot up and running:

### 1. Install Prerequisites
Ensure you have **Docker** and **Docker Compose** installed on your system. 

### 2. Install NVIDIA Container Toolkit
Because this bot utilizes GPU acceleration for hash cracking, you need to install the **NVIDIA Container Toolkit**. 
Follow the official installation guide here:
👉 [NVIDIA Container Toolkit Installation Guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### 3. Clone the Repository
Clone the project repository and navigate into the project directory:
```bash
git clone git@github.com:apristen/tg-bot-wpa2.git && cd tg-bot-wpa2
```

### 4. Configure Environment Variables
Create and configure your environment file. Copy the example file (if available) or create a new `.env` file in the root directory:
```bash
cp .env.example .env
```
Open the `.env` file and fill it with your specific settings (such as Telegram API tokens, bot settings, and paths).

### 5. Launch the Bot
Start the application in detached mode using Docker Compose:
```bash
docker-compose up -d
```

Enjoy! 🚀 :)
