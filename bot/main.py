import os
import re
import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types, BaseMiddleware
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp_socks import ProxyConnector  # Native high-performance SOCKS connector
from collections import deque

# Set up clean logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ALLOWED_USER_IDS = [int(uid.strip()) for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()]
HASHCAT_LOG_N_LINES = int(os.environ.get("HASHCAT_LOG_N_LINES", 30))
PROXY_URI = os.environ.get("PROXY_URI") or None

# Pass the session object directly to the Bot instance
bot = None
dp = Dispatcher()

# Universal regex for WPA*01* and WPA*02* formats
WPA_REGEX = re.compile(r"WPA\*[0-9]{2}\*[a-fA-F0-9\*]+")

# Global state manager for Hashcat tasks
class HashcatManager:
    def __init__(self):
        self.process = None
        self.current_user = None
        self.current_hash_file = None
        self.selected_wordlist = "rockyou.txt"  # Default wordlist placeholder
        self.current_status = "No status update received yet."

manager = HashcatManager()

# Middleware to strictly restrict access to whitelisted IDs
class StrictAccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data):
        if event.from_user.id not in ALLOWED_USER_IDS:
            logging.warning(f"Access denied for user ID: {event.from_user.id}")
            return
        return await handler(event, data)

dp.message.middleware(StrictAccessMiddleware())

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id not in ALLOWED_USER_IDS: return
    welcome_text = (
        "WPA2 Hashcat Bot Menu:\n"
        "/dict  - Show and select available wordlists\n"
        "/8dig WPA*02*... - Bruteforce exactly 8 digits mask\n"
        "/status - Check current Hashcat running state\n"
        "/stop   - Abort current running Hashcat process\n"
        "/potfile - Returns potfile.txt with cracked hashes\n"
        "/nvidia_smi - Print current nvidia-smi host stats\n"
        "/panic  - Emergency hard reset container and clear GPU\n\n"
        "Or just send your raw WPA*01* or WPA*02* hashes text to crack using selected wordlist."
    )
    await message.answer(welcome_text)

@dp.message(Command("dict"))
async def cmd_dict(message: types.Message):
    wordlists_dir = "/app/wordlists"
    if not os.path.exists(wordlists_dir):
        await message.answer("[INFO] Wordlists directory does not exist.")
        return

    # List all files inside the directory regardless of extension
    files = [f for f in os.listdir(wordlists_dir) if os.path.isfile(os.path.join(wordlists_dir, f))]
    if not files:
        await message.answer("[INFO] No wordlists found in /app/wordlists folder.")
        return

    # Process dict selection if arguments are provided
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        chosen = args[1].strip()
        if chosen in files:
            manager.selected_wordlist = chosen
            await message.answer(f"[SUCCESS] Selected wordlist changed to: {chosen}")
        else:
            await message.answer(f"[ERROR] File '{chosen}' not found in the list.")
        return

    # Print the files list and selection instruction
    list_str = "\n".join([f"- `{f}`" for f in files])
    await message.answer(
        f"Available wordlists:\n{list_str}\n\n"
        f"Current: `{manager.selected_wordlist}`\n"
        f"To select type: /dict filename",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    if not manager.process:
        await message.answer("[INFO] Hashcat is not running right now.")
        return
    try:
        manager.process.terminate()
        await message.answer("[SUCCESS] Hashcat process termination signal sent requested by user.")
    except Exception as e:
        await message.answer(f"[ERROR] Failed to terminate: {str(e)}")

@dp.message(Command("potfile"))
async def cmd_potfile(message: types.Message):
    potfile_path = "/root/.local/share/hashcat/hashcat.potfile"
    
    # Check if target file exists on disk and contains data
    if not os.path.exists(potfile_path) or os.path.getsize(potfile_path) == 0:
        await message.answer("[INFO] Your potfile is empty or has not been created yet.")
        return

    try:
        # Send raw potfile mapped as a standard .txt attachment for easy previewing
        file_to_send = types.FSInputFile(potfile_path, filename="potfile.txt")
        await message.answer_document(file_to_send, caption="Stored potfile entries")

    except Exception as e:
        await message.answer(f"[ERROR] Failed to fetch potfile object: {str(e)}")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not manager.process:
        await message.answer("[INFO] Hashcat is currently IDLE. No active cracking tasks.")
        return

    # Join the last N console strings from the rolling memory buffer
    console_snapshot = "\n".join(list(manager.current_status))
    
    await message.answer(
        f"[INFO] Hashcat Console Tail (Last N lines):\n```\n{console_snapshot}\n```", 
        parse_mode="Markdown"
    )

@dp.message(Command("8dig"))
async def cmd_8dig(message: types.Message):
    clean_text = message.text.replace("/8dig", "").strip()
    await run_hashcat_attack(message, clean_text, mode="8digits")

@dp.message(Command("nvidia_smi"))
async def cmd_nvidia_smi(message: types.Message):
    try:
        process = await asyncio.create_subprocess_exec(
            "nvidia-smi", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            gpu_stats = stdout.decode("utf-8").strip()
            await message.answer(f"[INFO] Current GPU Status:\n```\n{gpu_stats}\n```", parse_mode="Markdown")
        else:
            error_text = stderr.decode("utf-8").strip()
            await message.answer(f"[ERROR] Failed to run nvidia-smi. Code: {process.returncode}\n{error_text}")
    except Exception as e:
        await message.answer(f"[FATAL] GPU monitoring execution error: {str(e)}")

@dp.message(Command("panic"))
async def cmd_panic(message: types.Message):
    await message.answer("[EMERGENCY] Initiating hard reset. Killing all subprocesses and restarting container...")
    await asyncio.sleep(1)
    os.kill(-1, 9)

@dp.message()
async def handle_default_hashes(message: types.Message):
    if not message.text: return
    if message.text.startswith("/"): return
    await run_hashcat_attack(message, message.text, mode="wordlist")

async def run_hashcat_attack(message: types.Message, text: str, mode: str):
    if not text:
        await message.answer("[WARNING] Please send valid WPA string text along with the action.")
        return

    found_hashes = WPA_REGEX.findall(text)
    if not found_hashes:
        await message.answer("[WARNING] No valid WPA*01* or WPA*02* hashes detected in your input.")
        return

    if manager.process:
        await message.answer(
            f"[WARNING] Hashcat is busy processing a job for user {manager.current_user}.\n"
            f"If you want to abort the current job first, run /stop command."
        )
        return

    hash_file = f"/root/.local/share/hashcat/{message.from_user.id}_{int(time.time())}.txt" # unique each time!
    wordlist_path = f"/app/wordlists/{manager.selected_wordlist}"

    if mode == "wordlist" and not os.path.exists(wordlist_path):
        await message.answer(f"[ERROR] Selected wordlist file not found at {wordlist_path}")
        return

    with open(hash_file, "w") as f:
        for h in found_hashes:
            f.write(f"{h.strip()}\n")

    base_cmd = ["hashcat", "-m", "22000", hash_file, "--workload-profile", "2", "--status", "--status-timer=5"]
    
    if mode == "8digits":
        cmd = base_cmd + ["-a", "3", "?d?d?d?d?d?d?d?d"]
        await message.answer(f"Launching 8-digits BRUTEFORCE attack for {len(found_hashes)} hash(es)...")
    else:
        cmd = base_cmd + [wordlist_path]
        await message.answer(f"Launching WORDLIST attack ({manager.selected_wordlist}) for {len(found_hashes)} hash(es)...")

    # Added stdin=PIPE so the bot can simulate pressing keys interactively
    manager.process = await asyncio.create_subprocess_exec(
        *cmd, 
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, 
        stderr=asyncio.subprocess.PIPE
    )
    manager.current_user = message.from_user.id
    manager.current_hash_file = hash_file
    
    # Initialize a rolling log buffer keeping exactly the last N lines
    manager.current_status = deque(maxlen=HASHCAT_LOG_N_LINES)
    manager.current_status.append("Hashcat started. Gathering console snapshot...")

    try:
        # Non-blocking background loop to stream stdout line by line
        while True:
            line_bytes = await manager.process.stdout.readline()
            if not line_bytes:
                break  # Process exited
            
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if line:
                # Keep appending every raw console log line into the running queue
                manager.current_status.append(line)

        # Wait for the process code to finalize after stdout closes
        return_code = await manager.process.wait()
        _, stderr_bytes = await manager.process.communicate() # stderr can be read safely now

        # Hashcat returns 0 for BOTH successful crack AND clean keyspace exhaustion
        if return_code == 0:
            # Short sleep to guarantee the OS completely flushes potfile tables to disk
            await asyncio.sleep(0.5)
            
            show_cmd = ["hashcat", "-m", "22000", hash_file, "--show"]
            show_proc = await asyncio.create_subprocess_exec(
                *show_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            show_out, _ = await show_proc.communicate()          
            result_text = show_out.decode("utf-8").strip() if show_out else ""
            
            # If --show returned a valid string, it means the hash is DEFINITELY cracked
            if result_text:
                await message.answer(f"[SUCCESS] Cracking completed!\n\nResult(s):\n`{result_text}`", parse_mode="Markdown")
            else:
                # If return code is 0 but --show is empty, the wordlist/mask is exhausted without matches
                await message.answer("[INFO] Cracking finished. No passwords matches found in the wordlist/mask.")
        elif return_code in [255, -15]:  # Standard Linux process killed return codes
            await message.answer("[INFO] Hashcat attack was aborted by user request successfully.")
        else:
            # Any non-zero return code except manual stops means an actual runtime failure
            error_text = stderr_bytes.decode("utf-8").strip() if stderr_bytes else f"Exit code: {return_code}"
            await message.answer(f"[WARNING] Hashcat process failed. Check backend configuration or logs.\n`{error_text}`")
    except Exception as e:
        await message.answer(f"[FATAL] Process runtime exception loop error: {str(e)}")
    finally:
        if os.path.exists(hash_file):
            os.remove(hash_file)
        manager.process = None
        manager.current_user = None
        manager.current_hash_file = None

async def main():
    global bot
    session = AiohttpSession(proxy=PROXY_URI)
    bot = Bot(token=TELEGRAM_TOKEN, session=session)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
